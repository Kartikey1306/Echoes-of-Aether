// Hero eyes (URP, both heroes): the eyeball texture uses the centred-iris layout (iris where
// sqrt(4 du^2 + dv^2) < 0.085, v up; CharacterModel.ApplyEyes tints the iris into _BaseMap at runtime).
//   * iris parallax under the cornea (the iris sits deeper than the cornea: it no longer looks painted on);
//   * a darker limbal ring at the iris edge;
//   * wet cornea: sharp GGX highlight from the scene lights plus a small studio catchlight that stays in view, dim
//     environment reflection (bright skies used to wash the iris out);
//   * upper-lid shadow and corner occlusion so the eyeball sits inside the lids instead of being stuck on;
//   * soft wrapped diffuse on the sclera.
// SRP-Batcher compatible: URP Lit inputs, spare members reused:
//   _Parallax = iris depth, _ClearCoatMask = limbal ring darkness, _ClearCoatSmoothness = upper-lid shadow,
//   _DetailAlbedoMapScale = catchlight strength, _OcclusionStrength = environment reflection, _Smoothness = cornea.
Shader "EOA/Eye"
{
    Properties
    {
        [MainTexture] _BaseMap("Eyeball (centred iris)", 2D) = "white" {}
        [MainColor] _BaseColor("Color", Color) = (1,1,1,1)
        _Cutoff("Alpha Cutoff", Range(0.0, 1.0)) = 0.5
        _Smoothness("Cornea Smoothness", Range(0.0, 1.0)) = 0.93
        _Metallic("Metallic", Range(0.0, 1.0)) = 0.0
        _Parallax("Iris Depth", Range(0.0, 0.05)) = 0.014
        _ClearCoatMask("Limbal Ring", Range(0, 1)) = 0.55
        _ClearCoatSmoothness("Upper Lid Shadow", Range(0, 1)) = 0.5
        _DetailAlbedoMapScale("Catchlight", Range(0.0, 2.0)) = 0.9
        _OcclusionStrength("Environment Reflection", Range(0.0, 1.0)) = 0.18
        _SpecColor("Specular", Color) = (0.2, 0.2, 0.2)
        [HDR] _EmissionColor("Color", Color) = (0,0,0)
        _BumpScale("Scale", Float) = 1.0
        _DetailNormalMapScale("Scale", Range(0.0, 2.0)) = 1.0
        _Surface("__surface", Float) = 0.0
        _Cull("__cull", Float) = 2.0
        [HideInInspector] _EnvironmentReflections("Environment Reflections", Float) = 1.0
    }

    SubShader
    {
        Tags { "RenderType"="Opaque" "RenderPipeline"="UniversalPipeline" "UniversalMaterialType"="Lit" "IgnoreProjector"="True" }
        LOD 300

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode"="UniversalForward" }
            Cull[_Cull]

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex LitPassVertex
            #pragma fragment EyeFragment
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile _ EVALUATE_SH_MIXED EVALUATE_SH_VERTEX
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BLENDING
            #pragma multi_compile_fragment _ _REFLECTION_PROBE_BOX_PROJECTION
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _SCREEN_SPACE_OCCLUSION
            #pragma multi_compile_fragment _ _LIGHT_COOKIES
            #pragma multi_compile _ _LIGHT_LAYERS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/ProbeVolumeVariants.hlsl"
            #pragma multi_compile_instancing

            #define REQUIRES_WORLD_SPACE_TANGENT_INTERPOLATOR
            #include "Packages/com.unity.render-pipelines.universal/Shaders/LitInput.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/LitForwardPass.hlsl"

            half IrisDistance(float2 uv)
            {
                float2 d = uv - 0.5;
                return sqrt(4.0 * d.x * d.x + d.y * d.y);
            }

            half3 EyeLight(BRDFData brdf, Light light, half3 N, half3 V, half occl)
            {
                half3 L = light.direction;
                half3 radiance = light.color * light.distanceAttenuation * light.shadowAttenuation;
                half ndl = dot(N, L);
                half diff = saturate((ndl + 0.35h) / 1.35h);                         // sclera scatters a little
                half3 spec = brdf.specular * DirectBRDFSpecular(brdf, N, L, V) * saturate(ndl);
                return radiance * (brdf.diffuse * diff * occl + spec);
            }

            void EyeFragment(Varyings input, out half4 outColor : SV_Target0
            #ifdef _WRITE_RENDERING_LAYERS
                , out uint outRenderingLayers : SV_Target1
            #endif
            )
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);
                float2 uv = input.uv;
                half3 N = normalize(input.normalWS);
                half3 T = normalize(input.tangentWS.xyz);
                half3 B = cross(N, T) * input.tangentWS.w;
                half3 V = GetWorldSpaceNormalizeViewDir(input.positionWS);

                // iris parallax: the iris plane sits _Parallax (UV units) below the cornea
                half d0 = IrisDistance(uv);
                half irisMask = 1.0h - smoothstep(0.08h, 0.1h, d0);
                half3 vts = half3(dot(V, T), dot(V, B), dot(V, N));
                float2 off = -vts.xy / max(vts.z, 0.3h) * _Parallax;
                off.x *= 0.5;                                                 // u is squeezed 2x in this layout
                float2 uvI = lerp(uv, uv + off, irisMask);
                half4 tex = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uvI);
                half3 albedo = tex.rgb * _BaseColor.rgb;
                // limbal ring: the iris edge darkens into the sclera
                half dI = IrisDistance(uvI);
                albedo *= 1.0h - _ClearCoatMask * exp(-pow((dI - 0.084h) / 0.0085h, 2.0h));
                // the eyeball sits inside the lids: upper-lid shadow, darker corners
                half dv = uv.y - 0.5h;
                half occl = (1.0h - _ClearCoatSmoothness * smoothstep(0.0h, 0.15h, dv)) * (1.0h - 0.3h * smoothstep(0.16h, 0.3h, abs(uv.x - 0.5h) * 2.0h));

                SurfaceData s = (SurfaceData)0;
                s.albedo = albedo;
                s.metallic = 0;
                s.specular = 0;
                s.smoothness = _Smoothness;
                s.occlusion = occl;
                s.alpha = 1;
                InputData inputData;
                InitializeInputData(input, half3(0, 0, 1), inputData);
                InitializeBakedGIData(input, inputData);
                BRDFData brdf;
                InitializeBRDFData(s, brdf);
                half4 shadowMask = CalculateShadowMask(inputData);
                AmbientOcclusionFactor aoFactor = CreateAmbientOcclusionFactor(inputData.normalizedScreenSpaceUV, occl);
                uint meshRenderingLayers = GetMeshRenderingLayer();
                Light mainLight = GetMainLight(inputData, shadowMask, aoFactor);

                half3 color = inputData.bakedGI * brdf.diffuse * occl;
                // wet cornea: dim environment reflection + fresnel
                half3 R = reflect(-V, N);
                half fres = 0.04h + 0.96h * pow(1.0h - saturate(dot(N, V)), 5.0h);
                color += GlossyEnvironmentReflection(R, inputData.positionWS, brdf.perceptualRoughness, 1.0h, inputData.normalizedScreenSpaceUV)
                         * fres * _OcclusionStrength * occl;
            #ifdef _LIGHT_LAYERS
                if (IsMatchingLightLayer(mainLight.layerMask, meshRenderingLayers))
            #endif
                    color += EyeLight(brdf, mainLight, N, V, occl);
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
                        color += EyeLight(brdf, light, N, V, occl);
                }
            #endif
                LIGHT_LOOP_BEGIN(pixelLightCount)
                    Light light = GetAdditionalLight(lightIndex, inputData, shadowMask, aoFactor);
            #ifdef _LIGHT_LAYERS
                    if (IsMatchingLightLayer(light.layerMask, meshRenderingLayers))
            #endif
                        color += EyeLight(brdf, light, N, V, occl);
                LIGHT_LOOP_END
            #endif
                // studio catchlight: a small soft box up and to the side of the camera, always reflected by the cornea
                half3 camRight = UNITY_MATRIX_V[0].xyz;
                half3 camUp = UNITY_MATRIX_V[1].xyz;
                half3 box = normalize(V + camUp * 0.38h + camRight * 0.22h);
                half catchl = pow(saturate(dot(R, box)), 900.0h) + 0.25h * pow(saturate(dot(R, box)), 120.0h);
                color += catchl * _DetailAlbedoMapScale * smoothstep(0.0h, 0.2h, dot(N, V)) * (0.4h + 0.6h * occl);
                color = MixFog(color, inputData.fogCoord);
                outColor = half4(color, 1);
            #ifdef _WRITE_RENDERING_LAYERS
                outRenderingLayers = EncodeMeshRenderingLayer();
            #endif
            }
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
            #pragma multi_compile_instancing
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
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/Shaders/LitInput.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/Shaders/LitDepthNormalsPass.hlsl"
            ENDHLSL
        }
    }
    FallBack "Universal Render Pipeline/Lit"
}
