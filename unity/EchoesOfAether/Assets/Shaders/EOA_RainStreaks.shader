// GPU rain: a static mesh of N quads (RainField) animated entirely in the vertex shader. Every drop has a seed
// position in a box; drops fall with the wind velocity in WORLD space and wrap around a box that follows the camera
// (pushed forward along the view), so the rain is world-stable (walking through it reads correctly), costs no CPU
// and no particle simulation.
//
// Look (high-end rain: thin, short, motion-blurred streaks that only read where they are back-lit):
//   * streak length = fall speed x a short exposure with a per-drop jitter; width never drops under ~1 pixel (energy
//     conserving: thinner-than-a-pixel drops get wider and fainter instead of shimmering), so the far drops dissolve
//     into a fine sheen instead of drawing long lines;
//   * lighting is a forward-scattering phase function (Henyey-Greenstein, g ~0.7): a drop between the camera and a
//     lamp / sign lights up, the same drop against a dark wall nearly disappears. Sources: the URP Forward+ lamps, the
//     neon emitter field (EOA_CityFx.hlsl, per emitter so the phase works), the moon, lightning, and a very faint
//     ambient floor;
//   * travelling gust waves bend and push the drops (slant varies across the screen and over time), per-drop
//     sparkle, speed and length jitter;
//   * faded near the camera, at the box edges (before a drop wraps), by the city height fog and Unity fog.
//
// Passes: "Forward" (UniversalForward, the normal transparent queue) and "Late" (LightMode EOARainLate), drawn by
// RainLatePass after post-processing when TAA is on so the thin streaks are neither smeared nor suppressed by the
// temporal resolve; it tonemaps its own output (filmic shoulder) because it lands on the display-referred image.
// RainField enables exactly one of the two per material.
//
// Mesh layout: UV0.xy = corner (x -1..1 across, y 0 tail .. 1 head); UV1 = seed (xyz 0..1 position in the box,
// w 0..1 per-drop random: atlas column, speed / length jitter, sparkle and the _Amount cut-off).
Shader "EOA/RainStreaks"
{
    Properties
    {
        [NoScaleOffset] _BaseMap ("Streak Atlas (columns; R highlight, A coverage)", 2D) = "white" {}
        _Columns ("Atlas Columns", Float) = 8
        _Box ("Box size (m) xyz, forward offset (m) w", Vector) = (14, 14, 14, 5)
        _Velocity ("Fall velocity (m/s) xyz, speed jitter w", Vector) = (-2, -11, 0.8, 0.2)
        _Streak ("Exposure (s), width (m), min width (px), alpha", Vector) = (0.022, 0.0045, 1.0, 0.5)
        _Light ("Gain: ambient, neon, lights, moon", Vector) = (0.12, 1.0, 1.0, 0.25)
        _Fade ("Near start (m), near end (m), box edge start (0..1), far fade (m)", Vector) = (0.35, 1.6, 0.6, 0)
        _Gust ("Gust: amplitude (m/s), wavelength (1/m), speed (m/s), slant variation", Vector) = (1.6, 0.045, 6, 0.35)
        _Phase ("Scattering: g, forward gain, isotropic floor, sparkle", Vector) = (0.72, 0.42, 0.22, 1)
        _Amount ("Amount (fraction of drops)", Range(0, 1)) = 1
        _Tint ("Tint", Color) = (0.78, 0.84, 0.92, 1)
        _FlashGain ("Lightning Gain", Float) = 3
        _LateExposure ("Late pass exposure (display-referred)", Float) = 1.1
    }
    SubShader
    {
        Tags { "Queue"="Transparent+10" "RenderType"="Transparent" "IgnoreProjector"="True" "RenderPipeline"="UniversalPipeline" }

        HLSLINCLUDE
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
        #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/DeclareDepthTexture.hlsl"
        #include "EOA_CityFx.hlsl"

        TEXTURE2D(_BaseMap); SAMPLER(sampler_BaseMap);
        CBUFFER_START(UnityPerMaterial)
        float4 _Box, _Velocity, _Streak, _Light, _Fade, _Gust, _Phase;
        float _Columns, _Amount, _FlashGain, _LateExposure;
        half4 _Tint;
        CBUFFER_END

        float4 _EOA_LightningDir;

        struct Attributes
        {
            float4 positionOS : POSITION;
            float4 uv0 : TEXCOORD0;
            float4 uv1 : TEXCOORD1;
        };

        struct Varyings
        {
            float4 positionCS : SV_POSITION;
            float3 uv : TEXCOORD0;      // xy atlas, z across (-1..1)
            half4 color : TEXCOORD1;    // rgb light (premultiplied by alpha), a alpha
            float4 screen : TEXCOORD2;  // xyw screen position, z eye depth (late pass depth test)
        };

        // Henyey-Greenstein phase (x 4 pi): 1 for isotropic. cosTheta = cos(angle between light travel and view ray).
        float RainPhase(float cosTheta)
        {
            float g = _Phase.x;
            float d = max(1.0 + g * g - 2.0 * g * cosTheta, 1e-3);
            float hg = (1.0 - g * g) / (d * sqrt(d));
            return _Phase.z + hg * _Phase.y;
        }

        float3 AdditionalLightsAt(float3 p, float3 V, float4 positionCS)
        {
            float3 acc = 0;
            InputData inputData = (InputData)0;
            inputData.positionWS = p;
            float4 sp = ComputeScreenPos(positionCS);
            inputData.normalizedScreenSpaceUV = saturate(sp.xy / max(sp.w, 1e-4));
            uint count = GetAdditionalLightsCount();
            LIGHT_LOOP_BEGIN(count)
                Light l = GetAdditionalLight(lightIndex, p);
                // Scattering angle: light travels along -l.direction (lamp -> drop) and leaves toward the camera along V
                // (drop -> camera), so a drop in front of a lamp is the forward-scattering peak. Character-only lights
                // (the camera rig's key / fill / rim) never light the rain: lit from the lens, every drop in front of the
                // camera glowed alike and the rain read as a flat overlay on the screen.
                if ((l.layerMask & 1u) != 0)
                    acc += l.color * (l.distanceAttenuation * RainPhase(dot(-l.direction, V)));
            LIGHT_LOOP_END
            return acc;
        }

        // Neon emitter field with the same phase per emitter (signs behind the rain light it up).
        float3 NeonScatter(float3 p, float3 V)
        {
            float3 sum = 0;
            int n = (int)_EOA_NeonCount;
            [unroll] for (int i = 0; i < 8; i++)
            {
                if (i < n)
                {
                    float3 d = _EOA_NeonPos[i].xyz - p;
                    float r = _EOA_NeonPos[i].w * 1.6;
                    float dd = dot(d, d);
                    float att = saturate(1.0 - dd / (r * r));
                    float3 L = d * rsqrt(max(dd, 1e-4));
                    sum += _EOA_NeonCol[i].rgb * (att * att * RainPhase(dot(-L, V)));
                }
            }
            return sum;
        }

        Varyings RainVert(Attributes v)
        {
            Varyings o = (Varyings)0;
            float3 seed = v.uv1.xyz;
            float r = v.uv1.w;
            float r1 = frac(r * 7.13), r2 = frac(r * 3.71), r3 = frac(r * 13.37), r4 = frac(r * 5.17 + 0.31);
            float3 box = _Box.xyz;
            float3 vel = _Velocity.xyz * (1.0 + (r1 - 0.5) * 2.0 * _Velocity.w);
            float3 camPos = _WorldSpaceCameraPos.xyz;
            float3 fwd = -UNITY_MATRIX_V[2].xyz;
            float2 fh = fwd.xz / max(length(fwd.xz), 1e-3);
            float3 origin = camPos + float3(fh.x, 0, fh.y) * _Box.w;
            // world-anchored lattice of drops, wrapped into the box around the origin
            float3 p = seed * box + vel * _Time.y;
            p = origin + (frac((p - origin) / box + 0.5) - 0.5) * box;

            // Gusts: travelling waves along the wind push the drops sideways and bend the streaks (slant varies over
            // the screen and in time instead of every drop sharing one angle).
            float2 wdir = vel.xz / max(length(vel.xz), 0.3);
            float2 gp = p.xz * _Gust.y;
            float wave = dot(gp, wdir) - _Time.y * _Gust.z * _Gust.y;
            float g = sin(wave * 6.2831) * 0.6 + sin(wave * 2.7 + dot(gp, float2(-wdir.y, wdir.x)) * 3.1 + 1.3) * 0.4;
            float3 gust = float3(wdir.x, 0, wdir.y) * (_Gust.x * g) + float3(-wdir.y, 0, wdir.x) * (_Gust.x * _Gust.w * (r4 - 0.5));
            p += gust * 0.3;
            float3 fall = vel + gust;

            float3 toCam = camPos - p;
            float dist = length(toCam);
            float3 V = toCam / max(dist, 1e-4);
            float speed = max(length(fall), 1e-3);
            float3 dir = fall / speed;
            float len = speed * _Streak.x * (0.55 + 0.9 * r2);
            float3 side = cross(dir, V);
            side /= max(length(side), 1e-4);
            // pixel footprint at this distance
            float pixel = dist * 2.0 / (UNITY_MATRIX_P[1][1] * _ScreenParams.y);
            float w = _Streak.y * (0.7 + 0.6 * r3);
            // Drops within ~2.5 m of the lens are visibly bigger, softer and a little fainter (out of focus): the size
            // gradient from fat near streaks to hair-thin far ones is what reads as rain in 3D space.
            float nearK = saturate((2.2 - dist) / 1.6);
            w *= 1.0 + nearK * nearK * 1.8;
            float wMin = pixel * _Streak.z;
            float energy = w / max(w, wMin) * (1.0 - 0.4 * nearK);
            w = max(w, wMin);
            // a streak never gets shorter than ~3 px (sub-pixel lengths alias into dots)
            len = max(len, pixel * 3.0);
            float keep = step(r, _Amount);
            float3 pos = p - dir * (len * (1.0 - v.uv0.y)) + side * (w * 0.5 * v.uv0.x);
            pos = lerp(p, pos, keep);
            o.positionCS = TransformWorldToHClip(pos);
            o.screen = ComputeScreenPos(o.positionCS);
            o.screen.z = -TransformWorldToView(pos).z;

            // fades: near the camera, at the box edges (before a drop wraps), far, fog
            float3 rel = abs(p - origin) / (box * 0.5);
            float edge = max(rel.x, max(rel.y, rel.z));
            float fade = smoothstep(_Fade.x, _Fade.y, dist) * (1.0 - smoothstep(_Fade.z, 1.0, edge));
            if (_Fade.w > 0.0) fade *= 1.0 - smoothstep(_Fade.w * 0.5, _Fade.w, dist);
            float eye = -TransformWorldToView(p).z;
            fade *= EOA_FxFogFade(p) * EOA_UnityFogKeep(eye);

            // light: forward scattering dominates, so rain shows where it is back-lit
            float3 light = SampleSH(-V) * _Light.x;
            light += NeonScatter(p, V) * _Light.y;
            Light mainL = GetMainLight();
            light += mainL.color * (_Light.w * RainPhase(dot(-mainL.direction, V)));
            light += AdditionalLightsAt(p, V, o.positionCS) * _Light.z;
            light += float3(0.62, 0.68, 0.95) * (_EOA_LightningDir.w * _FlashGain);
            // per-drop sparkle (a few drops catch the light much more than their neighbours)
            light *= lerp(1.0, 0.35 + 1.5 * r4 * r4, _Phase.w);

            float a = _Streak.w * energy * fade * keep;
            o.color = half4(light * _Tint.rgb * a, a);
            float col = floor(frac(r * 13.37) * _Columns);
            o.uv = float3((col + v.uv0.x * 0.5 + 0.5) / _Columns, v.uv0.y, v.uv0.x);
            return o;
        }

        half4 RainFrag(Varyings i)
        {
            half4 tex = SAMPLE_TEXTURE2D(_BaseMap, sampler_BaseMap, i.uv.xy);
            // soft round profile across, tapered tail and a rounded head along (a motion-blurred drop, not a line)
            half x = i.uv.z;
            half across = saturate(1.0 - x * x);
            half y = i.uv.y;
            half along = smoothstep(0.0, 0.45, y) * smoothstep(1.0, 0.86, y);
            half cov = tex.a * across * along;
            half3 rgb = i.color.rgb * cov * (0.6 + 0.8 * tex.r) * (0.75 + 0.5 * y);
            // rain barely occludes: small alpha
            return half4(rgb, i.color.a * cov * 0.1);
        }
        ENDHLSL

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
            Varyings vert(Attributes v) { return RainVert(v); }
            half4 frag(Varyings i) : SV_Target { return RainFrag(i); }
            ENDHLSL
        }

        Pass
        {
            Name "Late"
            Tags { "LightMode"="EOARainLate" }
            Blend One OneMinusSrcAlpha
            ZWrite Off
            // no depth attachment after post (it may be upscaled): the depth test is done against the depth texture
            ZTest Always
            Cull Off

            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            Varyings vert(Attributes v) { return RainVert(v); }
            half4 frag(Varyings i) : SV_Target
            {
                float2 suv = i.screen.xy / max(i.screen.w, 1e-5);
                float scene = LinearEyeDepth(SampleSceneDepth(suv), _ZBufferParams);
                float vis = saturate((scene - i.screen.z) / 0.12);
                if (vis <= 0.0) discard;
                half4 c = RainFrag(i) * vis;
                // display-referred: soft filmic shoulder (premultiplied, so tonemap the colour and keep its alpha)
                half3 hdr = c.rgb * _LateExposure;
                c.rgb = hdr / (1.0 + hdr);
                return c;
            }
            ENDHLSL
        }
    }
    Fallback Off
}
