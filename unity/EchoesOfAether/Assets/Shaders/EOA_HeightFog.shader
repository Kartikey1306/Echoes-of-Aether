// Screen-space exponential height fog for the open city: one full-screen quad drawn by CityFx right after the
// opaques and the sky (queue 2990, before every transparent). Reconstructs the world position from the camera
// depth texture and integrates an exponential density that thins with height, so streets and tower bases sink
// into a glowing haze while tower tops stand clear: the layered skyline depth. Haze colour picks up the city glow
// toward the brightest district and the lit-from-below street mist. All parameters are globals (EOA_CityFx.hlsl).
Shader "EOA/HeightFog"
{
    Properties
    {
        _Drift ("Drift Noise", Range(0, 1)) = 0.35
        _RainVeil ("Distant Rain Veil", Range(0, 2)) = 1
    }
    SubShader
    {
        Tags { "Queue"="Transparent-10" "RenderType"="Transparent" "IgnoreProjector"="True" "RenderPipeline"="UniversalPipeline" }
        Pass
        {
            Name "HeightFog"
            Tags { "LightMode"="UniversalForward" }
            Blend SrcAlpha OneMinusSrcAlpha
            ZWrite Off
            ZTest Always
            Cull Off

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"
            #include "EOA_CityFx.hlsl"

            CBUFFER_START(UnityPerMaterial)
            float _Drift, _RainVeil;
            CBUFFER_END

            // value noise periodic in x (period in cells): the veil wraps around the view without a seam
            float PNoise(float2 p, float period)
            {
                float2 i = floor(p), f = frac(p);
                f = f * f * (3.0 - 2.0 * f);
                float x0 = i.x - period * floor(i.x / period), x1 = x0 + 1.0 - period * floor((x0 + 1.0) / period);
                float a = EOA_Hash21(float2(x0, i.y)), b = EOA_Hash21(float2(x1, i.y));
                float c = EOA_Hash21(float2(x0, i.y + 1.0)), d = EOA_Hash21(float2(x1, i.y + 1.0));
                return lerp(lerp(a, b, f.x), lerp(c, d, f.x), f.y);
            }

            struct Attributes { float4 positionOS : POSITION; };
            struct Varyings { float4 positionCS : SV_POSITION; };

            Varyings vert(Attributes v)
            {
                Varyings o;
                // The mesh is a unit quad in clip space: cover the whole target regardless of the draw matrix.
                o.positionCS = float4(v.positionOS.xy * 2.0, UNITY_NEAR_CLIP_VALUE, 1.0);
                return o;
            }

            half4 frag(Varyings i) : SV_Target
            {
                if (_EOA_HFog.x <= 0.0) return 0;
                float2 uv = i.positionCS.xy / _ScaledScreenParams.xy;
                float raw = SampleSceneDepth(uv);
                #if UNITY_REVERSED_Z
                    float depth = raw;
                    bool sky = raw <= 1e-6;
                #else
                    float depth = lerp(UNITY_NEAR_CLIP_VALUE, 1, raw);
                    bool sky = raw >= 0.999999;
                #endif
                float3 cam = _WorldSpaceCameraPos.xyz;
                float3 wp = ComputeWorldSpacePosition(uv, depth, UNITY_MATRIX_I_VP);
                float3 dir = normalize(wp - cam);
                if (sky) wp = cam + dir * 4000.0;
                float amt = EOA_HeightFogAmount(cam, wp);
                // Slow drifting fog banks on surfaces (cheap 2D noise on the hit point).
                float n = EOA_Noise2(wp.xz * 0.018 + _Time.y * float2(0.012, 0.007));
                amt *= lerp(1.0, 0.7 + 0.6 * n, _Drift * (sky ? 0.0 : 1.0));
                float3 col = EOA_HeightFogColor(dir, wp.y);
                // Distant rain veil: fine falling sheets in the haze past ~15 m (direction-space noise, so it stays put
                // when the camera turns), denser where the haze is thick and lit; the near rain is real streaks.
                float rain = _EOA_RainAmount * _RainVeil;
                if (rain > 0.001)
                {
                    float far = smoothstep(14.0, 50.0, length(wp - cam)) * (1.0 - smoothstep(0.25, 0.7, abs(dir.y)));
                    float u = atan2(dir.x, dir.z) * 0.15915494 + 0.5;
                    float t = _Time.y;
                    float s1 = PNoise(float2(u * 1100.0 + dir.y * 40.0, dir.y * 7.0 + t * 2.4), 1100.0);
                    float s2 = PNoise(float2(u * 700.0 + 13.0 + dir.y * 26.0, dir.y * 4.5 + t * 1.6), 700.0);
                    float veil = smoothstep(0.5, 0.92, s1) * 0.6 + smoothstep(0.55, 0.95, s2) * 0.4;
                    float k = veil * rain * far;
                    amt = saturate(amt * (1.0 + 0.9 * k) + 0.035 * k);
                }
                return half4(col, saturate(amt));
            }
            ENDHLSL
        }
    }
    Fallback Off
}
