// Tear meniscus / wet lid line (heroes): a thin strip along the lower lid where it meets the eyeball. Additive: only the
// wet specular (sharp highlight from the lights, a studio catchlight and a little environment reflection) is added, so
// the lid margin reads moist without a visible strip. UV.x = mask (0 at the strip ends / edges, 1 in the middle).
Shader "EOA/EyeWet"
{
    Properties
    {
        _Gloss("Gloss", Range(0.5, 1)) = 0.96
        _Strength("Strength", Range(0, 2)) = 0.8
        // common character-material properties read generically by game / dev code (tints, wetness, logs); unused here
        [HideInInspector] _BaseColor("Base Colour", Color) = (1, 1, 1, 1)
        [HideInInspector] _BaseMap("Base Map", 2D) = "white" {}
        [HideInInspector] _Smoothness("Smoothness", Range(0, 1)) = 0.5
    }
    SubShader
    {
        Tags { "Queue"="Transparent-19" "RenderType"="Transparent" "RenderPipeline"="UniversalPipeline" "IgnoreProjector"="True" }
        Pass
        {
            Name "Wet"
            Tags { "LightMode"="UniversalForward" }
            Blend One One
            ZWrite Off
            ZTest LEqual
            Cull Off
            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE _MAIN_LIGHT_SHADOWS_SCREEN
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            CBUFFER_START(UnityPerMaterial)
            half _Gloss;
            half _Strength;
            half4 _BaseColor;
            float4 _BaseMap_ST;
            half _Smoothness;
            CBUFFER_END
            struct A { float4 positionOS : POSITION; float3 normalOS : NORMAL; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 positionCS : SV_POSITION; float3 positionWS : TEXCOORD0; half3 normalWS : TEXCOORD1; half mask : TEXCOORD2; UNITY_VERTEX_OUTPUT_STEREO };
            V Vert(A input)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                VertexPositionInputs p = GetVertexPositionInputs(input.positionOS.xyz);
                o.positionCS = p.positionCS;
                o.positionWS = p.positionWS;
                o.normalWS = TransformObjectToWorldNormal(input.normalOS);
                o.mask = saturate(input.uv.x);
                return o;
            }
            half4 Frag(V input) : SV_Target
            {
                half3 N = normalize(input.normalWS);
                half3 Vd = GetWorldSpaceNormalizeViewDir(input.positionWS);
                half3 R = reflect(-Vd, N);
                Light l = GetMainLight(TransformWorldToShadowCoord(input.positionWS));
                half3 H = normalize(l.direction + Vd);
                half e = exp2(10.0h * _Gloss + 1.0h);
                half3 spec = l.color * l.shadowAttenuation * pow(saturate(dot(N, H)), e) * 0.6h;
                half3 camRight = UNITY_MATRIX_V[0].xyz;
                half3 camUp = UNITY_MATRIX_V[1].xyz;
                half3 box = normalize(Vd + camUp * 0.38h + camRight * 0.22h);
                spec += pow(saturate(dot(R, box)), 300.0h) * 0.5h;
                half fres = 0.04h + 0.96h * pow(1.0h - saturate(dot(N, Vd)), 5.0h);
                spec += GlossyEnvironmentReflection(R, 1.0h - _Gloss, 1.0h) * fres * 0.5h;
                return half4(spec * input.mask * _Strength, 0);
            }
            ENDHLSL
        }
    }
}
