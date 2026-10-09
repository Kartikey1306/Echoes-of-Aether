using UnityEngine;
using UnityEngine.Experimental.Rendering;
using UnityEngine.Rendering;
using UnityEngine.Rendering.RenderGraphModule;
using UnityEngine.Rendering.Universal;

namespace EOA
{
    /// <summary>
    /// Game-specific URP passes, enqueued on the game camera every frame from script (no renderer-asset features to
    /// keep in sync): <see cref="WetReflectionsPass"/> (screen-space reflections on wet ground) and
    /// <see cref="RainLatePass"/> (rain streaks after TAA). Both follow <see cref="GraphicsConfig"/>.
    /// </summary>
    public static class RenderPasses
    {
        static bool installed;
        static WetReflectionsPass ssr;
        static RainLatePass rainLate;
        static readonly int WetId = Shader.PropertyToID("_EOA_Wetness");

        public static void Install()
        {
            if (installed) return;
            installed = true;
            ssr = new WetReflectionsPass();
            rainLate = new RainLatePass();
            RenderPipelineManager.beginCameraRendering += OnBeginCamera;
        }

        static readonly int SsrOnId = Shader.PropertyToID("_EOA_SSROn");

        static void OnBeginCamera(ScriptableRenderContext ctx, Camera cam)
        {
            if (cam.cameraType != CameraType.Game) return;
            Shader.SetGlobalFloat(SsrOnId, WetReflectionsPass.Quality > 0 && ssr.Ready ? 1f : 0f);
            var data = cam.GetUniversalAdditionalCameraData();
            if (data == null || data.renderType != CameraRenderType.Base) return;
            var renderer = data.scriptableRenderer;
            if (renderer == null) return;
            if (WetReflectionsPass.Quality > 0 && ssr.Ready && Shader.GetGlobalFloat(WetId) > 0.02f) renderer.EnqueuePass(ssr);
            if (RainLatePass.Active && data.antialiasing == AntialiasingMode.TemporalAntiAliasing) renderer.EnqueuePass(rainLate);
        }
    }

    /// <summary>
    /// Screen-space reflections for wet streets (Hidden/EOA/WetReflections): a reduced-resolution trace of the lit
    /// opaque image along the reflected view ray of every up-facing pixel, composited additively with a vertical
    /// anisotropic blur (the stretched neon streaks of a rain-soaked street). Runs after the sky, before the height
    /// fog and transparents. Quality 0 = off (low effects, WebGL), 1 = third resolution / 14 steps, 2 = half / 22,
    /// 3 = half / 30 (ultra).
    /// </summary>
    public sealed class WetReflectionsPass : ScriptableRenderPass
    {
        public static int Quality;
        /// <summary>Overall reflection strength (zones may scale it; 1 = default).</summary>
        public static float Intensity = 1f;

        static readonly int SsrId = Shader.PropertyToID("_SSR"), Ssr2Id = Shader.PropertyToID("_SSR2"), Ssr3Id = Shader.PropertyToID("_SSR3");
        readonly Material mat;

        sealed class TraceData { public TextureHandle Color; public Material Mat; }
        sealed class CompositeData { public TextureHandle Trace; public Material Mat; }

        public bool Ready => mat != null;

        public WetReflectionsPass()
        {
            renderPassEvent = RenderPassEvent.AfterRenderingSkybox;
            profilingSampler = new ProfilingSampler("EOA Wet Reflections");
            var sh = Resources.Load<Shader>("Env/EOA_WetReflections");
            if (sh == null) sh = Shader.Find("Hidden/EOA/WetReflections");
            if (sh != null && sh.isSupported) mat = CoreUtils.CreateEngineMaterial(sh);
            else Debug.LogWarning("[graphics] wet reflections shader unavailable");
            ConfigureInput(ScriptableRenderPassInput.Depth);
        }

        public override void RecordRenderGraph(RenderGraph renderGraph, ContextContainer frameData)
        {
            if (mat == null || Quality <= 0) return;
            var res = frameData.Get<UniversalResourceData>();
            if (res.isActiveTargetBackBuffer || !res.cameraDepthTexture.IsValid()) return;
            var color = res.activeColorTexture;
            var desc = renderGraph.GetTextureDesc(color);
            var div = Quality == 1 ? 3 : 2;
            var td = new TextureDesc(Mathf.Max(1, desc.width / div), Mathf.Max(1, desc.height / div))
            {
                format = GraphicsFormat.R16G16B16A16_SFloat,
                name = "_EOA_WetReflections",
                clearBuffer = false,
                filterMode = FilterMode.Bilinear,
                wrapMode = TextureWrapMode.Clamp,
            };
            var trace = renderGraph.CreateTexture(td);
            var steps = Quality switch { 1 => 14, 2 => 22, _ => 30 };
            mat.SetVector(SsrId, new Vector4(1.1f * Intensity, Quality == 1 ? 90f : 140f, steps, 0.45f));
            mat.SetVector(Ssr2Id, new Vector4(0.028f, 0.5f, 2.6f, 0.12f));
            mat.SetVector(Ssr3Id, new Vector4(1f / td.width, 1f / td.height, 0, 0));

            using (var builder = renderGraph.AddRasterRenderPass<TraceData>("EOA SSR Trace", out var pd, profilingSampler))
            {
                pd.Color = color;
                pd.Mat = mat;
                builder.UseTexture(color, AccessFlags.Read);
                builder.UseTexture(res.cameraDepthTexture, AccessFlags.Read);
                builder.SetRenderAttachment(trace, 0, AccessFlags.WriteAll);
                builder.SetRenderFunc((TraceData d, RasterGraphContext ctx) => Blitter.BlitTexture(ctx.cmd, d.Color, new Vector4(1, 1, 0, 0), d.Mat, 0));
            }
            using (var builder = renderGraph.AddRasterRenderPass<CompositeData>("EOA SSR Composite", out var pd, profilingSampler))
            {
                pd.Trace = trace;
                pd.Mat = mat;
                builder.UseTexture(trace, AccessFlags.Read);
                builder.UseTexture(res.cameraDepthTexture, AccessFlags.Read);
                builder.SetRenderAttachment(color, 0, AccessFlags.Write);
                builder.SetRenderFunc((CompositeData d, RasterGraphContext ctx) => Blitter.BlitTexture(ctx.cmd, d.Trace, new Vector4(1, 1, 0, 0), d.Mat, 1));
            }
        }
    }

    /// <summary>
    /// Rain streaks after post-processing (LightMode "EOARainLate" of EOA/RainStreaks) when TAA is on: the temporal
    /// resolve would smear or suppress the thin fast drops. The pass tests against the depth texture itself.
    /// </summary>
    public sealed class RainLatePass : ScriptableRenderPass
    {
        /// <summary>True while the game camera uses TAA (set by GraphicsConfig; RainField switches its passes).</summary>
        public static bool Active;
        static readonly ShaderTagId Tag = new("EOARainLate");

        sealed class PassData { public RendererListHandle List; }

        public RainLatePass()
        {
            renderPassEvent = RenderPassEvent.AfterRenderingPostProcessing;
            profilingSampler = new ProfilingSampler("EOA Rain Late");
            ConfigureInput(ScriptableRenderPassInput.Depth);
        }

        public override void RecordRenderGraph(RenderGraph renderGraph, ContextContainer frameData)
        {
            var res = frameData.Get<UniversalResourceData>();
            var rd = frameData.Get<UniversalRenderingData>();
            var cd = frameData.Get<UniversalCameraData>();
            var ld = frameData.Get<UniversalLightData>();
            if (!res.cameraDepthTexture.IsValid()) return;
            using var builder = renderGraph.AddRasterRenderPass<PassData>("EOA Rain Late", out var pd, profilingSampler);
            var ds = RenderingUtils.CreateDrawingSettings(Tag, rd, cd, ld, SortingCriteria.CommonTransparent);
            var fs = new FilteringSettings(RenderQueueRange.transparent, 1 << CityFx.FxLayer);
            pd.List = renderGraph.CreateRendererList(new RendererListParams(rd.cullResults, ds, fs));
            builder.UseRendererList(pd.List);
            builder.UseTexture(res.cameraDepthTexture, AccessFlags.Read);
            builder.SetRenderAttachment(res.activeColorTexture, 0, AccessFlags.Write);
            builder.SetRenderFunc((PassData d, RasterGraphContext ctx) => ctx.cmd.DrawRendererList(d.List));
        }
    }
}
