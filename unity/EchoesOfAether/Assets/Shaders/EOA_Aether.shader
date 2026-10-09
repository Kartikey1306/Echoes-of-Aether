// Flowing Aether energy: fresnel rim + two scrolling noise layers blending cyan and violet, additive.
// Used for the Core, tethers, crystals and resonance effects (EnvMaterials.Aether).
Shader "EOA/Aether"
{
    Properties
    {
        _Color ("Color", Color) = (0.37, 0.85, 1, 1)
        _Color2 ("Secondary", Color) = (0.65, 0.48, 1, 1)
        _Intensity ("Intensity", Float) = 1
        _Fresnel ("Fresnel Power", Float) = 2.2
        _Flow ("Flow Speed", Float) = 0.35
        _Scale ("Noise Scale", Float) = 1.6
    }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "IgnoreProjector"="True" "RenderPipeline"="UniversalPipeline" }
        Blend One One
        ZWrite Off
        Cull Back

        Pass
        {
            Name "Forward"
            Tags { "LightMode"="UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
            half4 _Color, _Color2;
            float _Intensity, _Fresnel, _Flow, _Scale;
            CBUFFER_END

            struct Attributes { float4 positionOS : POSITION; float3 normalOS : NORMAL; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float3 positionOS : TEXCOORD2;
                float fog : TEXCOORD3;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                VertexPositionInputs p = GetVertexPositionInputs(v.positionOS.xyz);
                o.positionCS = p.positionCS;
                o.positionWS = p.positionWS;
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                o.positionOS = v.positionOS.xyz;
                o.fog = ComputeFogFactor(p.positionCS.z);
                return o;
            }

            float hash3(float3 p) { return frac(sin(dot(p, float3(17.1, 113.7, 41.3))) * 43758.5453); }
            float noise3(float3 p)
            {
                float3 i = floor(p), f = frac(p);
                f = f * f * (3.0 - 2.0 * f);
                float n000 = hash3(i), n100 = hash3(i + float3(1, 0, 0)), n010 = hash3(i + float3(0, 1, 0)), n110 = hash3(i + float3(1, 1, 0));
                float n001 = hash3(i + float3(0, 0, 1)), n101 = hash3(i + float3(1, 0, 1)), n011 = hash3(i + float3(0, 1, 1)), n111 = hash3(i + float3(1, 1, 1));
                return lerp(lerp(lerp(n000, n100, f.x), lerp(n010, n110, f.x), f.y), lerp(lerp(n001, n101, f.x), lerp(n011, n111, f.x), f.y), f.z);
            }

            half4 frag(Varyings i) : SV_Target
            {
                float t = _Time.y * _Flow;
                float3 n = normalize(i.normalWS);
                float3 v = normalize(GetWorldSpaceViewDir(i.positionWS));
                float fres = pow(1.0 - saturate(abs(dot(n, v))), _Fresnel);
                float3 q = i.positionOS * _Scale;
                float a = noise3(q * 1.7 + float3(0, t, t * 0.6));
                float b = noise3(q * 3.9 - float3(t * 0.8, t * 1.3, 0));
                float veins = smoothstep(0.55, 0.95, 1.0 - abs(a - b) * 2.2);
                float3 col = lerp(_Color.rgb, _Color2.rgb, smoothstep(0.3, 0.8, a));
                float body = 0.22 + 0.5 * b;
                float3 c = col * (body + veins * 1.1 + fres * 1.4) * _Intensity;
                c = MixFogColor(c, half3(0, 0, 0), i.fog);
                return half4(c, 1.0);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
