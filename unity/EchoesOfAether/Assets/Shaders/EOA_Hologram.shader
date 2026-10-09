// Cyberpunk holographic advert / display: additive, scanlines, flicker, glitch (slice offsets, chromatic split,
// block dropouts) and procedural animated "ads" when no texture is assigned. Everything is invented: glyphs are
// hash-lit stroke grids (never real letters), logos are abstract geometry, no brands, no images.
// _Mode: 0 scrolling glyph columns, 1 pulsing rings emblem, 2 equaliser bars, 3 oscilloscope waveforms,
//        4 rotating abstract logo with orbiting dots, 5 headline glyphs + scrolling ticker band.
// _Seed varies each panel; _Aspect (width / height) keeps glyphs and emblems undistorted on any panel size.
// No keywords: fog uses the shared exp2 + city height fog helpers (EOA_CityFx.hlsl).
Shader "EOA/Hologram"
{
    Properties
    {
        _MainTex ("Content (optional)", 2D) = "black" {}
        _UseTex ("Use Texture", Float) = 0
        _Color ("Primary (HDR)", Color) = (1, 0.17, 0.84, 1)
        _Color2 ("Secondary (HDR)", Color) = (0, 0.9, 1, 1)
        _Intensity ("Intensity", Float) = 2.2
        _Seed ("Seed", Float) = 0
        _Mode ("Mode", Float) = 0
        _Scan ("Scanline Density", Float) = 180
        _Flicker ("Flicker", Range(0, 1)) = 0.25
        _Aspect ("Aspect (w/h)", Float) = 1.6
        _FogScale ("Fog Distance Scale", Float) = 1
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
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "EOA_CityFx.hlsl"

            TEXTURE2D(_MainTex); SAMPLER(sampler_MainTex);
            CBUFFER_START(UnityPerMaterial)
            float4 _MainTex_ST;
            half4 _Color, _Color2;
            float _UseTex, _Intensity, _Seed, _Mode, _Scan, _Flicker, _Aspect, _FogScale;
            CBUFFER_END

            struct Attributes { float4 positionOS : POSITION; float2 uv : TEXCOORD0; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct Varyings { float4 positionCS : SV_POSITION; float2 uv : TEXCOORD0; float3 posWS : TEXCOORD1; float eye : TEXCOORD2; UNITY_VERTEX_OUTPUT_STEREO };

            Varyings vert(Attributes v)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.posWS = TransformObjectToWorld(v.positionOS.xyz);
                o.positionCS = TransformWorldToHClip(o.posWS);
                o.eye = -TransformWorldToView(o.posWS).z;
                o.uv = v.uv;
                return o;
            }

            float h1(float n) { return frac(sin(n * 127.1 + _Seed * 311.7) * 43758.5453); }
            float h2(float2 p) { return frac(sin(dot(p, float2(12.9898, 78.233)) + _Seed * 17.13) * 43758.5453); }

            // Invented glyph: a 3x5 stroke grid lit by hash bits (never real letters); f = 0..1 inside the glyph cell.
            float Glyph(float2 f, float id)
            {
                if (any(f < 0) || any(f > 1)) return 0;
                float2 g = floor(f * float2(3, 5));
                float bit = step(0.42, h2(g + id * 7.3));
                // Keep a spine so glyphs read as characters, not noise.
                bit = max(bit, step(0.5, h1(id)) * step(g.x, 0.5) * step(0.5, g.y));
                float2 c = frac(f * float2(3, 5));
                return bit * step(0.14, c.x) * step(c.x, 0.86) * step(0.1, c.y) * step(c.y, 0.9);
            }

            // Row of n invented glyphs across a box (p in box space 0..1).
            float GlyphRow(float2 p, float n, float id)
            {
                float k = floor(p.x * n);
                float2 f = float2(frac(p.x * n) * 1.25 - 0.12, p.y);
                return Glyph(f, id + k * 3.1);
            }

            float Line(float d, float w) { return smoothstep(w, 0.0, abs(d)); }

            half3 Procedural(float2 uv, float t)
            {
                half3 a = _Color.rgb, b = _Color2.rgb;
                // Square-pixel coordinates centred on the panel.
                float2 p = (uv - 0.5) * float2(_Aspect, 1.0);
                half3 c = 0;
                if (_Mode < 0.5)
                {
                    float cols = max(3.0, floor(_Aspect * 4.0));
                    float col = floor(uv.x * cols);
                    float speed = 0.25 + h1(col) * 0.7;
                    float rows = 3.0 + floor(h1(col + 9) * 3.0);
                    float y = uv.y * rows + t * speed;
                    float id = floor(y) + col * 13;
                    float2 f = float2(frac(uv.x * cols) * 1.3 - 0.15, frac(y) * 1.2 - 0.1);
                    float head = step(0.82, frac(id * 0.137 + floor(t * 0.5) * 0.31));
                    c = lerp(a, b, h1(col + 3)) * Glyph(f, id) * (0.55 + head);
                    c += a * 0.05;
                }
                else if (_Mode < 1.5)
                {
                    float r = length(p);
                    float ang = atan2(p.y, p.x);
                    float rings = smoothstep(0.02, 0.0, abs(frac(r * 6 - t * 0.6) - 0.5) - 0.42) * saturate(1 - r * 1.8);
                    float arc = Line(r - 0.32, 0.012) * step(0.0, sin(ang * 3 + t * 2));
                    float ticks = Line(r - 0.4, 0.01) * step(0.7, frac(ang * 9.549 + t * 0.2));
                    c = b * rings + a * (arc + ticks);
                }
                else if (_Mode < 2.5)
                {
                    float bars = max(8.0, floor(_Aspect * 8.0));
                    float bi = floor(uv.x * bars);
                    float hgt = 0.15 + 0.75 * abs(sin(t * (1 + h1(bi) * 3) + h1(bi + 9) * 6));
                    float seg = step(0.25, frac(uv.y * 14.0));
                    float on = step(uv.y, hgt) * step(0.18, frac(uv.x * bars)) * seg;
                    c = lerp(b, a, uv.y) * on;
                    c += a * Line(frac(uv.y - t * 0.25) - 0.5, 0.02) * 0.5;
                }
                else if (_Mode < 3.5)
                {
                    // Oscilloscope: three traces over a faint grid.
                    float2 g = abs(frac(uv * float2(_Aspect * 6.0, 6.0)) - 0.5);
                    c = b * 0.06 * step(0.46, max(g.x, g.y));
                    [unroll] for (int k = 0; k < 3; k++)
                    {
                        float fk = k;
                        float fr = 3.0 + h1(fk + 1) * 9.0;
                        float y = 0.5 + (0.12 + 0.1 * fk) * sin(uv.x * fr * _Aspect + t * (1.2 + fk * 0.7) + h1(fk) * 6.0)
                                     * (0.6 + 0.4 * sin(uv.x * 2.0 + t * 0.4 + fk));
                        float w = 0.008 + 0.012 * fwidth(y) * 40.0;
                        c += (k == 1 ? a : b) * (Line(uv.y - y, w) + Line(uv.y - y, w * 6.0) * 0.25);
                    }
                }
                else if (_Mode < 4.5)
                {
                    // Abstract logo: rotating polygon outline, counter-rotating inner triangle, orbiting dots, a glyph line.
                    float sides = 3.0 + floor(h1(2) * 4.0);
                    float rot = t * 0.35;
                    float2 q = float2(cos(rot) * p.x - sin(rot) * p.y, sin(rot) * p.x + cos(rot) * p.y);
                    float an = atan2(q.y, q.x);
                    float sector = 6.2831853 / sides;
                    float pr = cos(floor(0.5 + an / sector) * sector - an) * length(q);
                    float poly = Line(pr - 0.28, 0.012);
                    float2 q2 = float2(cos(-rot * 2.0) * p.x - sin(-rot * 2.0) * p.y, sin(-rot * 2.0) * p.x + cos(-rot * 2.0) * p.y);
                    float an2 = atan2(q2.y, q2.x);
                    float pr2 = cos(floor(0.5 + an2 / 2.0944) * 2.0944 - an2) * length(q2);
                    float tri = Line(pr2 - 0.13, 0.01);
                    float dots = 0;
                    [unroll] for (int k = 0; k < 4; k++)
                    {
                        float aa = t * (0.8 + k * 0.3) + k * 1.57;
                        float2 dp = p - float2(cos(aa), sin(aa)) * (0.36 + 0.02 * k);
                        dots += smoothstep(0.02, 0.0, length(dp));
                    }
                    float pulse = 0.6 + 0.4 * sin(t * 2.0);
                    c = a * poly * (0.8 + 0.4 * pulse) + b * tri + b * dots;
                    c += a * 0.12 * smoothstep(0.3, 0.0, length(p)) * pulse;
                    if (_Aspect > 1.2)
                    {
                        float2 gp = float2((uv.x - 0.5) * _Aspect / 0.9 + 0.5, (uv.y - 0.06) / 0.12);
                        c += b * GlyphRow(gp, 6.0, floor(h1(4) * 50.0)) * step(0.0, gp.y) * step(gp.y, 1.0) * 0.8;
                    }
                }
                else
                {
                    // Headline glyphs that type on and blink, a colour sweep and a ticker band.
                    float n = 3.0 + floor(h1(5) * 3.0);
                    float2 hp = float2((uv.x - 0.08) / 0.84, (uv.y - 0.42) / 0.42);
                    float typed = step(floor(hp.x * n), fmod(floor(t * 3.0), n + 4.0));
                    float head = GlyphRow(hp, n, floor(t * 0.25) * 17.0) * typed * step(0.0, hp.y) * step(hp.y, 1.0);
                    float sweep = smoothstep(0.0, 0.4, 1.0 - abs(frac(uv.x * 0.6 - t * 0.15) - 0.5) * 2.0);
                    c = lerp(a, b, sweep) * head;
                    float band = step(0.08, uv.y) * step(uv.y, 0.26);
                    float2 tp = float2(frac(uv.x * _Aspect * 0.18 + t * 0.12), (uv.y - 0.1) / 0.14);
                    c += b * GlyphRow(tp, 4.0, floor(uv.x * _Aspect * 0.18 + t * 0.12) * 5.0) * band * 0.9;
                    c += a * band * 0.08 + a * Line(uv.y - 0.3, 0.004) * 0.6;
                }
                return c;
            }

            half4 frag(Varyings i) : SV_Target
            {
                float t = _Time.y + _Seed * 3.17;
                float2 uv = i.uv;
                // Glitch windows: slice offsets, chromatic split, block dropouts.
                float slice = floor(uv.y * 24);
                float burst = step(0.92, h1(floor(t * 2.3)));
                float glitchOn = step(0.9 - burst * 0.4, h1(floor(t * 7) + slice * 0.37));
                uv.x += (h1(slice + floor(t * 13)) - 0.5) * 0.08 * glitchOn;
                half3 c;
                if (_UseTex > 0.5) c = SAMPLE_TEXTURE2D(_MainTex, sampler_MainTex, TRANSFORM_TEX(uv, _MainTex)).rgb * _Color.rgb;
                else
                {
                    c = Procedural(uv, t);
                    if (burst * glitchOn > 0.5)
                    {
                        half3 shifted = Procedural(uv + float2(0.012, 0), t);
                        c = half3(shifted.r, c.g, c.b * 1.2);
                    }
                }
                float block = step(0.985, h2(floor(uv * float2(10, 6)) + floor(t * 9)));
                c *= 1 - block * 0.85;
                // Scanlines, edge falloff, frame, flicker.
                float scan = 0.7 + 0.3 * sin(i.uv.y * _Scan + t * 8);
                float2 e = min(i.uv, 1 - i.uv);
                float frame = smoothstep(0.0, 0.012, min(e.x, e.y)) * (1 - smoothstep(0.012, 0.024, min(e.x, e.y)));
                float edge = smoothstep(0.0, 0.06, min(e.x, e.y));
                float flicker = 1 - _Flicker * step(0.97, h1(floor(t * 20))) * 0.8 - _Flicker * 0.08 * sin(t * 50);
                half3 col = (c * scan * edge + _Color2.rgb * frame * 0.6) * _Intensity * flicker;
                // Fog (skyline adverts use a smaller scale so they glow through the haze like the lit windows).
                col *= EOA_UnityFogKeep(i.eye * _FogScale) * (1.0 - EOA_HeightFogAmount(_WorldSpaceCameraPos.xyz, i.posWS) * saturate(_FogScale * 2.0));
                return half4(col, 1);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
