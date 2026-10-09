using System;
using System.IO;
using System.Linq;
using System.Reflection;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace EOA.EditorTools
{
    /// <summary>
    /// One-click (and automatic first-open) project setup for Echoes of Aether:
    /// layers + physics matrix, URP asset/renderer (Forward+), quality, player/WebGL settings, shader/variant
    /// template materials, environment library, characters, UI assets, the Boot scene and build settings.
    /// Menu: EOA/Setup Project (All). Batch: -executeMethod EOA.EditorTools.ProjectSetup.RunAllBatch
    /// </summary>
    [InitializeOnLoad]
    public static class ProjectSetup
    {
        const int Version = 1;
        const string Marker = "ProjectSettings/EOA_Setup.txt";
        const string SettingsDir = "Assets/Settings";
        public const string BootScene = "Assets/Scenes/Boot.unity";

        static readonly (int index, string name)[] Layers =
        {
            (6, "World"), (7, "Player"), (8, "Enemy"), (9, "NPC"), (10, "Interactable"), (11, "Projectile"), (12, "IgnoreCamera"), (13, "Pickup"),
        };

        static ProjectSetup()
        {
            if (Application.isBatchMode) return;
            EditorApplication.delayCall += AutoRun;
        }

        static int InstalledVersion => File.Exists(Marker) && int.TryParse(File.ReadAllText(Marker).Trim(), out var v) ? v : 0;

        static void AutoRun()
        {
            if (InstalledVersion >= Version) return;
            if (EditorApplication.isCompiling || EditorApplication.isUpdating || EditorApplication.isPlayingOrWillChangePlaymode)
            {
                EditorApplication.delayCall += AutoRun;
                return;
            }
            Debug.Log("[setup] first open: running EOA project setup");
            RunAll();
        }

        [MenuItem("EOA/Setup Project (All)", priority = 0)]
        public static void RunAll()
        {
            var failures = 0;
            void Step(string label, float progress, Action a)
            {
                EditorUtility.DisplayProgressBar("Echoes of Aether setup", label, progress);
                try { a(); Debug.Log("[setup] ✓ " + label); }
                catch (Exception e) { failures++; Debug.LogError($"[setup] ✗ {label}: {e}"); }
            }
            try
            {
                Step("Layers", 0.02f, SetupLayers);
                Step("Physics", 0.04f, SetupPhysics);
                Step("Render pipeline", 0.08f, SetupRenderPipeline);
                Step("Player settings", 0.12f, SetupPlayer);
                Step("Shader templates", 0.16f, SetupTemplates);
                Step("Environment library", 0.2f, EnvLibraryBuilder.Build);
                Step("Robot materials", 0.6f, SetupRobotMaterial);
                Step("Characters", 0.65f, CharacterBuilder.BuildAll);
                Step("Customization library", 0.8f, CustomizationBuilder.Build);
                Step("UI", 0.85f, UISetup.Run);
                Step("Boot scene", 0.95f, SetupBootScene);
            }
            finally { EditorUtility.ClearProgressBar(); }
            AssetDatabase.SaveAssets();
            if (failures == 0) File.WriteAllText(Marker, Version.ToString());
            Debug.Log(failures == 0 ? "[setup] Echoes of Aether project setup complete. Open Assets/Scenes/Boot.unity and press Play."
                                    : $"[setup] finished with {failures} failed step(s); see errors above. Run EOA/Setup Project (All) again after fixing.");
        }

        /// <summary>Batch-mode entry point; exits with code 1 if any step failed.</summary>
        public static void RunAllBatch()
        {
            RunAll();
            EditorApplication.Exit(InstalledVersion >= Version ? 0 : 1);
        }

        // ------------------------------------------------------------------ layers & physics

        static void SetupLayers()
        {
            var tagManager = new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/TagManager.asset")[0]);
            var layers = tagManager.FindProperty("layers");
            foreach (var (i, n) in Layers)
            {
                var p = layers.GetArrayElementAtIndex(i);
                if (p.stringValue != n) p.stringValue = n;
            }
            tagManager.ApplyModifiedPropertiesWithoutUndo();
        }

        static void SetupPhysics()
        {
            const int world = 6, player = 7, enemy = 8, npc = 9, interact = 10, proj = 11, ignoreCam = 12, pickup = 13;
            // Projectiles resolve hits with queries; their (trigger) bodies never need contacts with each other or pickups.
            Physics.IgnoreLayerCollision(proj, proj, true);
            Physics.IgnoreLayerCollision(proj, pickup, true);
            Physics.IgnoreLayerCollision(proj, interact, true);
            Physics.IgnoreLayerCollision(proj, ignoreCam, true);
            // Pickups and interaction volumes only matter to the player.
            foreach (var l in new[] { world, enemy, npc, interact, ignoreCam, pickup, 0 }) Physics.IgnoreLayerCollision(pickup, l, true);
            foreach (var l in new[] { world, enemy, npc, interact, ignoreCam, 0 }) Physics.IgnoreLayerCollision(interact, l, true);
            Physics.queriesHitTriggers = false;
            Physics.autoSyncTransforms = false;
        }

        // ------------------------------------------------------------------ render pipeline

        static void SetupRenderPipeline()
        {
            EnvLibraryBuilder.EnsureFolder(SettingsDir);
            var assetPath = SettingsDir + "/EOA_URP.asset";
            var rendererPath = SettingsDir + "/EOA_URP_Renderer.asset";
            var urp = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(assetPath);
            if (urp == null)
            {
                var data = AssetDatabase.LoadAssetAtPath<UniversalRendererData>(rendererPath);
                if (data == null)
                {
                    data = ScriptableObject.CreateInstance<UniversalRendererData>();
                    data.postProcessData = AssetDatabase.LoadAssetAtPath<PostProcessData>("Packages/com.unity.render-pipelines.universal/Runtime/Data/PostProcessData.asset");
                    AssetDatabase.CreateAsset(data, rendererPath);
                    ResourceReloader.ReloadAllNullIn(data, "Packages/com.unity.render-pipelines.universal");
                }
                data.renderingMode = RenderingMode.ForwardPlus;
                EditorUtility.SetDirty(data);
                urp = UniversalRenderPipelineAsset.Create(data);
                AssetDatabase.CreateAsset(urp, assetPath);
            }
            var so = new SerializedObject(urp);
            void SetInt(string p, int v) { var sp = so.FindProperty(p); if (sp != null) sp.intValue = v; else Debug.LogWarning("[setup] URP field missing: " + p); }
            void SetBool(string p, bool v) { var sp = so.FindProperty(p); if (sp != null) sp.boolValue = v; else Debug.LogWarning("[setup] URP field missing: " + p); }
            void SetFloat(string p, float v) { var sp = so.FindProperty(p); if (sp != null) sp.floatValue = v; else Debug.LogWarning("[setup] URP field missing: " + p); }
            SetBool("m_SupportsHDR", true);
            SetInt("m_MSAA", 1);
            SetFloat("m_RenderScale", 1f);
            SetBool("m_RequireDepthTexture", true);
            SetBool("m_RequireOpaqueTexture", false);
            SetInt("m_MainLightRenderingMode", 1);          // per pixel
            SetBool("m_MainLightShadowsSupported", true);
            SetInt("m_MainLightShadowmapResolution", 2048);
            SetInt("m_AdditionalLightsRenderingMode", 1);   // per pixel
            SetInt("m_AdditionalLightsPerObjectLimit", 8);
            SetBool("m_AdditionalLightShadowsSupported", false);
            SetBool("m_ReflectionProbeBlending", true);
            SetBool("m_ReflectionProbeBoxProjection", false);
            SetFloat("m_ShadowDistance", 70f);
            SetInt("m_ShadowCascadeCount", 2);
            SetFloat("m_Cascade2Split", 0.22f);
            SetBool("m_SoftShadowsSupported", true);
            SetBool("m_UseSRPBatcher", true);
            SetBool("m_SupportsDynamicBatching", false);
            SetInt("m_ColorGradingMode", 1);                // HDR grading
            SetInt("m_ColorGradingLutSize", 32);
            SetBool("m_EnableLODCrossFade", true);
            SetInt("m_SoftShadowQuality", 3);               // high
            SetBool("m_SupportsLightLayers", true);         // rendering layers: character-only rim/fill lights
            so.ApplyModifiedPropertiesWithoutUndo();
            UnityEngine.Rendering.GraphicsSettings.defaultRenderPipeline = urp;
            // Renderer features: screen-space ambient occlusion and decals (puddles, cracks, grime).
            var rendererData = AssetDatabase.LoadAssetAtPath<UniversalRendererData>(rendererPath);
            if (rendererData != null)
            {
                var ssao = AddFeature<ScreenSpaceAmbientOcclusion>(rendererData, "SSAO");
                var sso = new SerializedObject(ssao);
                void S(string p, System.Action<SerializedProperty> f) { var sp = sso.FindProperty("m_Settings." + p); if (sp != null) f(sp); else Debug.LogWarning("[setup] SSAO field missing: " + p); }
                // Normals-based AO on ambient light only: depth-only AO applied after opaques left blotches on faces.
                S("Source", sp => sp.intValue = 1);   // DepthNormals
                S("Intensity", sp => sp.floatValue = 0.85f);
                S("DirectLightingStrength", sp => sp.floatValue = 0.3f);
                S("Radius", sp => sp.floatValue = 0.25f);
                S("Falloff", sp => sp.floatValue = 45f);
                S("Downsample", sp => sp.boolValue = false);
                S("AfterOpaque", sp => sp.boolValue = false);
                sso.ApplyModifiedPropertiesWithoutUndo();
                var decals = AddFeature<DecalRendererFeature>(rendererData, "Decals");
                var dso = new SerializedObject(decals);
                var tech = dso.FindProperty("m_Settings.technique");
                if (tech != null) tech.intValue = 2;           // screen space (works on WebGL and desktop)
                var dist = dso.FindProperty("m_Settings.maxDrawDistance");
                if (dist != null) dist.floatValue = 80f;
                dso.ApplyModifiedPropertiesWithoutUndo();
                EditorUtility.SetDirty(rendererData);
            }
            // Every quality level uses the default pipeline asset (runtime settings tweak it).
            var qs = new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/QualitySettings.asset")[0]);
            var levels = qs.FindProperty("m_QualitySettings");
            for (var i = 0; i < levels.arraySize; i++)
            {
                var lv = levels.GetArrayElementAtIndex(i);
                var rp = lv.FindPropertyRelative("customRenderPipeline");
                if (rp != null) rp.objectReferenceValue = null;
                var lodBias = lv.FindPropertyRelative("lodBias");
                if (lodBias != null && lodBias.floatValue < 1f) lodBias.floatValue = 1f;
            }
            qs.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(urp);
        }

        static T AddFeature<T>(UniversalRendererData data, string name) where T : ScriptableRendererFeature
        {
            var existing = data.rendererFeatures.OfType<T>().FirstOrDefault();
            if (existing != null) return existing;
            var f = ScriptableObject.CreateInstance<T>();
            f.name = name;
            AssetDatabase.AddObjectToAsset(f, data);
            data.rendererFeatures.Add(f);
            // Keep the serialized feature map in sync (what the renderer inspector does when adding a feature).
            typeof(ScriptableRendererData).GetMethod("UpdateMap", BindingFlags.NonPublic | BindingFlags.Instance)?.Invoke(data, null);
            EditorUtility.SetDirty(data);
            AssetDatabase.SaveAssets();
            return f;
        }

        // ------------------------------------------------------------------ player

        static void SetupPlayer()
        {
            PlayerSettings.companyName = "EchoesOfAether";
            PlayerSettings.productName = "Echoes of Aether";
            PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.runInBackground = true;
            PlayerSettings.bakeCollisionMeshes = true;
            PlayerSettings.defaultScreenWidth = 1920;
            PlayerSettings.defaultScreenHeight = 1080;
            PlayerSettings.defaultWebScreenWidth = 1280;   // 16:9 page (the UI is designed for 16:9)
            PlayerSettings.defaultWebScreenHeight = 720;
            PlayerSettings.fullScreenMode = FullScreenMode.FullScreenWindow;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.visibleInBackground = true;
            PlayerSettings.SetManagedStrippingLevel(NamedBuildTarget.WebGL, ManagedStrippingLevel.Minimal);
            PlayerSettings.SetManagedStrippingLevel(NamedBuildTarget.Standalone, ManagedStrippingLevel.Minimal);
            PlayerSettings.SetScriptingBackend(NamedBuildTarget.Standalone, ScriptingImplementation.Mono2x);
            PlayerSettings.WebGL.compressionFormat = WebGLCompressionFormat.Brotli;
            PlayerSettings.WebGL.decompressionFallback = true;   // itch.io does not send Content-Encoding headers
            PlayerSettings.WebGL.dataCaching = true;
            PlayerSettings.WebGL.exceptionSupport = WebGLExceptionSupport.ExplicitlyThrownExceptionsOnly;
            PlayerSettings.WebGL.nameFilesAsHashes = false;
            PlayerSettings.WebGL.showDiagnostics = false;
            // Input System + legacy (both) so package samples/debug UIs keep working.
            var ps = new SerializedObject(AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/ProjectSettings.asset")[0]);
            var input = ps.FindProperty("activeInputHandler");
            if (input != null && input.intValue == 0) input.intValue = 2;
            ps.ApplyModifiedPropertiesWithoutUndo();
            // IL2CPP/WebGL code stripping: keep reflection-driven JSON types.
            const string linkXml = "Assets/link.xml";
            if (!File.Exists(linkXml))
            {
                File.WriteAllText(linkXml,
                    "<linker>\n" +
                    "  <!-- Game data is deserialised with Newtonsoft via reflection. -->\n" +
                    "  <assembly fullname=\"Assembly-CSharp\" preserve=\"all\"/>\n" +
                    "  <assembly fullname=\"Newtonsoft.Json\" preserve=\"all\"/>\n" +
                    "  <assembly fullname=\"Unity.AI.Navigation\" preserve=\"all\"/>\n" +
                    "</linker>\n");
                AssetDatabase.ImportAsset(linkXml);
            }
        }

        // ------------------------------------------------------------------ materials that keep shaders/variants in builds

        static void SaveMat(Material m, string path)
        {
            EnvLibraryBuilder.EnsureFolder(Path.GetDirectoryName(path).Replace('\\', '/'));
            var existing = AssetDatabase.LoadAssetAtPath<Material>(path);
            if (existing != null) AssetDatabase.DeleteAsset(path);
            AssetDatabase.CreateAsset(m, path);
        }

        static void SetupTemplates()
        {
            // FxMaterials clones these when present (Resources/VFX/*); a material per keyword set also keeps the
            // variants that runtime code enables (emission, transparency) from being stripped.
            SaveMat(Fresh(FxMaterials.Particle(true, null)), "Assets/Resources/VFX/Particle_Additive.mat");
            SaveMat(Fresh(FxMaterials.Particle(false, null)), "Assets/Resources/VFX/Particle_Alpha.mat");
            SaveMat(Fresh(FxMaterials.Lit(Color.white, 0f, 0.5f, "Lit")), "Assets/Resources/VFX/Lit.mat");
            SaveMat(Fresh(FxMaterials.Unlit(Color.white, "Unlit")), "Assets/Resources/VFX/Unlit.mat");
            var litT = Fresh(FxMaterials.Lit(Color.white, 0f, 0.5f, "Lit_TransparentVariant"));
            FxMaterials.SetTransparent(litT, true);
            SaveMat(litT, "Assets/Resources/VFX/Variants/Lit_TransparentVariant.mat");
            var litTA = Fresh(FxMaterials.Lit(Color.white, 0f, 0.5f, "Lit_TransparentAdditiveVariant"));
            FxMaterials.SetTransparent(litTA, true, true);
            SaveMat(litTA, "Assets/Resources/VFX/Variants/Lit_TransparentAdditiveVariant.mat");
            var unlitT = Fresh(FxMaterials.Unlit(Color.white, "Unlit_TransparentVariant"));
            FxMaterials.SetTransparent(unlitT, true, true);
            SaveMat(unlitT, "Assets/Resources/VFX/Variants/Unlit_TransparentVariant.mat");
            var sky = Shader.Find("EOA/Sky");
            if (sky != null) SaveMat(new Material(sky) { name = "Sky" }, "Assets/Resources/Env/Sky.mat");
            else Debug.LogError("[setup] EOA/Sky shader failed to compile");
            foreach (var (shader, file) in new[] { ("EOA/Hologram", "Hologram"), ("EOA/CityLights", "CityLights"), ("EOA/Skin", "Skin") })
            {
                var sh = Shader.Find(shader);
                if (sh != null && sh.isSupported) SaveMat(new Material(sh) { name = file }, "Assets/Resources/Env/" + file + ".mat");
                else Debug.LogError($"[setup] {shader} shader failed to compile");
            }
            var text = Shader.Find("EOA/WorldText");
            if (text != null) SaveMat(new Material(text) { name = "WorldText" }, "Assets/Resources/Env/WorldText.mat");
            else Debug.LogError("[setup] EOA/WorldText shader failed to compile");
            var aether = Shader.Find("EOA/Aether");
            if (aether != null) SaveMat(new Material(aether) { name = "Aether" }, "Assets/Resources/Env/Aether.mat");
            else Debug.LogError("[setup] EOA/Aether shader failed to compile");
        }

        /// <summary>Copy of a runtime material that is safe to save (no references to non-asset textures).</summary>
        static Material Fresh(Material m)
        {
            var c = new Material(m) { name = m.name };
            foreach (var prop in c.GetTexturePropertyNames())
            {
                var t = c.GetTexture(prop);
                if (t != null && !AssetDatabase.Contains(t)) c.SetTexture(prop, null);
            }
            return c;
        }

        static void SetupRobotMaterial()
        {
            const string dir = "Assets/Resources/Models/Robots/Textures/";
            var baseTex = dir + "robot_worn_metal_BaseColor.png";
            var nrm = dir + "robot_worn_metal_Normal.png";
            var ms = dir + "robot_worn_metal_MetallicSmoothness.png";
            if (!File.Exists(baseTex)) { Debug.LogWarning("[setup] robot textures missing; robots stay untextured"); return; }
            if (AssetImporter.GetAtPath(nrm) is TextureImporter ni) { ni.textureType = TextureImporterType.NormalMap; ni.maxTextureSize = 1024; ni.SaveAndReimport(); }
            if (AssetImporter.GetAtPath(ms) is TextureImporter mi) { mi.sRGBTexture = false; mi.alphaSource = TextureImporterAlphaSource.FromInput; mi.maxTextureSize = 1024; mi.SaveAndReimport(); }
            if (AssetImporter.GetAtPath(baseTex) is TextureImporter bi) { bi.maxTextureSize = 1024; bi.SaveAndReimport(); }
            var m = new Material(Shader.Find("Universal Render Pipeline/Lit")) { name = "robot_metal" };
            m.SetTexture("_BaseMap", AssetDatabase.LoadAssetAtPath<Texture2D>(baseTex));
            m.SetTextureScale("_BaseMap", new Vector2(2.5f, 2.5f));
            m.SetTexture("_BumpMap", AssetDatabase.LoadAssetAtPath<Texture2D>(nrm));
            m.EnableKeyword("_NORMALMAP");
            m.SetTexture("_MetallicGlossMap", AssetDatabase.LoadAssetAtPath<Texture2D>(ms));
            m.EnableKeyword("_METALLICSPECGLOSSMAP");
            m.SetFloat("_Metallic", 1f);
            m.SetFloat("_Smoothness", 1f);
            m.EnableKeyword("_EMISSION");
            m.SetColor("_EmissionColor", Color.black);
            m.globalIlluminationFlags = MaterialGlobalIlluminationFlags.None;
            SaveMat(m, "Assets/Resources/Models/Robots/robot_metal.mat");
            // Variant used while a stalker phases (transparent + textured).
            var t = new Material(m) { name = "robot_metal_TransparentVariant" };
            FxMaterials.SetTransparent(t, true);
            SaveMat(t, "Assets/Resources/VFX/Variants/robot_metal_TransparentVariant.mat");
            // Robot FBX: rigid parts, no animation import, keep names.
            foreach (var f in Directory.GetFiles("Assets/Resources/Models/Robots", "*.fbx"))
            {
                if (AssetImporter.GetAtPath(f.Replace('\\', '/')) is not ModelImporter r) continue;
                r.animationType = ModelImporterAnimationType.None;
                r.importAnimation = false;
                r.importCameras = false;
                r.importLights = false;
                r.materialImportMode = ModelImporterMaterialImportMode.ImportStandard;
                r.SaveAndReimport();
            }
        }

        // ------------------------------------------------------------------ boot scene & build settings

        static void SetupBootScene()
        {
            EnvLibraryBuilder.EnsureFolder("Assets/Scenes");
            Scene scene;
            if (File.Exists(BootScene)) scene = EditorSceneManager.OpenScene(BootScene, OpenSceneMode.Single);
            else
            {
                scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                var go = new GameObject("GameManager");
                go.AddComponent<GameManager>();
            }
            if (UnityEngine.Object.FindAnyObjectByType<GameManager>() == null) new GameObject("GameManager").AddComponent<GameManager>();
            // Fully realtime lighting: zones configure sky/fog/ambient at runtime.
            var lighting = new LightingSettings { name = "EOA_Lighting", bakedGI = false, realtimeGI = false, autoGenerate = false };
            var lightingPath = SettingsDir + "/EOA_Lighting.lighting";
            EnvLibraryBuilder.EnsureFolder(SettingsDir);
            if (AssetDatabase.LoadAssetAtPath<LightingSettings>(lightingPath) == null) AssetDatabase.CreateAsset(lighting, lightingPath);
            Lightmapping.SetLightingSettingsForScene(scene, AssetDatabase.LoadAssetAtPath<LightingSettings>(lightingPath));
            RenderSettings.skybox = AssetDatabase.LoadAssetAtPath<Material>("Assets/Resources/Env/Sky.mat");
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = new Color(0.16f, 0.2f, 0.26f);
            RenderSettings.ambientEquatorColor = new Color(0.1f, 0.12f, 0.15f);
            RenderSettings.ambientGroundColor = new Color(0.04f, 0.045f, 0.05f);
            EditorSceneManager.MarkSceneDirty(scene);
            EditorSceneManager.SaveScene(scene, BootScene);
            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(BootScene, true) };
        }
    }
}
