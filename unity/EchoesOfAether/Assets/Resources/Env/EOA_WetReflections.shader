// Screen-space reflections for wet ground (WetReflectionsPass, after the opaques and the sky, before the height fog
// and every transparent). Only upward-facing surfaces while the city is wet (_EOA_Wetness) take part, so it costs
// nothing indoors or when dry.
//
//   Pass 0 "Trace" (reduced resolution): reconstructs position and normal from the camera depth, reflects the view
//          ray about the ground (wobbled by the rain ripples and a world-stable asphalt undulation), marches it in
//          world space with growing steps against the depth buffer (binary refinement on a hit) and fetches the lit
//          scene colour there. Output: reflected radiance x confidence (screen-edge, distance, thickness fades) x
//          fresnel x wetness, premultiplied.
//   Pass 1 "Composite" (full resolution, additive): a vertical anisotropic blur of the trace, so neon and lamps
//          stretch into the long streaks of a rain-soaked street, masked again at full resolution (no bleeding onto
//          walls), faded by Unity's fog.
//
// Parameters (WetReflectionsPass): _SSR (x intensity, y max distance m, z steps, w thickness m),
// _SSR2 (x wobble, y ripple strength, z stretch in trace texels, w first step m), _SSR3 (xy trace texel size).
Shader "Hidden/EOA/WetReflections"
{
    SubShader
    {
        Tags { "RenderType"="Opaque" "RenderPipeline"="UniversalPipeline" }
        ZWrite Off
        ZTest Always
        Cull Off

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
        #include "Packages/com.unity.render-pipelines.core/Runtime/Utilities/Blit.hlsl"
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"
        #include "Assets/Shaders/EOA_CityFx.hlsl"
        #include "Assets/Shaders/EOA_RainRipple.hlsl"

        float4 _SSR, _SSR2, _SSR3;

        float DeviceDepth(float2 uv, out bool sky)
        {
            float raw = SampleSceneDepth(uv);
            #if UNITY_REVERSED_Z
                sky = raw <= 1e-6;
                return raw;
            #else
                sky = raw >= 0.999999;
                return lerp(UNITY_NEAR_CLIP_VALUE, 1, raw);
            #endif
        }

        float3 WorldAt(float2 uv)
        {
            bool sky;
            float d = DeviceDepth(uv, sky);
            return ComputeWorldSpacePosition(uv, d, UNITY_MATRIX_I_VP);
        }

        // Up-facing mask from the depth buffer (the smaller-difference neighbours keep silhouettes out).
        float UpMask(float2 uv, float3 P, out float3 N)
        {
            float2 t = _CameraDepthTexture_TexelSize.xy;
            float3 r = WorldAt(uv + float2(t.x, 0)) - P, l = P - WorldAt(uv - float2(t.x, 0));
            float3 u = WorldAt(uv + float2(0, t.y)) - P, d = P - WorldAt(uv - float2(0, t.y));
            float3 dx = dot(r, r) < dot(l, l) ? r : l;
            float3 dy = dot(u, u) < dot(d, d) ? u : d;
            N = normalize(cross(dy, dx));
            if (dot(N, _WorldSpaceCameraPos.xyz - P) < 0) N = -N;
            return smoothstep(0.86, 0.96, N.y);
        }

        float EyeOf(float3 p) { return -mul(UNITY_MATRIX_V, float4(p, 1)).z; }

        half4 FragTrace(Varyings input) : SV_Target
        {
            float2 uv = input.texcoord;
            float wet = saturate(_EOA_Wetness);
            if (wet < 0.02) return 0;
            bool sky;
            float dev = DeviceDepth(uv, sky);
            if (sky) return 0;
            float3 P = ComputeWorldSpacePosition(uv, dev, UNITY_MATRIX_I_VP);
            float3 cam = _WorldSpaceCameraPos.xyz;
            float dist = length(P - cam);
            if (dist > _SSR.y) return 0;
            float3 Ng;
            float mask = UpMask(uv, P, Ng);
            if (mask <= 0.001) return 0;

            float3 V = (P - cam) / max(dist, 1e-4);
            // wet ground: flat water film wobbled by the rain ripples and a slow world-space undulation of the asphalt
            float3 rip = EOA_RainRippleNormal(P.xz, 1.1);
            float2 wob = float2(EOA_Noise2(P.xz * 2.7) - 0.5, EOA_Noise2(P.xz * 2.1 + 17.3) - 0.5) * _SSR2.x;
            float3 N = normalize(float3(rip.x * _SSR2.y + wob.x, 1.0, rip.y * _SSR2.y + wob.y));
            float3 R = reflect(V, N);
            if (R.y <= 0.0) return 0;

            // march (world space, growing steps), refine on a hit
            float3 o = P + Ng * 0.04;
            float stepLen = _SSR2.w + dist * 0.006;
            float t = 0, tPrev = 0;
            int steps = (int)_SSR.z;
            bool hit = false;
            float2 huv = 0;
            [loop] for (int i = 0; i < steps; i++)
            {
                tPrev = t;
                t += stepLen;
                stepLen *= 1.22;
                float3 q = o + R * t;
                float2 quv = ComputeNormalizedDeviceCoordinates(q, UNITY_MATRIX_VP);
                if (quv.x < 0 || quv.x > 1 || quv.y < 0 || quv.y > 1) break;
                bool s;
                float sd = DeviceDepth(quv, s);
                if (s) continue;
                float sEye = LinearEyeDepth(sd, _ZBufferParams);
                float qEye = EyeOf(q);
                float diff = qEye - sEye;
                if (diff > 0.0 && diff < _SSR.w + stepLen * 1.2)
                {
                    // binary refinement between the last two samples
                    float lo = tPrev, hi = t;
                    [unroll] for (int k = 0; k < 4; k++)
                    {
                        float mid = (lo + hi) * 0.5;
                        float3 m = o + R * mid;
                        float2 muv = ComputeNormalizedDeviceCoordinates(m, UNITY_MATRIX_VP);
                        bool ms;
                        float md = LinearEyeDepth(DeviceDepth(muv, ms), _ZBufferParams);
                        if (EyeOf(m) > md) hi = mid; else lo = mid;
                    }
                    t = hi;
                    huv = ComputeNormalizedDeviceCoordinates(o + R * t, UNITY_MATRIX_VP);
                    hit = true;
                    break;
                }
            }
            if (!hit) return 0;

            half3 c = SAMPLE_TEXTURE2D_X_LOD(_BlitTexture, sampler_LinearClamp, huv, 0).rgb;
            // fireflies: keep the brightest neon from exploding in the blur
            float lum = max(dot(c, half3(0.2126, 0.7152, 0.0722)), 1e-4);
            c *= min(1.0, 12.0 / lum);
            float2 e = min(huv, 1.0 - huv);
            float edge = smoothstep(0.0, 0.06, e.x) * smoothstep(0.0, 0.12, e.y);
            float far = 1.0 - smoothstep(_SSR.y * 0.55, _SSR.y, t + dist * 0.5);
            float near = smoothstep(0.4, 1.5, dist);
            float nv = saturate(dot(-V, N));
            float fres = 0.02 + 0.98 * pow(1.0 - nv, 5.0);
            // water film fresnel: faint looking down at your feet, strong toward the grazing street ahead
            float w = mask * edge * far * near * wet * (0.07 + 0.93 * fres) * _SSR.x * EOA_UnityFogKeep(EyeOf(P));
            return half4(c * w, w);
        }

        // 9-tap vertical (screen space) anisotropic blur: wet-street reflection streaks.
        half4 FragComposite(Varyings input) : SV_Target
        {
            float2 uv = input.texcoord;
            bool sky;
            float dev = DeviceDepth(uv, sky);
            if (sky) return 0;
            float3 P = ComputeWorldSpacePosition(uv, dev, UNITY_MATRIX_I_VP);
            float3 Ng;
            float mask = UpMask(uv, P, Ng);
            if (mask <= 0.001) return 0;
            float2 texel = _SSR3.xy;
            float stretch = _SSR2.z;
            half3 acc = 0;
            half wsum = 0;
            [unroll] for (int k = -4; k <= 4; k++)
            {
                half wk = exp(-k * k * 0.18);
                float2 o = float2(k * 0.15 * texel.x, k * stretch * texel.y);
                acc += SAMPLE_TEXTURE2D_X_LOD(_BlitTexture, sampler_LinearClamp, uv + o, 0).rgb * wk;
                wsum += wk;
            }
            return half4(acc / wsum * mask, 0);
        }
        ENDHLSL

        Pass
        {
            Name "Trace"
            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment FragTrace
            #pragma target 3.5
            ENDHLSL
        }

        Pass
        {
            Name "Composite"
            Blend One One
            HLSLPROGRAM
            #pragma vertex Vert
            #pragma fragment FragComposite
            #pragma target 3.5
            ENDHLSL
        }
    }
    Fallback Off
}
