// Contact shadows under characters: a depth-aware ambient-occlusion "blob" (DepthCues draws one instanced unit box
// per character at its ground point, x/z = diameter, y = height of the volume). Like a deferred decal, each box pixel
// reconstructs the world position under it from the depth texture and darkens it by a soft radial falloff that also
// fades with height above the ground point and only lands on upward-facing surfaces (steps, curbs, floors; not walls
// or the character itself). Multiplicative, drawn after the opaques and before the height fog and transparents.
Shader "EOA/ContactShadow"
{
    Properties
    {
        _Strength ("Strength", Range(0, 1)) = 0.62
    }
    SubShader
    {
        Tags { "Queue"="Transparent-20" "RenderType"="Transparent" "IgnoreProjector"="True" "RenderPipeline"="UniversalPipeline" }
        Pass
        {
            Name "ContactShadow"
            Tags { "LightMode"="UniversalForward" }
            Blend DstColor Zero
            ZWrite Off
            ZTest Always
            Cull Front

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"

            CBUFFER_START(UnityPerMaterial)
            float _Strength;
            CBUFFER_END

            UNITY_INSTANCING_BUFFER_START(Props)
                UNITY_DEFINE_INSTANCED_PROP(float, _Amount)
            UNITY_INSTANCING_BUFFER_END(Props)

            struct Attributes
            {
                float4 positionOS : POSITION;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                nointerpolation float3 center : TEXCOORD0;
                nointerpolation float3 size : TEXCOORD1;   // x radius, y half height, z amount
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(v);
                float4x4 m = GetObjectToWorldMatrix();
                o.positionCS = TransformWorldToHClip(TransformObjectToWorld(v.positionOS.xyz));
                o.center = float3(m._m03, m._m13, m._m23);
                o.size = float3(length(float3(m._m00, m._m10, m._m20)) * 0.5, length(float3(m._m01, m._m11, m._m21)) * 0.5,
                                UNITY_ACCESS_INSTANCED_PROP(Props, _Amount));
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                float2 uv = i.positionCS.xy / _ScaledScreenParams.xy;
                float raw = SampleSceneDepth(uv);
                #if !UNITY_REVERSED_Z
                    raw = lerp(UNITY_NEAR_CLIP_VALUE, 1, raw);
                #endif
                float3 wp = ComputeWorldSpacePosition(uv, raw, UNITY_MATRIX_I_VP);
                float3 rel = wp - i.center;
                float r = length(rel.xz) / max(i.size.x, 1e-3);
                float y = rel.y / max(i.size.y, 1e-3);
                if (r >= 1.0 || abs(y) >= 1.0) return half4(1, 1, 1, 1);
                // facing from the depth derivatives: floors, steps and curbs take the shadow, walls and the body do not
                float3 n = normalize(cross(ddy(wp), ddx(wp)));
                float up = saturate((abs(n.y) - 0.6) * 4.0);
                // soft core + wide penumbra (ambient occlusion under the feet)
                float blob = exp(-r * r * 4.0) * 0.75 + (1.0 - smoothstep(0.35, 1.0, r)) * 0.25;
                float vert = 1.0 - smoothstep(0.25, 1.0, abs(y));
                float k = saturate(blob * vert * up * i.size.z * _Strength);
                return half4((1.0 - k).xxx, 1);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
