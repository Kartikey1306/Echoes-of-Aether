// City atmosphere effects in one premultiplied-alpha transparent shader (no keywords, one variant):
//   _Mode 0  light cone / god-ray volume under lamps and signs: soft view-angle edges, falloff from the source,
//            drifting dust, depth-faded where it meets the ground (no hard intersection lines)
//   _Mode 1  mist billboard (camera-facing from a centre in UV1): soft noisy blob tinted by the nearest neon
//   _Mode 2  beacon billboard: aircraft-warning blink (phase in UV1.w)
//   _Mode 3  haze curtain between skyline layers: vertical gradient glow, soft at the ends
//   _Mode 4  LED strip: running chase pulses along UV0.y (metres)
//   _Mode 5  particles (rain streaks / steam): texture alpha x vertex colour, lit by the nearest neon emitters
// Output is premultiplied (Blend One OneMinusSrcAlpha): alpha 0 = pure additive glow, alpha > 0 also occludes.
// Every mode fades with the city height fog and Unity's exp2 fog. Geometry is merged per cell in Unity space.
Shader "EOA/CityFx"
{
    Properties
    {
        _BaseMap ("Texture (particles)", 2D) = "white" {}
        _BaseColor ("Tint (HDR)", Color) = (1, 1, 1, 1)
        _Mode ("Mode", Float) = 0
        _Intensity ("Intensity", Float) = 1
        _Soft ("Depth Fade (m)", Float) = 1.5
        _Alpha ("Occlusion", Range(0, 1)) = 0
        _NeonGain ("Neon Light Gain", Float) = 1
        _NearFade ("Near Fade (m)", Float) = 2
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
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"
            #include "EOA_CityFx.hlsl"

            TEXTURE2D(_BaseMap); SAMPLER(sampler_BaseMap);
            CBUFFER_START(UnityPerMaterial)
            float4 _BaseMap_ST;
            half4 _BaseColor;
            float _Mode, _Intensity, _Soft, _Alpha, _NeonGain, _NearFade;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                half4 color : COLOR;
                float4 uv : TEXCOORD0;
                float4 uv1 : TEXCOORD1;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float3 posWS : TEXCOORD0;
                float3 normalWS : TEXCOORD1;
                half4 color : COLOR;
                float4 uv : TEXCOORD2;
                float4 extra : TEXCOORD3;   // mode-specific (billboard corner, phase)
                float eye : TEXCOORD4;      // linear eye depth
            };

            Varyings vert(Attributes v)
            {
                Varyings o = (Varyings)0;
                float3 ws = TransformObjectToWorld(v.positionOS.xyz);
                o.extra = 0;
                if (_Mode > 0.5 && _Mode < 2.5)
                {
                    // Billboard: UV1.xyz = centre (world), UV0.xy = corner (-1..1), UV0.z = half size (m).
                    float3 c = v.uv1.xyz;
                    float3 right = UNITY_MATRIX_V[0].xyz;
                    float3 up = UNITY_MATRIX_V[1].xyz;
                    if (_Mode < 1.5)
                    {
                        // Mist: keep the cards upright so they do not swim when the camera tilts.
                        up = float3(0, 1, 0);
                        right = normalize(cross(up, c - _WorldSpaceCameraPos.xyz + 1e-4));
                    }
                    ws = c + (right * v.uv.x + up * v.uv.y) * v.uv.z;
                    o.extra = float4(v.uv.xy, v.uv1.w, 0);
                    if (_Mode < 1.5) o.color.rgb = v.color.rgb + (half3)(EOA_NeonLight(c) * _NeonGain);
                }
                o.posWS = ws;
                o.positionCS = TransformWorldToHClip(ws);
                o.eye = -TransformWorldToView(ws).z;
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                if (!(_Mode > 0.5 && _Mode < 1.5)) o.color = v.color;
                else o.color.a = v.color.a;
                if (_Mode > 4.5) o.color.rgb = v.color.rgb * _BaseColor.rgb + (half3)(EOA_NeonLight(ws) * _NeonGain);
                o.uv = v.uv;
                o.uv.xy = _Mode > 4.5 ? TRANSFORM_TEX(v.uv.xy, _BaseMap) : v.uv.xy;
                return o;
            }

            float DepthFade(float4 positionCS, float eye, float soft)
            {
                float2 suv = positionCS.xy / _ScaledScreenParams.xy;
                float scene = LinearEyeDepth(SampleSceneDepth(suv), _ZBufferParams);
                return saturate((scene - eye) / max(soft, 1e-3));
            }

            half4 frag(Varyings i) : SV_Target
            {
                float t = _Time.y;
                float eye = i.eye;
                float fog = EOA_FxFogFade(i.posWS) * EOA_UnityFogKeep(eye);
                float near = saturate((eye - _NearFade * 0.35) / max(_NearFade, 1e-3));
                float3 rgb = 0;
                float a = 0;
                if (_Mode < 0.5)
                {
                    // Light cone: UV0.y 0 at the source, 1 at the far end.
                    float3 V = normalize(_WorldSpaceCameraPos.xyz - i.posWS);
                    float ndv = abs(dot(normalize(i.normalWS), V));
                    float edge = ndv * ndv;
                    float y = saturate(i.uv.y);
                    float fall = pow(1.0 - y, 1.7) * smoothstep(0.0, 0.06, y);
                    float dust = EOA_Noise2(i.posWS.xz * 1.3 + float2(i.posWS.y * 1.7 + t * 0.35, t * 0.9));
                    float body = edge * fall * (0.7 + 0.45 * dust);
                    // rain caught in the beam: thin falling streaks on view-aligned columns, only while it rains (the
                    // lamp light is where rain reads in high-end night scenes; dark rain elsewhere stays invisible)
                    float3 side = normalize(cross(float3(0, 1, 0), V) + 1e-5);
                    float sx = dot(i.posWS, side) * 24.0;
                    float col = floor(sx);
                    float sy = i.posWS.y * 0.8 + t * (9.0 + EOA_Hash11(col) * 4.0) + EOA_Hash11(col + 3.7) * 11.0;
                    float drop = smoothstep(0.7, 0.98, EOA_Noise2(float2(col * 1.37, sy))) * smoothstep(0.5, 0.15, abs(frac(sx) - 0.5));
                    float rainBeam = drop * _EOA_RainAmount * fall * (0.35 + 0.65 * ndv);
                    // forward scattering: looking up into the beam (toward the source) is brighter than across it; rain
                    // and mist thicken the medium
                    float phase = 0.75 + 1.1 * pow(saturate(-V.y), 2.0);
                    float medium = 1.0 + 0.6 * _EOA_RainAmount;
                    rgb = i.color.rgb * (body * phase * medium + rainBeam * 2.2) * DepthFade(i.positionCS, eye, _Soft);
                }
                else if (_Mode < 1.5)
                {
                    float2 q = i.extra.xy;
                    float r2 = dot(q, q);
                    float blob = saturate(1.0 - r2);
                    blob *= blob;
                    float n = EOA_Noise2(q * 1.6 + i.extra.z * 7.0 + float2(t * 0.05, -t * 0.03)) * 0.6
                            + EOA_Noise2(q * 3.4 - i.extra.z * 3.0 + float2(-t * 0.08, t * 0.04)) * 0.4;
                    float d = blob * saturate(n * 1.6 - 0.25) * i.color.a * DepthFade(i.positionCS, eye, _Soft);
                    rgb = i.color.rgb * d;
                    a = d * _Alpha;
                }
                else if (_Mode < 2.5)
                {
                    float2 q = i.extra.xy;
                    float r2 = dot(q, q);
                    float f = frac(t * 0.55 + i.extra.z);
                    float flash = exp(-f * 9.0) + 0.06;
                    float g = exp(-r2 * 14.0) * 1.6 + exp(-r2 * 3.5) * 0.3;
                    rgb = i.color.rgb * g * flash;
                    near = 1;
                }
                else if (_Mode < 3.5)
                {
                    float y = saturate(i.uv.y);
                    float ends = smoothstep(0.0, 0.12, i.uv.x) * smoothstep(1.0, 0.88, i.uv.x);
                    float3 V = normalize(_WorldSpaceCameraPos.xyz - i.posWS);
                    float ndv = abs(dot(normalize(i.normalWS), V));
                    float shimmer = 0.85 + 0.15 * EOA_Noise2(float2(i.posWS.x * 0.01 + i.posWS.z * 0.01 + t * 0.02, y * 3.0));
                    rgb = i.color.rgb * pow(1.0 - y, 2.2) * ends * (0.4 + 0.6 * ndv) * shimmer * DepthFade(i.positionCS, eye, _Soft);
                    near = 1;
                }
                else if (_Mode < 4.5)
                {
                    float p = frac(i.uv.y * 0.015 - t * (0.25 + i.uv.x * 0.2) + i.uv.x * 5.3);
                    float pulse = exp(-p * 18.0) * 2.5 + exp(-frac(p + 0.5) * 30.0) * 0.8;
                    rgb = i.color.rgb * (0.35 + pulse);
                    near = 1;
                }
                else
                {
                    half4 tex = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, i.uv.xy);
                    float d = tex.a * i.color.a * _BaseColor.a * DepthFade(i.positionCS, eye, _Soft);
                    rgb = i.color.rgb * tex.rgb * d;
                    a = d * _Alpha;
                }
                float k = _Intensity * fog * near;
                return half4(rgb * k, a * near * fog);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
