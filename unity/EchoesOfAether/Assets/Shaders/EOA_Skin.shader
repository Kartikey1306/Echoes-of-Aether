// Character skin for URP (both heroes; owned by the character-shading pass):
//   * soft-skin diffuse: the diffuse term sees a blurrier normal than the specular one, per colour channel (red light
//     travels furthest in skin), and wraps past the terminator per channel -> a soft red-tinted terminator instead of a
//     plastic hard edge or an orange cast;
//   * GGX specular from the roughness (mask map A) on the fully detailed normal (main normal map + tiled pore detail),
//     environment reflection kept dim (no plastic sheen);
//   * thin-area transmission (ears, nose wings, jaw silhouettes) for back light;
//   * tiled pore detail normal map for close-ups (mip-faded at distance).
// Uses URP Lit's inputs, so every Lit property/texture/keyword still works (CharacterModel tints _BaseColor, sets the
// tattoo detail albedo / emission). To stay SRP-Batcher compatible it reuses spare Lit CBUFFER members:
//   _SpecColor           = subsurface tint (light colour that survives deep scattering: red)
//   _ClearCoatMask       = subsurface strength (0..1)
//   _ClearCoatSmoothness = wrap amount (0..1)
//   _ParallaxMap         = pore detail normal map (tangent space, tiled; the Lit parallax keyword is never used)
//   _Parallax            = pore detail tiling (repeats over the 0..1 UV square)
//   _DetailNormalMapScale= pore detail strength (the Lit detail normal slot itself stays unassigned)
Shader "EOA/Skin"
{
    Properties
    {
        [MainTexture] _BaseMap("Albedo", 2D) = "white" {}
        [MainColor] _BaseColor("Color", Color) = (1,1,1,1)
        _Cutoff("Alpha Cutoff", Range(0.0, 1.0)) = 0.5
        _Smoothness("Smoothness", Range(0.0, 1.0)) = 0.42
        _GlossMapScale("Smoothness Scale", Range(0.0, 1.0)) = 1.0
        _SmoothnessTextureChannel("Smoothness texture channel", Float) = 0
        _Metallic("Metallic", Range(0.0, 1.0)) = 0.0
        _MetallicGlossMap("Metallic", 2D) = "white" {}
        _SpecColor("Subsurface Tint", Color) = (0.9, 0.32, 0.26)
        _SpecGlossMap("Specular", 2D) = "white" {}
        [ToggleOff] _SpecularHighlights("Specular Highlights", Float) = 1.0
        [ToggleOff] _EnvironmentReflections("Environment Reflections", Float) = 1.0
        _BumpScale("Scale", Float) = 1.0
        _BumpMap("Normal Map", 2D) = "bump" {}
        _Parallax("Pore Tiling", Float) = 48.0
        [Normal] _ParallaxMap("Pore Detail Normal", 2D) = "bump" {}
        _OcclusionStrength("Strength", Range(0.0, 1.0)) = 1.0
        _OcclusionMap("Occlusion", 2D) = "white" {}
        [HDR] _EmissionColor("Color", Color) = (0,0,0)
        _EmissionMap("Emission", 2D) = "white" {}
        _DetailMask("Detail Mask", 2D) = "white" {}
        _DetailAlbedoMapScale("Scale", Range(0.0, 2.0)) = 1.0
        _DetailAlbedoMap("Detail Albedo x2", 2D) = "linearGrey" {}
        _DetailNormalMapScale("Pore Strength", Range(0.0, 2.0)) = 0.6
        [Normal] _DetailNormalMap("Normal Map", 2D) = "bump" {}
        _ClearCoatMask("Subsurface Strength", Range(0, 1)) = 0.7
        _ClearCoatSmoothness("Subsurface Wrap", Range(0, 1)) = 0.55
        _Surface("__surface", Float) = 0.0
        _Blend("__blend", Float) = 0.0
        _Cull("__cull", Float) = 2.0
        [ToggleUI] _AlphaClip("__clip", Float) = 0.0
        [HideInInspector] _SrcBlend("__src", Float) = 1.0
        [HideInInspector] _DstBlend("__dst", Float) = 0.0
        [HideInInspector] _SrcBlendAlpha("__srcA", Float) = 1.0
        [HideInInspector] _DstBlendAlpha("__dstA", Float) = 0.0
        [HideInInspector] _ZWrite("__zw", Float) = 1.0
        [HideInInspector] _BlendModePreserveSpecular("_BlendModePreserveSpecular", Float) = 1.0
        [HideInInspector] _AlphaToMask("__alphaToMask", Float) = 0.0
        [HideInInspector] _QueueOffset("Queue offset", Float) = 0.0
        [HideInInspector] _MainTex("BaseMap", 2D) = "white" {}
        [HideInInspector] _Color("Base Color", Color) = (1, 1, 1, 1)
        [HideInInspector] _Glossiness("Smoothness", Float) = 0.0
        [HideInInspector] _GlossyReflections("EnvironmentReflections", Float) = 0.0
    }

    SubShader
    {
        Tags { "RenderType"="Opaque" "RenderPipeline"="UniversalPipeline" "UniversalMaterialType"="Lit" "IgnoreProjector"="True" }
        LOD 300

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode"="UniversalForward" }
            Blend[_SrcBlend][_DstBlend], [_SrcBlendAlpha][_DstBlendAlpha]
            ZWrite[_ZWrite]
            Cull[_Cull]

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex LitPassVertex
            #pragma fragment SkinPassFragment

            #pragma shader_feature_local _NORMALMAP
            #pragma shader_feature_local _ _DETAIL_MULX2 _DETAIL_SCALED
            #pragma shader_feature_local _RECEIVE_SHADOWS_OFF
            #pragma shader_feature_local_fragment _ALPHATEST_ON
            #pragma shader_feature_local_fragment _EMISSION
            #pragma shader_feature_local_fragment _METALLICSPECGLOSSMAP
            #pragma shader_feature_local_fragment _SMOOTHNESS_TEXTURE_ALBEDO_CHANNEL_A
            #pragma shader_feature_local_fragment _OCCLUSIONMAP

            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ EVALUATE_SH_MIXED EVALUATE_SH_VERTEX
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BLENDING
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BOX_PROJECTION
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_ATLAS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _SCREEN_SPACE_OCCLUSION
            #pragma multi_compile_fragment _ _DBUFFER_MRT1 _DBUFFER_MRT2 _DBUFFER_MRT3
            #pragma multi_compile_fragment _ _LIGHT_COOKIES
            #pragma multi_compile _ _LIGHT_LAYERS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"
            #pragma multi_compile _ LOD_FADE_CROSSFADE
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/ProbeVolumeVariants.hlsl"
            #pragma multi_compile_instancing
            #pragma instancing_options renderinglayer
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"

            #include "Packages/com.unity.render-pipelines.universal/Shaders/LitInput.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/LitForwardPass.hlsl"

            // Per-channel soft diffuse + GGX specular + thin-area transmission for one light.
            //   Ns: fully detailed normal (normal map + pores), Ng: interpolated vertex normal.
            half3 SkinLight(BRDFData brdf, Light light, half3 Ns, half3 Ng, half3 V)
            {
                half3 L = light.direction;
                half shadow = light.shadowAttenuation;
                half3 radiance = light.color * light.distanceAttenuation;
                // diffuse: red sees the blurriest normal and wraps furthest past the terminator (deep scattering)
                half ndlS = dot(Ns, L);
                half ndlG = dot(Ng, L);
                half3 detail = half3(0.42h, 0.8h, 0.92h);               // share of the detailed normal per channel
                half3 ndl = lerp(ndlG.xxx, ndlS.xxx, detail);
                half3 w = _ClearCoatSmoothness * _ClearCoatMask * saturate(_SpecColor.rgb * 1.15h);
                half3 diff = saturate((ndl + w) / (1.0h + w));
                diff = lerp(diff, diff * diff * (3.0h - 2.0h * diff), 0.35h); // soften the wrapped ramp
                // shadow edges bleed a little red
                half3 sh = lerp(shadow.xxx, sqrt(max(shadow, 0.0h)).xxx, w * 1.4h);
                half3 diffuse = brdf.diffuse * diff * sh;
                // specular on the detailed normal
                half nl = saturate(ndlS);
                half3 specular = 0;
            #ifndef _SPECULARHIGHLIGHTS_OFF
                specular = brdf.specular * DirectBRDFSpecular(brdf, Ns, L, V) * nl * shadow;
            #endif
                // transmission where the skin is thin as seen from the camera (ears, nose, jaw silhouettes): a light
                // behind the head (the camera rim light) must not flood a camera-facing face red
                half3 Hs = normalize(L + Ng * 0.35h);
                half edge = 1.0h - saturate(dot(Ng, V));
                half back = pow(saturate(dot(V, -Hs)), 3.0h) * 0.25h * edge * edge * _ClearCoatMask;   // a back/rim light must not paint a red rim
                half3 trans = brdf.diffuse * _SpecColor.rgb * back * lerp(1.0h, shadow, 0.6h);
                return radiance * (diffuse + specular + trans);
            }

            void SkinPassFragment(Varyings input, out half4 outColor : SV_Target0
            #ifdef _WRITE_RENDERING_LAYERS
                , out uint outRenderingLayers : SV_Target1
            #endif
            )
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);

                SurfaceData surfaceData;
                InitializeStandardLitSurfaceData(input.uv, surfaceData);
            #ifdef LOD_FADE_CROSSFADE
                LODFadeCrossFade(input.positionCS);
            #endif
            #if defined(_NORMALMAP)
                // tiled pore detail (mips fade it out with distance: no speckle on screen-sized pores)
                half3 pore = UnpackNormalScale(SAMPLE_TEXTURE2D(_ParallaxMap, sampler_ParallaxMap, input.uv * _Parallax), _DetailNormalMapScale);
                surfaceData.normalTS = normalize(BlendNormalRNM(surfaceData.normalTS, pore));
            #endif
                // no plastic sheen: skin never gets glossier than a damp T-zone
                surfaceData.smoothness = min(surfaceData.smoothness, 0.62h);
                InputData inputData;
                InitializeInputData(input, surfaceData.normalTS, inputData);
            #if defined(_DBUFFER)
                ApplyDecalToSurfaceData(input.positionCS, surfaceData, inputData);
            #endif
                InitializeBakedGIData(input, inputData);

                BRDFData brdfData;
                InitializeBRDFData(surfaceData, brdfData);
                half4 shadowMask = CalculateShadowMask(inputData);
                AmbientOcclusionFactor aoFactor = CreateAmbientOcclusionFactor(inputData, surfaceData);
                uint meshRenderingLayers = GetMeshRenderingLayer();
                Light mainLight = GetMainLight(inputData, shadowMask, aoFactor);
                MixRealtimeAndBakedGI(mainLight, inputData.normalWS, inputData.bakedGI);

                half3 Ns = inputData.normalWS;
                half3 Ng = normalize(input.normalWS);
                half3 V = inputData.viewDirectionWS;

                // indirect: soft-normal ambient diffuse, dimmed environment specular (skin is not a mirror)
                BRDFData noClearCoat = (BRDFData)0;
                half3 gi = GlobalIllumination(brdfData, noClearCoat, 0.0, inputData.bakedGI, aoFactor.indirectAmbientOcclusion,
                                              inputData.positionWS, normalize(lerp(Ng, Ns, 0.6h)), V, inputData.normalizedScreenSpaceUV);
                half3 color = gi;
            #ifdef _LIGHT_LAYERS
                if (IsMatchingLightLayer(mainLight.layerMask, meshRenderingLayers))
            #endif
                    color += SkinLight(brdfData, mainLight, Ns, Ng, V);
            #if defined(_ADDITIONAL_LIGHTS)
                uint pixelLightCount = GetAdditionalLightsCount();
            #if USE_CLUSTER_LIGHT_LOOP
                [loop] for (uint lightIndex = 0; lightIndex < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS); lightIndex++)
                {
                    CLUSTER_LIGHT_LOOP_SUBTRACTIVE_LIGHT_CHECK
                    Light light = GetAdditionalLight(lightIndex, inputData, shadowMask, aoFactor);
            #ifdef _LIGHT_LAYERS
                    if (IsMatchingLightLayer(light.layerMask, meshRenderingLayers))
            #endif
                        color += SkinLight(brdfData, light, Ns, Ng, V);
                }
            #endif
                LIGHT_LOOP_BEGIN(pixelLightCount)
                    Light light = GetAdditionalLight(lightIndex, inputData, shadowMask, aoFactor);
            #ifdef _LIGHT_LAYERS
                    if (IsMatchingLightLayer(light.layerMask, meshRenderingLayers))
            #endif
                        color += SkinLight(brdfData, light, Ns, Ng, V);
                LIGHT_LOOP_END
            #endif
            #if defined(_ADDITIONAL_LIGHTS_VERTEX)
                color += inputData.vertexLighting * brdfData.diffuse;
            #endif
                color += surfaceData.emission;
                color = MixFog(color, inputData.fogCoord);
                outColor = half4(color, OutputAlpha(surfaceData.alpha, IsSurfaceTypeTransparent(_Surface)));
            #ifdef _WRITE_RENDERING_LAYERS
                outRenderingLayers = EncodeMeshRenderingLayer();
            #endif
            }
            ENDHLSL
        }

        Pass
        {
            Name "ShadowCaster"
            Tags { "LightMode"="ShadowCaster" }
            ZWrite On
            ZTest LEqual
            ColorMask 0
            Cull[_Cull]

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex ShadowPassVertex
            #pragma fragment ShadowPassFragment
            #pragma shader_feature_local _ALPHATEST_ON
            #pragma shader_feature_local_fragment _SMOOTHNESS_TEXTURE_ALBEDO_CHANNEL_A
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"
            #pragma multi_compile _ LOD_FADE_CROSSFADE
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #include "Packages/com.unity.render-pipelines.universal/Shaders/LitInput.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/ShadowCasterPass.hlsl"
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode"="DepthOnly" }
            ZWrite On
            ColorMask R
            Cull[_Cull]

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex DepthOnlyVertex
            #pragma fragment DepthOnlyFragment
            #pragma shader_feature_local _ALPHATEST_ON
            #pragma shader_feature_local_fragment _SMOOTHNESS_TEXTURE_ALBEDO_CHANNEL_A
            #pragma multi_compile _ LOD_FADE_CROSSFADE
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/LitInput.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/DepthOnlyPass.hlsl"
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode"="DepthNormals" }
            ZWrite On
            Cull[_Cull]

            HLSLPROGRAM
            #pragma target 2.0
            #pragma vertex DepthNormalsVertex
            #pragma fragment DepthNormalsFragment
            #pragma shader_feature_local _NORMALMAP
            #pragma shader_feature_local _ALPHATEST_ON
            #pragma shader_feature_local_fragment _SMOOTHNESS_TEXTURE_ALBEDO_CHANNEL_A
            #pragma multi_compile _ LOD_FADE_CROSSFADE
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"
            #pragma multi_compile_instancing
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DOTS.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/LitInput.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/LitDepthNormalsPass.hlsl"
            ENDHLSL
        }
    }
    FallBack "Universal Render Pipeline/Lit"
}
