// Night sky for RenderSettings.skybox (set up by Atmosphere; storm textures assigned by SkyFx).
//
// Two paths (uniform branch on _UseSkyTex):
//  * Blender storm sky (outdoor city zones): a 4K equirectangular volumetric storm deck rendered in Blender
//    (blender/fx/scripts/sky_pano.py; RGB radiance, A = how much the deck lights up when lightning fires), drifting
//    very slowly; distant cloud-to-ground bolts from the lightning atlas behind a far-far megacity silhouette band
//    (sky_horizon.py; premultiplied RGBA strip -3..12 deg); a faint distant rain veil; two parallax layers of fast
//    low scud (sky_clouds.py; tileable, R lit-from-below, G lit-from-above, B ambient, A coverage) whose underside
//    takes the city glow of the deck's horizon in the same azimuth; lightning lights the deck and the scud around
//    the strike direction.
//  * Procedural fallback (no textures): the prototype's gradient, horizon glow, fbm clouds, storm pockets, flash.
//
// Panorama mapping: u = 0.5 + atan2(d.x, d.z) / 2pi (u 0.5 = +Z, 0.75 = +X), v = 0.5 + asin(d.y) / pi.
// Globals (Weather -> SkyFx): _EOA_LightningDir xyz = strike direction (unit, world), w = flash 0..~1.5;
// _EOA_LightningBolt x = atlas column 0..3, y = bolt visibility 0..1, z = half width (rad), w = top elevation (rad);
// _EOA_RainAmount 0..1 (CityFx).
Shader "EOA/Sky"
{
    Properties
    {
        _Top ("Top", Color) = (0.04, 0.08, 0.13, 1)
        _Horizon ("Horizon", Color) = (0.1, 0.16, 0.22, 1)
        _Bottom ("Bottom", Color) = (0.02, 0.03, 0.04, 1)
        _Glow ("Horizon Glow", Color) = (0.16, 0.23, 0.31, 1)
        _GlowStrength ("Glow Strength", Float) = 0.5
        _Storm ("Storm", Float) = 0
        _Stars ("Stars", Float) = 0
        _Flash ("Lightning Flash", Float) = 0
        _CityGlow ("City Light Pollution", Color) = (0, 0, 0, 1)
        _CityGlowStrength ("City Glow Strength", Float) = 0

        [Header(Blender storm sky)]
        _UseSkyTex ("Use Storm Textures", Float) = 0
        [NoScaleOffset] _SkyTex ("Storm Deck Panorama (RGB, A flash response)", 2D) = "black" {}
        _SkyExposure ("Deck Exposure", Float) = 0.5
        _SkyTint ("Deck Tint", Color) = (1, 1, 1, 1)
        _SkySaturation ("Deck Saturation", Float) = 1
        _SkyDrift ("Deck Drift (turns per second)", Float) = 0.00001
        _SkyBelow ("Below-horizon colour", Color) = (0.012, 0.016, 0.026, 1)
        [NoScaleOffset] _CloudTex ("Scud Layer (R below-lit, G above-lit, B ambient, A coverage)", 2D) = "black" {}
        _CloudParams ("Scud: scale, opacity, plane bias, horizon fade", Vector) = (0.36, 0.55, 0.12, 0.3)
        _CloudWind ("Scud wind: layer A uv/s (xy), layer B (zw)", Vector) = (0.0045, 0.0016, 0.0026, 0.0011)
        _CloudLight ("Scud light: city, ambient, flash, darken", Vector) = (0.5, 0.004, 2.4, 0.85)
        [NoScaleOffset] _BandTex ("Far City Band (premultiplied RGBA)", 2D) = "black" {}
        _BandParams ("Band: lat min deg, lat max deg, light, alpha", Vector) = (-3, 12, 1, 1)
        [NoScaleOffset] _BoltTex ("Lightning Bolts (4 columns)", 2D) = "black" {}
        _FlashColor ("Flash Colour", Color) = (0.62, 0.68, 0.95, 1)
        _RainVeil ("Distant Rain Veil", Float) = 1
    }
    SubShader
    {
        Tags { "Queue"="Background" "RenderType"="Background" "PreviewType"="Skybox" "RenderPipeline"="UniversalPipeline" }
        Cull Off ZWrite Off

        Pass
        {
            HLSLPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"

            #define EOA_INV_PI 0.3183098862
            #define EOA_INV_2PI 0.1591549431
            #define EOA_2PI 6.2831853072

            TEXTURE2D(_SkyTex); SAMPLER(sampler_SkyTex);
            TEXTURE2D(_CloudTex); SAMPLER(sampler_CloudTex);
            TEXTURE2D(_BandTex); SAMPLER(sampler_BandTex);
            TEXTURE2D(_BoltTex); SAMPLER(sampler_BoltTex);

            CBUFFER_START(UnityPerMaterial)
            half4 _Top, _Horizon, _Bottom, _Glow;
            float _GlowStrength, _Storm, _Stars, _Flash;
            half4 _CityGlow;
            float _CityGlowStrength;
            float _UseSkyTex, _SkyExposure, _SkySaturation, _SkyDrift, _RainVeil;
            half4 _SkyTint, _SkyBelow, _FlashColor;
            float4 _CloudParams, _CloudWind, _CloudLight, _BandParams;
            CBUFFER_END

            // Globals (Weather / SkyFx / CityFx).
            float4 _EOA_LightningDir;
            float4 _EOA_LightningBolt;
            float _EOA_RainAmount;

            struct Attributes { float4 positionOS : POSITION; UNITY_VERTEX_INPUT_INSTANCE_ID };
            struct Varyings { float4 positionCS : SV_POSITION; float3 dir : TEXCOORD0; UNITY_VERTEX_OUTPUT_STEREO };

            Varyings vert(Attributes v)
            {
                Varyings o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.positionCS = TransformObjectToHClip(v.positionOS.xyz);
                o.dir = v.positionOS.xyz;
                return o;
            }

            float h(float2 p) { return frac(sin(dot(p, float2(12.9898, 78.233))) * 43758.5453); }
            float n2(float2 p)
            {
                float2 i = floor(p), f = frac(p);
                f = f * f * (3.0 - 2.0 * f);
                return lerp(lerp(h(i), h(i + float2(1, 0)), f.x), lerp(h(i + float2(0, 1)), h(i + float2(1, 1)), f.x), f.y);
            }
            float fbm(float2 p)
            {
                float s = 0.0, a = 0.5;
                [unroll] for (int i = 0; i < 5; i++) { s += a * n2(p); p *= 2.03; a *= 0.5; }
                return s;
            }

            // ------------------------------------------------------------------ procedural fallback (prototype)
            float3 ProceduralSky(float3 d)
            {
                float y = d.y;
                float t = _Time.y;
                float3 col = y > 0.0 ? lerp(_Horizon.rgb, _Top.rgb, pow(saturate(y), 0.55)) : lerp(_Horizon.rgb, _Bottom.rgb, saturate(-y * 4.0));
                col += _Glow.rgb * exp(-abs(y) * 9.0) * _GlowStrength;
                float2 cp = d.xz / max(0.08, y + 0.15) * 0.6 + float2(t * 0.004, t * 0.002);
                float cl = fbm(cp * 1.5);
                float cloudMask = smoothstep(0.0, 0.35, y) * smoothstep(0.35, 0.75, cl);
                col = lerp(col, _Horizon.rgb * 1.25 + _Glow.rgb * 0.08, cloudMask * 0.55);
                if (_CityGlowStrength > 0.0)
                {
                    float low = exp(-max(y, 0.0) * 7.0) * smoothstep(-0.02, 0.04, y);
                    float under = smoothstep(0.25, 0.85, fbm(cp * 0.9 + 7.3));
                    float dome = exp(-max(y, 0.0) * 3.0) * smoothstep(-0.05, 0.02, y);
                    col += _CityGlow.rgb * _CityGlowStrength * (low * (0.35 + 0.9 * under) + dome * 0.18);
                }
                if (_Storm > 0.5)
                {
                    float st = smoothstep(0.55, 0.8, fbm(d.xz * 3.0 + float2(t * 0.01, 0))) * exp(-abs(y - 0.08) * 12.0);
                    col += float3(0.25, 0.12, 0.45) * st * (0.4 + 0.6 * _Flash);
                }
                if (_Stars > 0.5 && y > 0.05)
                {
                    float2 sp = d.xz / (y + 0.4) * 140.0;
                    float star = step(0.9975, h(floor(sp))) * (1.0 - cloudMask) * smoothstep(0.05, 0.3, y);
                    col += star * (0.6 + 0.4 * sin(t * 2.0 + h(floor(sp)) * 40.0));
                }
                col += float3(0.55, 0.6, 0.75) * _Flash * (0.25 + cloudMask * 0.9) * smoothstep(-0.05, 0.3, y);
                return col;
            }

            // ------------------------------------------------------------------ Blender storm sky
            float3 DeckColor(float2 uv)
            {
                float3 c = SAMPLE_TEXTURE2D_LOD(_SkyTex, sampler_SkyTex, uv, 0).rgb;
                float l = dot(c, float3(0.2126, 0.7152, 0.0722));
                return lerp(l.xxx, c, _SkySaturation) * _SkyExposure * _SkyTint.rgb;
            }

            float3 StormSky(float3 d)
            {
                float t = _Time.y;
                float az = atan2(d.x, d.z);
                float lat = asin(clamp(d.y, -1.0, 1.0));
                float u = 0.5 + az * EOA_INV_2PI;
                float v = 0.5 + lat * EOA_INV_PI;
                float2 uvDeck = float2(u + frac(t * _SkyDrift), v);
                half4 deck = SAMPLE_TEXTURE2D_LOD(_SkyTex, sampler_SkyTex, uvDeck, 0);
                float l0 = dot(deck.rgb, float3(0.2126, 0.7152, 0.0722));
                float3 col = lerp(l0.xxx, deck.rgb, _SkySaturation) * _SkyExposure * _SkyTint.rgb;
                // below the horizon (seen only past the world's edge / from the rooftops): deep haze
                col = lerp(col, _SkyBelow.rgb + col * 0.35, smoothstep(0.0, -0.08, d.y));

                // zone light-pollution tint (AtmosphereSettings.CityGlow), kept subtle: the deck carries its own city glow
                float low = exp(-max(d.y, 0.0) * 7.0) * smoothstep(-0.02, 0.04, d.y);
                col += _CityGlow.rgb * _CityGlowStrength * low * 0.45;

                // lightning: lobe around the strike direction (the whole deck still pulses a little)
                float3 L = _EOA_LightningDir.xyz;
                float flash = max(_Flash, _EOA_LightningDir.w);
                float hasDir = step(0.5, dot(L, L));
                float lobe = hasDir > 0.0 ? pow(saturate(dot(d, L) * 0.5 + 0.5), 18.0) : 0.35;
                col += _FlashColor.rgb * flash * deck.a * (0.05 + 1.8 * lobe);

                // distant cloud-to-ground bolt (behind the far city)
                if (_EOA_LightningBolt.y > 0.001 && hasDir > 0.0)
                {
                    float dAz = az - atan2(L.x, L.z);
                    dAz -= EOA_2PI * round(dAz * EOA_INV_2PI);
                    float bx = dAz / max(_EOA_LightningBolt.z, 1e-3);
                    float by = (lat + 0.01) / (_EOA_LightningBolt.w + 0.01);
                    if (abs(bx) < 1.0 && by > 0.0 && by < 1.0)
                    {
                        float2 buv = float2((_EOA_LightningBolt.x + bx * 0.5 + 0.5) * 0.25, by);
                        half b = SAMPLE_TEXTURE2D_LOD(_BoltTex, sampler_BoltTex, buv, 0).r;
                        // sharp core, restrained glow (bloom adds the rest)
                        col += _FlashColor.rgb * (b * b * 1.6 + b * 0.15) * _EOA_LightningBolt.y;
                    }
                }

                // far-far megacity silhouette band (premultiplied; bolts and glow sit behind it)
                float bandV = (lat * 57.2957795 - _BandParams.x) / (_BandParams.y - _BandParams.x);
                if (bandV > 0.0 && bandV < 1.0)
                {
                    half4 band = SAMPLE_TEXTURE2D_LOD(_BandTex, sampler_BandTex, float2(u, bandV), 0);
                    col = col * (1.0 - band.a * _BandParams.w) + band.rgb * _BandParams.z * (1.0 + flash * 0.4);
                }

                // distant rain veil: faint falling streaks catching the city glow low on the horizon
                float rain = _EOA_RainAmount * _RainVeil;
                if (rain > 0.001)
                {
                    float hz = exp(-abs(lat) * 9.0) * smoothstep(-0.03, 0.01, d.y);
                    float s1 = n2(float2(u * 1400.0, v * 26.0 + t * 1.9));
                    float s2 = n2(float2(u * 900.0 + 17.0, v * 18.0 + t * 1.3));
                    float veil = smoothstep(0.55, 0.95, s1) * 0.6 + smoothstep(0.6, 0.98, s2) * 0.4;
                    float3 glow = DeckColor(float2(uvDeck.x, 0.503));
                    col += glow * veil * hz * rain * 0.35;
                }

                // scud: two planar layers of low cloud racing under the deck
                if (d.y > 0.0)
                {
                    float2 p = d.xz / (d.y + _CloudParams.z);
                    float2 uvA = p * _CloudParams.x + t * _CloudWind.xy;
                    float2 pb = float2(p.x * 0.8 - p.y * 0.6, p.x * 0.6 + p.y * 0.8);
                    float2 uvB = pb * _CloudParams.x * 1.85 + float2(0.37, 0.71) + t * _CloudWind.zw;
                    half4 ca = SAMPLE_TEXTURE2D(_CloudTex, sampler_CloudTex, uvA);
                    half4 cb = SAMPLE_TEXTURE2D(_CloudTex, sampler_CloudTex, uvB);
                    float fade = smoothstep(0.0, _CloudParams.w, d.y);
                    float aA = ca.a * fade * _CloudParams.y;
                    float aB = cb.a * fade * _CloudParams.y * 0.7;
                    float3 city = DeckColor(float2(uvDeck.x, 0.5 + 0.035));
                    city = lerp(dot(city, float3(0.2126, 0.7152, 0.0722)).xxx, city, 0.55);
                    // low clouds lit from below by the zone's own light pollution: the glow's hue at the deck's brightness
                    float lc = dot(city, float3(0.2126, 0.7152, 0.0722));
                    float3 gh = _CityGlow.rgb / max(dot(_CityGlow.rgb, float3(0.2126, 0.7152, 0.0722)), 1e-3);
                    city = lerp(city, lc * gh * 1.15, saturate(_CityGlowStrength * 1.6));
                    float3 amb = DeckColor(float2(uvDeck.x, 0.75)) * 0.6 + _CloudLight.yyy;
                    float3 fl = _FlashColor.rgb * flash * (0.08 + 2.0 * lobe) * _CloudLight.z;
                    float3 colB = city * cb.r * _CloudLight.x + amb * cb.b + fl * cb.g;
                    float3 colA = city * ca.r * _CloudLight.x + amb * ca.b + fl * ca.g;
                    // scud is darker than the deck behind it where it is thick (silhouetted), lit where thin
                    col = lerp(col, colB, aB * _CloudLight.w + aB * (1.0 - _CloudLight.w) * saturate(cb.r * 2.0));
                    col = lerp(col, colA, aA * _CloudLight.w + aA * (1.0 - _CloudLight.w) * saturate(ca.r * 2.0));
                }
                return col;
            }

            half4 frag(Varyings i) : SV_Target
            {
                float3 d = normalize(i.dir);
                float3 col = _UseSkyTex > 0.5 ? StormSky(d) : ProceduralSky(d);
                // tiny dither (the night gradients are very dark)
                col += (h(i.positionCS.xy + frac(_Time.y)) - 0.5) / 512.0;
                return half4(max(col, 0.0), 1.0);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
