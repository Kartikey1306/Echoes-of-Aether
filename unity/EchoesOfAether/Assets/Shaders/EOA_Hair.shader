// Hero hair / brows / lashes / facial hair cards (URP, both heroes):
//   * alpha test with a narrow screen-space dither band around the cutoff: TAA (High) resolves it into soft strand
//     edges, FXAA (Low) still sees thin strands instead of hard card edges; the same clip runs in every depth/shadow
//     pass so depth priming never punches holes;
//   * Kajiya-Kay dual anisotropic highlight along the strand (card UV v runs root -> tip, i.e. the mesh bitangent):
//     a light-coloured primary shifted towards the root and a hair-tinted secondary shifted towards the tip,
//     broken up by the strand texture;
//   * wrapped diffuse (hair scatters light), optional per-vertex strand data (_STRAND_DATA: second UV set, x = root (0)
//     -> tip (1), y = depth/occlusion inside the hair mass) for root darkening and inner-layer occlusion;
//   * double sided with the shading normal flipped on back faces.
// Runtime contract kept: _BaseMap (grey strand texture), _BaseColor (hair tint), _Cutoff, _Cull, _Smoothness.
Shader "EOA/Hair"
{
    Properties
    {
        [MainTexture] _BaseMap("Strands (grey, A = coverage)", 2D) = "white" {}
        [MainColor] _BaseColor("Tint", Color) = (0.3, 0.22, 0.17, 1)
        _Cutoff("Alpha Cutoff", Range(0.0, 1.0)) = 0.4
        _DitherWidth("Edge Dither Width", Range(0.0, 0.4)) = 0.14
        _Smoothness("Smoothness", Range(0.0, 1.0)) = 0.55
        _SpecStrength("Primary Highlight", Range(0.0, 2.0)) = 0.1
        _Spec2Strength("Secondary Highlight", Range(0.0, 2.0)) = 0.4
        _SpecShift("Primary Shift", Range(-0.5, 0.5)) = 0.1
        _Spec2Shift("Secondary Shift", Range(-0.5, 0.5)) = -0.12
        _Wrap("Diffuse Wrap", Range(0.0, 1.0)) = 0.4
        _RootDark("Root Darkening", Range(0.0, 1.0)) = 0.45
        _InnerOcclusion("Inner Layer Occlusion", Range(0.0, 1.0)) = 0.5
        [Toggle(_STRAND_DATA)] _StrandData("Strand Data (UV2: root->tip, depth)", Float) = 0
        _Cull("__cull", Float) = 0.0
        // kept so code that toggles Lit-style properties still finds them
        [HideInInspector] _AlphaClip("__clip", Float) = 1.0
        [HideInInspector] _Metallic("Metallic", Float) = 0.0
    }

    HLSLINCLUDE
    #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

    CBUFFER_START(UnityPerMaterial)
    float4 _BaseMap_ST;
    half4 _BaseColor;
    half _Cutoff;
    half _DitherWidth;
    half _Smoothness;
    half _SpecStrength;
    half _Spec2Strength;
    half _SpecShift;
    half _Spec2Shift;
    half _Wrap;
    half _RootDark;
    half _InnerOcclusion;
    half _StrandData;
    half _Cull;
    half _AlphaClip;
    half _Metallic;
    CBUFFER_END

    TEXTURE2D(_BaseMap); SAMPLER(sampler_BaseMap);

    // interleaved gradient noise (stable in screen space; TAA's sub-pixel jitter turns it into a soft edge)
    half HairDither(float2 positionCS)
    {
        return frac(52.9829189 * frac(dot(positionCS, float2(0.06711056, 0.00583715))));
    }

    void HairClip(half alpha, float2 positionCS)
    {
        half threshold = _Cutoff + (HairDither(positionCS) - 0.5h) * _DitherWidth;
        clip(alpha - threshold);
    }
    ENDHLSL

    SubShader
    {
        Tags { "RenderType"="TransparentCutout" "Queue"="AlphaTest" "RenderPipeline"="UniversalPipeline" "IgnoreProjector"="True" }
        LOD 300

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode"="UniversalForward" }
            Cull[_Cull]
            ZWrite On

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex HairVert
            #pragma fragment HairFrag
            #pragma shader_feature_local _STRAND_DATA
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile_fragment _ _SCREEN_SPACE_OCCLUSION
            #pragma multi_compile_fragment _ _LIGHT_COOKIES
            #pragma multi_compile _ _LIGHT_LAYERS
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RenderingLayers.hlsl"
            #include_with_pragmas "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Fog.hlsl"
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float4 tangentOS : TANGENT;
                float2 uv : TEXCOORD0;
                float2 strandUV : TEXCOORD1;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 positionWS : TEXCOORD1;
                half3 normalWS : TEXCOORD2;
                half4 tangentWS : TEXCOORD3;
                half4 strand : TEXCOORD4;      // x root->tip, y inner occlusion
                half fogFactor : TEXCOORD5;
                half3 sh : TEXCOORD6;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings HairVert(Attributes input)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_TRANSFER_INSTANCE_ID(input, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                VertexPositionInputs p = GetVertexPositionInputs(input.positionOS.xyz);
                VertexNormalInputs n = GetVertexNormalInputs(input.normalOS, input.tangentOS);
                o.positionCS = p.positionCS;
                o.positionWS = p.positionWS;
                o.normalWS = n.normalWS;
                o.tangentWS = half4(n.tangentWS, input.tangentOS.w * GetOddNegativeScale());
                o.uv = TRANSFORM_TEX(input.uv, _BaseMap);
            #if defined(_STRAND_DATA)
                o.strand = half4(input.strandUV.x, input.strandUV.y, 0, 1);
            #else
                o.strand = half4(0.6h, 0.0h, 0, 1);
            #endif
                o.fogFactor = ComputeFogFactor(p.positionCS.z);
                o.sh = SampleSHVertex(n.normalWS);
                return o;
            }

            half KK(half3 T, half3 H, half exponent)
            {
                half th = dot(T, H);
                half s = sqrt(max(0.0h, 1.0h - th * th));
                half dirAtten = smoothstep(-1.0h, 0.0h, th);
                return dirAtten * pow(s, exponent);
            }

            half3 HairLight(Light light, half3 N, half3 T, half3 V, half3 albedo, half noise, half ao, half specK)
            {
                half3 L = light.direction;
                half3 radiance = light.color * light.distanceAttenuation * light.shadowAttenuation;
                half ndl = dot(N, L);
                half diff = saturate((ndl + _Wrap) / (1.0h + _Wrap));
                half3 H = normalize(L + V);
                half exp1 = lerp(16.0h, 120.0h, _Smoothness);
                half3 T1 = normalize(T + N * _SpecShift);
                half3 T2 = normalize(T + N * _Spec2Shift);
                half s1 = KK(T1, H, exp1) * _SpecStrength;
                half s2 = KK(T2, H, exp1 * 0.35h) * _Spec2Strength * noise;
                half spec = saturate(ndl * 0.5h + 0.5h) * specK;   // highlights fade on the dark side
                half3 col = albedo * diff + (s1.xxx * lerp(half3(1, 1, 1), albedo * 4.0h, 0.25h) + s2 * albedo * 2.2h) * spec * ao;
                return radiance * col;
            }

            half4 HairFrag(Varyings input, FRONT_FACE_TYPE facing : FRONT_FACE_SEMANTIC) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(input);
                half4 tex = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, input.uv);
                HairClip(tex.a, input.positionCS.xy);

                half3 N = normalize(input.normalWS) * IS_FRONT_VFACE(facing, 1.0h, -1.0h);
                half3 T0 = normalize(input.tangentWS.xyz);
                // strand direction = bitangent (UV v runs along the strand)
                half3 T = normalize(cross(N, T0) * input.tangentWS.w);
                half3 V = normalize(GetWorldSpaceViewDir(input.positionWS));

                // strand data: x < 0 marks the painted base cap (its UVs do not follow the strands: matte, no root fade)
                half cap = step(input.strand.x, -0.5h);
                half rootDark = lerp(lerp(1.0h - _RootDark, 1.0h, smoothstep(0.0h, 0.45h, input.strand.x)), 1.0h, cap);
                half specK = lerp(1.0h, 0.2h, cap);
                half ao = lerp(1.0h, 1.0h - _InnerOcclusion, saturate(input.strand.y));
                half3 albedo = tex.rgb * _BaseColor.rgb * rootDark * ao;
                half noise = saturate(tex.r * 1.6h);

                InputData inputData = (InputData)0;
                inputData.positionWS = input.positionWS;
                inputData.normalWS = N;
                inputData.viewDirectionWS = V;
                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(input.positionCS);
                inputData.shadowCoord = TransformWorldToShadowCoord(input.positionWS);
                inputData.shadowMask = half4(1, 1, 1, 1);
                half4 shadowMask = half4(1, 1, 1, 1);
                AmbientOcclusionFactor aoFactor = CreateAmbientOcclusionFactor(inputData.normalizedScreenSpaceUV, ao);
                uint meshRenderingLayers = GetMeshRenderingLayer();

                half3 color = input.sh * albedo * aoFactor.indirectAmbientOcclusion;
                Light mainLight = GetMainLight(inputData, shadowMask, aoFactor);
            #ifdef _LIGHT_LAYERS
                if (IsMatchingLightLayer(mainLight.layerMask, meshRenderingLayers))
            #endif
                    color += HairLight(mainLight, N, T, V, albedo, noise, ao, specK);
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
                        color += HairLight(light, N, T, V, albedo, noise, ao, specK);
                }
            #endif
                LIGHT_LOOP_BEGIN(pixelLightCount)
                    Light light = GetAdditionalLight(lightIndex, inputData, shadowMask, aoFactor);
            #ifdef _LIGHT_LAYERS
                    if (IsMatchingLightLayer(light.layerMask, meshRenderingLayers))
            #endif
                        color += HairLight(light, N, T, V, albedo, noise, ao, specK);
                LIGHT_LOOP_END
            #endif
                color = MixFog(color, input.fogFactor);
                return half4(color, 1);
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
            Cull Off

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex ShadowVert
            #pragma fragment ShadowFrag
            #pragma multi_compile_instancing
            #pragma multi_compile_vertex _ _CASTING_PUNCTUAL_LIGHT_SHADOW
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.core/ShaderLibrary/CommonMaterial.hlsl"
            float3 _LightDirection;
            float3 _LightPosition;
            struct A { float4 positionOS : POSITION; float3 normalOS : NORMAL; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; };
            V ShadowVert(A input)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(input);
                float3 positionWS = TransformObjectToWorld(input.positionOS.xyz);
                float3 normalWS = TransformObjectToWorldNormal(input.normalOS);
            #if _CASTING_PUNCTUAL_LIGHT_SHADOW
                float3 lightDirectionWS = normalize(_LightPosition - positionWS);
            #else
                float3 lightDirectionWS = _LightDirection;
            #endif
                float4 positionCS = TransformWorldToHClip(ApplyShadowBias(positionWS, normalWS, lightDirectionWS));
                o.positionCS = ApplyShadowClamping(positionCS);
                o.uv = TRANSFORM_TEX(input.uv, _BaseMap);
                return o;
            }
            half4 ShadowFrag(V input) : SV_Target
            {
                clip(SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, input.uv).a - _Cutoff);
                return 0;
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
            #pragma target 3.0
            #pragma vertex DepthVert
            #pragma fragment DepthFrag
            #pragma multi_compile_instancing
            struct A { float4 positionOS : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };
            V DepthVert(A input)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                o.uv = TRANSFORM_TEX(input.uv, _BaseMap);
                return o;
            }
            half DepthFrag(V input) : SV_Target
            {
                HairClip(SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, input.uv).a, input.positionCS.xy);
                return input.positionCS.z;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode"="DepthNormals" }
            ZWrite On
            Cull[_Cull]

            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex DNVert
            #pragma fragment DNFrag
            #pragma multi_compile_instancing
            #pragma multi_compile_fragment _ _GBUFFER_NORMALS_OCT
            #include "Packages/com.unity.render-pipelines.core/ShaderLibrary/Packing.hlsl"
            struct A { float4 positionOS : POSITION; float3 normalOS : NORMAL; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; half3 normalWS : TEXCOORD1; UNITY_VERTEX_OUTPUT_STEREO };
            V DNVert(A input)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                o.uv = TRANSFORM_TEX(input.uv, _BaseMap);
                o.normalWS = TransformObjectToWorldNormal(input.normalOS);
                return o;
            }
            half4 DNFrag(V input, FRONT_FACE_TYPE facing : FRONT_FACE_SEMANTIC) : SV_Target
            {
                HairClip(SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, input.uv).a, input.positionCS.xy);
                float3 n = normalize(input.normalWS) * IS_FRONT_VFACE(facing, 1.0, -1.0);
            #if defined(_GBUFFER_NORMALS_OCT)
                float2 oct = PackNormalOctQuadEncode(n);
                return half4(PackFloat2To888(saturate(oct * 0.5 + 0.5)), 0);
            #else
                return half4(n, 0);
            #endif
            }
            ENDHLSL
        }
    }
    FallBack "Universal Render Pipeline/Lit"
}
