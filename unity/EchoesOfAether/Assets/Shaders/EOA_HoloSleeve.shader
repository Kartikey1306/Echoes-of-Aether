// Character hologram (Kael's Aether forearm sleeve): additive, unlit, double-sided, no depth write.
// _BaseMap RGB = pattern, A = coverage; tinted by _EmissionColor (set from the hero's glow colour by
// CharacterModel.Glow) × _Intensity. Fresnel brightens the silhouette edge, faint scanlines drift along the arm
// and a subtle flicker keeps it reading as projected light rather than a solid shell.
Shader "EOA/HoloSleeve"
{
    Properties
    {
        _BaseMap ("Pattern (RGB) Coverage (A)", 2D) = "white" {}
        _BaseColor ("Base (unused, kept for the glow API)", Color) = (0, 0, 0, 1)
        [HDR] _EmissionColor ("Tint (HDR)", Color) = (0, 2.7, 3, 1)
        _Intensity ("Intensity", Float) = 0.45
        _Fresnel ("Edge Power", Float) = 2.2
        _EdgeBoost ("Edge Boost", Float) = 1.2
        _Scan ("Scanline Density", Float) = 220
        _ScanSpeed ("Scanline Speed", Float) = 0.6
        _Flicker ("Flicker", Range(0, 1)) = 0.12
    }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "IgnoreProjector"="True" "RenderPipeline"="UniversalPipeline" }
        Blend One One
        ZWrite Off
        Cull Off

        Pass
        {
            Name "Forward"
            Tags { "LightMode"="UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            TEXTURE2D(_BaseMap); SAMPLER(sampler_BaseMap);
            CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseColor, _EmissionColor;
            float _Intensity, _Fresnel, _EdgeBoost, _Scan, _ScanSpeed, _Flicker;
            CBUFFER_END

            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float3 viewWS : TEXCOORD2;
                float fog : TEXCOORD3;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                float3 posWS = TransformObjectToWorld(v.positionOS.xyz);
                o.positionCS = TransformWorldToHClip(posWS);
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                o.viewWS = GetWorldSpaceViewDir(posWS);
                o.uv = TRANSFORM_TEX(v.uv, _BaseMap);
                o.fog = ComputeFogFactor(o.positionCS.z);
                return o;
            }

            half4 frag(Varyings i, bool front : SV_IsFrontFace) : SV_Target
            {
                half4 tex = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, i.uv);
                float3 n = normalize(front ? i.normalWS : -i.normalWS);
                float ndv = saturate(abs(dot(n, normalize(i.viewWS))));
                float edge = pow(1 - ndv, _Fresnel) * _EdgeBoost;
                float scan = 0.82 + 0.18 * sin((i.uv.y * _Scan - _Time.y * _ScanSpeed * 6.2832));
                float flick = 1 - _Flicker * (0.5 + 0.5 * sin(_Time.y * 23.0)) * step(0.93, frac(sin(floor(_Time.y * 9.0) * 91.7) * 43758.5));
                half3 c = _EmissionColor.rgb * _Intensity * (tex.rgb * tex.a * scan + edge * tex.a * 0.6) * flick;
                c = MixFogColor(c, half3(0, 0, 0), i.fog);
                return half4(c, 0);
            }
            ENDHLSL
        }
    }
    FallBack Off
}
