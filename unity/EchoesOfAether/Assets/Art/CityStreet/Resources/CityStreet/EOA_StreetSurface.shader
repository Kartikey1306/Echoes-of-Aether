// EOA/StreetSurface: wet-street PBR surface for the open city's roads, pavements, kerbs, gutters and road paint
// (street kit, blender/city_street). Built on URP's UniversalFragmentPBR (Forward+, shadows, SSAO, reflection probes).
//
//  * World-space planar UVs on horizontal faces (no stretching across merged road / slab geometry); vertical faces
//    and _UVMode 1 (gutter strips) use the mesh UV0. _Tiling = 1 / texture tile size in metres.
//  * Anti-tiling: a second, rotated / offset sample of every map is blended in by a macro noise (_MacroMap.a), and a
//    40-60 m macro map adds tone (r), grime (g) and puddle basins (b). Grid materials (pavers) use rotation 0 and an
//    offset that is a whole number of units so the joints stay aligned.
//  * Wetness from the shared CityFx global _EOA_Wetness (Weather.cs): darkening and glossy water film, water in the
//    pores (MaskMap.b = height), flat mirror puddles in the macro basins (amount = _PuddleAmount), rain ripples in the
//    puddles from the FX globals (Shaders/EOA_RainRipple.hlsl: 16-frame ripple normal flipbook, strength follows the
//    rain; 0 = off, so it falls back cleanly), the nearest neon emitters (EOA_NeonLight) tinting the wet film at
//    grazing angles, and puddles as dark water that mirror those emitters (view-dependent glints broken up by the
//    ripples) instead of a flat probe colour.
//  * _Cutoff > 0 clips by BaseMap alpha (worn road paint) in every pass.
Shader "EOA/StreetSurface"
{
    Properties
    {
        _BaseMap ("Base Colour", 2D) = "white" {}
        _BaseColor ("Tint", Color) = (1, 1, 1, 1)
        _BumpMap ("Normal", 2D) = "bump" {}
        _MaskMap ("Mask (R metal, G AO, B height, A smoothness)", 2D) = "white" {}
        _MacroMap ("Macro (R tone, G grime, B basins, A blend noise)", 2D) = "grey" {}
        _Tiling ("Tiling (1 / metres)", Float) = 0.25
        _MacroTiling ("Macro tiling (1 / metres)", Float) = 0.02
        _MacroStrength ("Macro strength", Range(0, 1)) = 0.6
        _NormalScale ("Normal scale", Range(0, 2)) = 1
        _SmoothnessScale ("Smoothness scale", Range(0, 2)) = 1
        _AntiTile ("Anti-tiling strength", Range(0, 1)) = 1
        _AntiTileRot ("Anti-tiling rotation (rad)", Float) = 0.7
        _AntiTileOffset ("Anti-tiling offset (tile units)", Vector) = (0.37, 0.61, 0, 0)
        _PuddleAmount ("Puddle amount", Range(0, 1.5)) = 0.6
        _WetResponse ("Wet response", Range(0, 1)) = 1
        _NeonReflect ("Neon reflection", Range(0, 2)) = 0.6
        _Cutoff ("Alpha clip (0 = off)", Range(0, 1)) = 0
        _UVMode ("UV mode (0 world planar, 1 mesh UV0)", Float) = 0
    }

    SubShader
    {
        Tags { "RenderType"="Opaque" "RenderPipeline"="UniversalPipeline" "Queue"="Geometry" "UniversalMaterialType"="Lit" }
        LOD 300

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

        CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseColor;
            float _Tiling;
            float _MacroTiling;
            half _MacroStrength;
            half _NormalScale;
            half _SmoothnessScale;
            half _AntiTile;
            float _AntiTileRot;
            float4 _AntiTileOffset;
            half _PuddleAmount;
            half _WetResponse;
            half _NeonReflect;
            half _Cutoff;
            float _UVMode;
        CBUFFER_END

        TEXTURE2D(_BaseMap);    SAMPLER(sampler_BaseMap);
        TEXTURE2D(_BumpMap);    SAMPLER(sampler_BumpMap);
        TEXTURE2D(_MaskMap);    SAMPLER(sampler_MaskMap);
        TEXTURE2D(_MacroMap);   SAMPLER(sampler_MacroMap);

        // Surface UV: world XZ on horizontal faces (unless _UVMode = 1), mesh UV0 otherwise. Returns tile units.
        float2 StreetUV(float3 positionWS, float3 normalWS, float2 uv0)
        {
            bool planar = _UVMode < 0.5 && abs(normalWS.y) > 0.7;
            return planar ? positionWS.xz * _Tiling : uv0 * float2(_Tiling, _UVMode > 0.5 ? 1.0 : _Tiling);
        }

        float2 RotUV(float2 uv, float a)
        {
            float s = sin(a), c = cos(a);
            return float2(uv.x * c - uv.y * s, uv.x * s + uv.y * c);
        }

        half StreetAlpha(float2 uv)
        {
            return SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uv).a;
        }
        ENDHLSL

        Pass
        {
            Name "ForwardLit"
            Tags { "LightMode"="UniversalForward" }
            Cull Back
            ZWrite On

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex vert
            #pragma fragment frag

            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile _ _ADDITIONAL_LIGHTS_VERTEX _ADDITIONAL_LIGHTS
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
            #pragma multi_compile_fog
            #pragma multi_compile_instancing

            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DBuffer.hlsl"
            #include "Assets/Shaders/EOA_CityFx.hlsl"

            // FX globals: rain ripple flipbook for the puddles (unset = strength 0 = no ripples).
            #include "Assets/Shaders/EOA_RainRipple.hlsl"
            float _EOA_SSROn;

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float4 tangentOS : TANGENT;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 positionWS : TEXCOORD1;
                float3 normalWS : TEXCOORD2;
                float4 tangentWS : TEXCOORD3;
                half fogFactor : TEXCOORD4;
                half3 vertexSH : TEXCOORD5;
                UNITY_VERTEX_INPUT_INSTANCE_ID
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_TRANSFER_INSTANCE_ID(v, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                VertexPositionInputs p = GetVertexPositionInputs(v.positionOS.xyz);
                VertexNormalInputs n = GetVertexNormalInputs(v.normalOS, v.tangentOS);
                o.positionCS = p.positionCS;
                o.positionWS = p.positionWS;
                o.normalWS = n.normalWS;
                o.tangentWS = float4(n.tangentWS, v.tangentOS.w * GetOddNegativeScale());
                o.uv = v.uv;
                o.fogFactor = ComputeFogFactor(p.positionCS.z);
                o.vertexSH = SampleSH(n.normalWS);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                UNITY_SETUP_INSTANCE_ID(i);
                UNITY_SETUP_STEREO_EYE_INDEX_POST_VERTEX(i);
                float3 nGeo = normalize(i.normalWS);
                bool planar = _UVMode < 0.5 && abs(nGeo.y) > 0.7;
                float2 uvA = StreetUV(i.positionWS, nGeo, i.uv);
                float2 macroUV = (planar ? i.positionWS.xz : i.uv) * _MacroTiling;
                half4 macro = SAMPLE_TEXTURE2D(_MacroMap, sampler_MacroMap, macroUV);

                // two decorrelated taps blended by the macro noise (texture repetition breaker)
                float2 uvB = RotUV(uvA, _AntiTileRot) + _AntiTileOffset.xy;
                half wB = smoothstep(0.38, 0.62, macro.a) * _AntiTile;
                half4 baseA = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uvA);
                half4 maskA = SAMPLE_TEXTURE2D(_MaskMap, sampler_MaskMap, uvA);
                half3 nA = UnpackNormalScale(SAMPLE_TEXTURE2D(_BumpMap, sampler_BumpMap, uvA), _NormalScale);
                half4 base = baseA, mask = maskA;
                half3 nTS = nA;
                UNITY_BRANCH if (wB > 0.001)
                {
                    half4 baseB = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, uvB);
                    half4 maskB = SAMPLE_TEXTURE2D(_MaskMap, sampler_MaskMap, uvB);
                    half3 nB = UnpackNormalScale(SAMPLE_TEXTURE2D(_BumpMap, sampler_BumpMap, uvB), _NormalScale);
                    nB.xy = RotUV(nB.xy, -_AntiTileRot);
                    base = lerp(baseA, baseB, wB);
                    mask = lerp(maskA, maskB, wB);
                    nTS = normalize(lerp(nA, nB, wB));
                }
                if (_Cutoff > 0) clip(base.a - _Cutoff);

                half3 albedo = base.rgb * _BaseColor.rgb;
                half metal = mask.r;
                half ao = mask.g;
                half height = mask.b;
                half smooth = saturate(mask.a * _SmoothnessScale);

                // macro tone and grime
                albedo *= lerp(1.0, macro.r * 2.0, _MacroStrength);
                half grime = saturate((macro.g - 0.5) * 2.0) * _MacroStrength;
                albedo *= 1.0 - grime * 0.35;
                smooth *= 1.0 - grime * 0.25;

                // wetness: film everywhere, water in the low texels, mirror puddles in the macro basins
                half wet = saturate(_EOA_Wetness) * _WetResponse;
                half pores = smoothstep(0.62 - wet * 0.2, 0.5 - wet * 0.25, height) * wet;
                half field = planar ? macro.b * 0.8 + (1.0 - height) * 0.2 : 0.0;
                half level = 1.0 - wet * 0.5 * _PuddleAmount;
                half puddle = planar ? smoothstep(level, level + 0.05, field) : 0.0;
                albedo *= lerp(1.0, 0.5, wet);
                albedo *= 1.0 - pores * 0.25 - puddle * 0.8;      // standing water: dark
                smooth = lerp(smooth, max(smooth, 0.68 + 0.2 * (1.0 - height)), wet * 0.9);
                smooth = lerp(smooth, 0.94, saturate(pores * 0.7 + puddle));
                metal *= 1.0 - puddle;
                nTS = normalize(lerp(nTS, half3(0, 0, 1), saturate(puddle * 0.92 + pores * 0.4)));
                // rain ripples: full strength in the puddles, a fainter pock-marking of the whole wet film while it rains
                UNITY_BRANCH if (_EOA_RainRippleParams.w > 0 && planar && (puddle > 0.01 || wet > 0.4))
                {
                    half3 rip = EOA_RainRippleNormal(i.positionWS.xz, 1.1);
                    nTS = normalize(half3(nTS.xy + rip.xy * (puddle * 1.6 + (1.0 - puddle) * wet * 0.35), nTS.z));
                }

                // tangent frame: world X / Z on planar ground (UV = world XZ), mesh tangents elsewhere
                float3 T, B;
                if (planar)
                {
                    T = float3(1, 0, 0);
                    B = float3(0, 0, nGeo.y > 0 ? 1 : -1);
                }
                else
                {
                    T = normalize(i.tangentWS.xyz);
                    B = cross(nGeo, T) * i.tangentWS.w;
                }
                float3 nWS = normalize(mul(nTS, float3x3(T, B, nGeo)));

                InputData inputData = (InputData)0;
                inputData.positionWS = i.positionWS;
                inputData.normalWS = nWS;
                inputData.viewDirectionWS = GetWorldSpaceNormalizeViewDir(i.positionWS);
                inputData.shadowCoord = TransformWorldToShadowCoord(i.positionWS);
                inputData.fogCoord = i.fogFactor;
                inputData.bakedGI = SampleSH(nWS);
                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(i.positionCS);
                inputData.shadowMask = half4(1, 1, 1, 1);

                SurfaceData s = (SurfaceData)0;
                s.albedo = albedo;
                s.metallic = metal;
                s.specular = half3(0, 0, 0);
                s.smoothness = smooth;
                s.occlusion = ao * (1.0 - puddle * 0.88);        // puddles: dark water, the screen-space reflections and neon glints carry them
                s.normalTS = nTS;
                s.alpha = 1;
                s.emission = 0;
                #if defined(_DBUFFER)
                ApplyDecalToSurfaceData(i.positionCS, s, inputData);
                #endif

                half4 color = UniversalFragmentPBR(inputData, s);
                // neon catching the wet street at grazing angles (shared CityFx neon field)
                half nv = saturate(dot(nWS, inputData.viewDirectionWS));
                half fres = 0.04 + 0.96 * pow(1.0 - nv, 5.0);
                // (a soft sheen on the film; standing water shows the emitters as streaks below, not as a flat tint)
                color.rgb += EOA_NeonLight(i.positionWS) * fres * wet * 0.3 * (1.0 - puddle * 0.85) * _NeonReflect;
                // Wet film / puddles mirror the nearest neon emitters as long vertical streaks (the rain-soaked street look):
                // the lobe is sharp in azimuth and wide in elevation (anisotropic, stretched toward the viewer), tighter
                // in standing water. With the screen-space reflections on (_EOA_SSROn) these only add the hot cores; with
                // them off (low effects / WebGL) they carry the wet-street reflections on their own.
                UNITY_BRANCH if (wet > 0.05 && planar)
                {
                    half3 R = reflect(-inputData.viewDirectionWS, nWS);
                    float2 rh = normalize(R.xz + 1e-5);
                    half3 glints = 0;
                    float sharp = lerp(60.0, 260.0, saturate(puddle + pores * 0.5));
                    float spread = lerp(0.45, 0.22, saturate(puddle + pores * 0.5));
                    int nn = (int)_EOA_NeonCount;
                    [unroll] for (int k = 0; k < 8; k++)
                    {
                        if (k < nn)
                        {
                            float3 dn = _EOA_NeonPos[k].xyz - i.positionWS;
                            float dist = length(dn);
                            float3 L = dn / max(dist, 1e-3);
                            float att = saturate(1.0 - dist / (_EOA_NeonPos[k].w * 3.5));
                            float az = pow(saturate(dot(rh, normalize(L.xz + 1e-5))), sharp);
                            float de = (R.y - L.y) / spread;
                            glints += _EOA_NeonCol[k].rgb * (az * exp(-de * de) * att * att);
                        }
                    }
                    float k2 = lerp(1.0, 0.45, saturate(_EOA_SSROn));
                    color.rgb += glints * (0.2 + fres) * (wet * 0.35 + saturate(puddle + pores * 0.3)) * _NeonReflect * 2.4 * k2;
                }
                color.rgb = MixFog(color.rgb, inputData.fogCoord);
                color.a = 1;
                return color;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthOnly"
            Tags { "LightMode"="DepthOnly" }
            ZWrite On
            ColorMask R
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing

            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct Varyings { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; float3 positionWS : TEXCOORD1; float3 normalWS : TEXCOORD2; UNITY_VERTEX_OUTPUT_STEREO };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionWS = TransformObjectToWorld(v.positionOS.xyz);
                o.positionCS = TransformWorldToHClip(o.positionWS);
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                o.uv = v.uv;
                return o;
            }

            half frag(Varyings i) : SV_Target
            {
                if (_Cutoff > 0) clip(StreetAlpha(StreetUV(i.positionWS, normalize(i.normalWS), i.uv)) - _Cutoff);
                return i.positionCS.z;
            }
            ENDHLSL
        }

        Pass
        {
            Name "DepthNormals"
            Tags { "LightMode"="DepthNormals" }
            ZWrite On
            Cull Back

            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #pragma multi_compile_fragment _ _GBUFFER_NORMALS_OCT
            #pragma multi_compile_fragment _ _WRITE_RENDERING_LAYERS
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/RealtimeLights.hlsl"

            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct Varyings { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; float3 positionWS : TEXCOORD1; float3 normalWS : TEXCOORD2; UNITY_VERTEX_OUTPUT_STEREO };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionWS = TransformObjectToWorld(v.positionOS.xyz);
                o.positionCS = TransformWorldToHClip(o.positionWS);
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                o.uv = v.uv;
                return o;
            }

            void frag(Varyings i, out half4 outNormalWS : SV_Target0
            #ifdef _WRITE_RENDERING_LAYERS
                , out uint outRenderingLayers : SV_Target1
            #endif
            )
            {
                float3 n = normalize(i.normalWS);
                if (_Cutoff > 0) clip(StreetAlpha(StreetUV(i.positionWS, n, i.uv)) - _Cutoff);
                #if defined(_GBUFFER_NORMALS_OCT)
                float2 oct = PackNormalOctQuadEncode(n);
                outNormalWS = half4(PackFloat2To888(saturate(oct * 0.5 + 0.5)), 0.0);
                #else
                outNormalWS = half4(n, 0.0);
                #endif
                #ifdef _WRITE_RENDERING_LAYERS
                outRenderingLayers = EncodeMeshRenderingLayer();
                #endif
            }
            ENDHLSL
        }
    }
    FallBack "Universal Render Pipeline/Lit"
}
