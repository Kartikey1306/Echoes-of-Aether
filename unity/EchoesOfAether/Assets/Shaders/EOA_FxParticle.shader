// Lit soft particles for the Blender-rendered FX flipbooks (rain splashes / rings / drips, steam, smoke, mist).
// Texture: RGB = rendered lighting / highlight (grey), A = coverage. Colour per vertex = ambient SH + neon emitter
// field + Forward+ additional lights + moon + lightning, times the particle colour and _BaseColor. Flipbook frames
// blend smoothly when the particle system sends the UV2 + AnimBlend vertex streams (FxLibrary.Flipbook sets them):
// TEXCOORD0.xy current frame, TEXCOORD0.zw next frame, TEXCOORD1.x blend.
// Output is premultiplied (Blend One OneMinusSrcAlpha): _Alpha 0 = additive glow, 1 = fully occluding (smoke).
// Depth-faded against the scene (_Soft metres), faded near the camera and by the city height fog / Unity fog.
Shader "EOA/FxParticle"
{
    Properties
    {
        _BaseMap ("Flipbook (RGB light, A coverage)", 2D) = "white" {}
        [HDR] _BaseColor ("Tint", Color) = (1, 1, 1, 1)
        _Alpha ("Occlusion (0 additive .. 1 alpha)", Range(0, 1)) = 0.5
        _Light ("Gain: ambient, neon, lights, moon", Vector) = (1, 1, 1, 0.3)
        _Emission ("Self glow", Float) = 0
        _Soft ("Depth Fade (m)", Float) = 0.4
        _NearFade ("Near Fade (m)", Float) = 0.6
        _FlashGain ("Lightning Gain", Float) = 2
        _Contrast ("Coverage contrast", Float) = 1
    }
    SubShader
    {
        Tags { "Queue"="Transparent" "RenderType"="Transparent" "IgnoreProjector"="True" "RenderPipeline"="UniversalPipeline" }
        Pass
        {
            Name "Forward"
            Tags { "LightMode"="UniversalForward" }
            Blend One OneMinusSrcAlpha
            ZWrite Off
            Cull Off

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"
            #include "EOA_CityFx.hlsl"

            TEXTURE2D(_BaseMap); SAMPLER(sampler_BaseMap);
            CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseColor;
            float4 _Light;
            float _Alpha, _Emission, _Soft, _NearFade, _FlashGain, _Contrast;
            CBUFFER_END

            float4 _EOA_LightningDir;

            struct Attributes
            {
                float4 positionOS : POSITION;
                half4 color : COLOR;
                float4 uv : TEXCOORD0;      // xy frame, zw next frame (UV2 stream)
                float animBlend : TEXCOORD1;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float4 uv : TEXCOORD0;
                half4 color : TEXCOORD1;
                float3 posWS : TEXCOORD2;
                float2 blendEye : TEXCOORD3;
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                float3 ws = TransformObjectToWorld(v.positionOS.xyz);
                o.positionCS = TransformWorldToHClip(ws);
                o.posWS = ws;
                float3 V = normalize(_WorldSpaceCameraPos.xyz - ws);
                float3 light = SampleSH(V) * _Light.x + EOA_NeonLight(ws) * _Light.y;
                Light mainL = GetMainLight();
                light += mainL.color * _Light.w;
                float3 add = 0;
                InputData inputData = (InputData)0;
                inputData.positionWS = ws;
                float4 sp = ComputeScreenPos(o.positionCS);
                inputData.normalizedScreenSpaceUV = saturate(sp.xy / max(sp.w, 1e-4));
                uint count = GetAdditionalLightsCount();
                LIGHT_LOOP_BEGIN(count)
                    Light l = GetAdditionalLight(lightIndex, ws);
                    add += l.color * l.distanceAttenuation * (0.5 + 0.8 * pow(saturate(dot(-l.direction, V) * 0.5 + 0.5), 3.0));
                LIGHT_LOOP_END
                light += add * _Light.z + float3(0.62, 0.68, 0.95) * (_EOA_LightningDir.w * _FlashGain);
                o.color = half4((light + _Emission) * v.color.rgb * _BaseColor.rgb, v.color.a * _BaseColor.a);
                o.uv = float4(TRANSFORM_TEX(v.uv.xy, _BaseMap), TRANSFORM_TEX(v.uv.zw, _BaseMap));
                o.blendEye = float2(v.animBlend, -TransformWorldToView(ws).z);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                half4 a = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, i.uv.xy);
                half4 b = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, i.uv.zw);
                half4 tex = lerp(a, b, saturate(i.blendEye.x));
                float eye = i.blendEye.y;
                float2 suv = i.positionCS.xy / _ScaledScreenParams.xy;
                float scene = LinearEyeDepth(SampleSceneDepth(suv), _ZBufferParams);
                float soft = saturate((scene - eye) / max(_Soft, 1e-3));
                float near = saturate((eye - _NearFade * 0.3) / max(_NearFade, 1e-3));
                float fog = EOA_FxFogFade(i.posWS) * EOA_UnityFogKeep(eye);
                float cov = saturate(pow(max(tex.a, 0.0), _Contrast)) * i.color.a * soft * near;
                half3 rgb = i.color.rgb * tex.rgb * cov * fog;
                return half4(rgb, cov * _Alpha * fog);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
