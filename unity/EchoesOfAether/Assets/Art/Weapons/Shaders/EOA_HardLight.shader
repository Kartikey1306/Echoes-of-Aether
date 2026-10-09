// Hard-light weapon energy (Kael's blade, Giva's claws, Aether bolts, muzzle flashes, impact bursts). Additive HDR.
// Meshes come from blender/weapons/w_fx.py: uv.x = around the section, uv.y = along the length (0 base, 1 tip);
// vertex colour R = cutting-edge weight, G = spine weight, B = part (0 hull, 1 core, 0.5 burst).
//  _Mode 0  blade / claw hull: fresnel rim, glowing cutting edge, flowing streaks, a parallax inner layer that shifts
//           with the view (reads as depth / refraction inside the light), base-to-tip emissive gradient.
//  _Mode 1  inner core: white-hot, pulsing.
//  _Mode 2  projectile hull: fresnel crystal, tail fades out (uv.y 0 = tail).
//  _Mode 3  flash / impact burst: per-spike intensity (R) fading towards the tips, hot centre.
// _Extend (0..1) clips the mesh along uv.y with a bright forming front, so blades and claws grow out of the emitter.
Shader "EOA/HardLight"
{
    Properties
    {
        [HDR] _Color ("Color", Color) = (0.37, 0.85, 1, 1)
        [HDR] _CoreColor ("Core", Color) = (0.85, 0.97, 1, 1)
        _Intensity ("Intensity", Float) = 1
        _Alpha ("Alpha", Range(0, 1)) = 1
        _Extend ("Extend", Range(0, 1)) = 1
        _Fresnel ("Fresnel Power", Float) = 2.4
        _EdgeBoost ("Edge Boost", Float) = 1.4
        _Flow ("Flow Speed", Float) = 2.2
        _NoiseScale ("Noise Scale", Float) = 9
        _Parallax ("Parallax Depth", Float) = 0.035
        _Mode ("Mode", Float) = 0
        _Seed ("Seed", Float) = 0
        [Enum(UnityEngine.Rendering.CullMode)] _Cull ("Cull", Float) = 2
    }
    SubShader
    {
        Tags { "Queue"="Transparent+10" "RenderType"="Transparent" "IgnoreProjector"="True" "RenderPipeline"="UniversalPipeline" }
        Blend One One
        ZWrite Off
        Cull [_Cull]

        Pass
        {
            Name "Forward"
            Tags { "LightMode"="UniversalForward" }
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_fog
            #pragma multi_compile_instancing
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            CBUFFER_START(UnityPerMaterial)
            half4 _Color, _CoreColor;
            float _Intensity, _Alpha, _Extend, _Fresnel, _EdgeBoost, _Flow, _NoiseScale, _Parallax, _Mode, _Seed, _Cull;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float2 uv : TEXCOORD0;
                half4 color : COLOR;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };
            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 positionWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                float3 positionOS : TEXCOORD2;
                float3 viewOS : TEXCOORD3;
                float2 uv : TEXCOORD4;
                half4 color : TEXCOORD5;
                float fog : TEXCOORD6;
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
                o.viewOS = TransformWorldToObjectDir(GetWorldSpaceViewDir(p.positionWS), false);
                o.uv = v.uv;
                o.color = v.color;
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
                float t = _Time.y * _Flow + _Seed * 7.31;
                float3 n = normalize(i.normalWS);
                float3 vw = normalize(GetWorldSpaceViewDir(i.positionWS));
                float ndv = saturate(abs(dot(n, vw)));
                float fres = pow(1.0 - ndv, _Fresnel);
                float v = i.uv.y;
                float edge = i.color.r, spine = i.color.g;
                float3 c;
                // extend clip with a forming front
                float ext = saturate((_Extend - v) / 0.012 + 0.5);
                float front = (_Extend < 0.995) ? exp(-pow((_Extend - v) / 0.03, 2.0)) : 0.0;
                if (ext <= 0.0) discard;

                if (_Mode < 0.5)
                {
                    // flowing streaks along the blade, a parallax inner layer, and a hot cutting edge
                    float s1 = noise3(float3(i.uv.x * 6.0, v * _NoiseScale - t, _Seed));
                    float s2 = noise3(float3(i.uv.x * 11.0 + 3.0, v * _NoiseScale * 2.3 - t * 1.7, _Seed + 5.0));
                    float streak = smoothstep(0.55, 0.95, s1 * 0.6 + s2 * 0.5);
                    float3 qp = (i.positionOS - normalize(i.viewOS) * _Parallax) * 60.0;
                    float inner = noise3(qp + float3(0, 0, -t * 1.3)) * noise3(qp * 1.9 + float3(t, 0, 0));
                    inner = smoothstep(0.15, 0.6, inner);
                    float grad = lerp(1.25, 0.85, v) + 0.6 * smoothstep(0.92, 1.0, v);   // bright emitter end, hot tip
                    float body = 0.22 + 0.25 * streak + 0.42 * inner;
                    float rim = fres * 1.1;
                    // white-hot only on the cutting-edge line; the spine just gets a little more body colour
                    float hot = smoothstep(0.78, 1.0, edge) * _EdgeBoost * (0.75 + 0.25 * s2);
                    c = _Color.rgb * (body + rim + spine * 0.35) * grad + _CoreColor.rgb * (hot * 0.9 + front * 3.0);
                }
                else if (_Mode < 1.5)
                {
                    float pulse = 0.85 + 0.15 * sin(t * 6.0 + v * 20.0);
                    float n1 = noise3(float3(i.uv.x * 4.0, v * _NoiseScale - t * 1.5, _Seed + 9.0));
                    c = _CoreColor.rgb * (0.9 + 0.5 * n1) * pulse * (1.25 - 0.5 * fres) + _CoreColor.rgb * front * 2.0;
                }
                else if (_Mode < 2.5)
                {
                    float tail = smoothstep(0.0, 0.75, v);
                    float n1 = noise3(float3(i.uv.x * 5.0, v * 6.0 - t * 3.0, _Seed));
                    c = _Color.rgb * (0.25 + 1.8 * fres + 0.5 * edge + 0.35 * n1) * tail + _CoreColor.rgb * fres * 0.3 * tail;
                }
                else
                {
                    float fade = pow(saturate(1.0 - v), 1.6);
                    float hotc = smoothstep(0.35, 0.0, v);
                    c = lerp(_Color.rgb, _CoreColor.rgb, hotc) * edge * fade * (0.6 + 0.6 * fres + 0.6 * ndv);
                }
                c *= _Intensity * _Alpha * ext;
                c = MixFogColor(c, half3(0, 0, 0), i.fog);
                return half4(c, 1.0);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
