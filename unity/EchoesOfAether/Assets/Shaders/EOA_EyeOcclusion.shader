// Eye occlusion shell (heroes): a thin multiply-blended shell just in front of the eyeball, behind the lids. It darkens
// the eyeball where the lids meet it - strongest under the upper lid and lashes, softly in the corners - so the eyes sit
// in their sockets instead of looking stuck on. UV.x carries the occlusion amount (0 = none, 1 = full) baked per vertex.
Shader "EOA/EyeOcclusion"
{
    Properties
    {
        _ShadowColor("Shadow Colour", Color) = (0.32, 0.22, 0.2, 1)
        _Strength("Strength", Range(0, 1)) = 0.85
        // common character-material properties read generically by game / dev code (tints, wetness, logs); unused here
        [HideInInspector] _BaseColor("Base Colour", Color) = (1, 1, 1, 1)
        [HideInInspector] _BaseMap("Base Map", 2D) = "white" {}
        [HideInInspector] _Smoothness("Smoothness", Range(0, 1)) = 0.5
    }
    SubShader
    {
        Tags { "Queue"="Transparent-20" "RenderType"="Transparent" "RenderPipeline"="UniversalPipeline" "IgnoreProjector"="True" }
        Pass
        {
            Name "Occlusion"
            Tags { "LightMode"="UniversalForward" }
            Blend DstColor Zero
            ZWrite Off
            ZTest LEqual
            Cull Back
            HLSLPROGRAM
            #pragma target 3.0
            #pragma vertex Vert
            #pragma fragment Frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            CBUFFER_START(UnityPerMaterial)
            half4 _ShadowColor;
            half _Strength;
            half4 _BaseColor;
            float4 _BaseMap_ST;
            half _Smoothness;
            CBUFFER_END
            struct A { float4 positionOS : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct V { float4 positionCS : SV_POSITION; half occl : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };
            V Vert(A input)
            {
                V o;
                UNITY_SETUP_INSTANCE_ID(input);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionCS = TransformObjectToHClip(input.positionOS.xyz);
                o.occl = saturate(input.uv.x);
                return o;
            }
            half4 Frag(V input) : SV_Target
            {
                half k = input.occl * _Strength;
                return half4(lerp(half3(1, 1, 1), _ShadowColor.rgb, k), 1);
            }
            ENDHLSL
        }
    }
}
