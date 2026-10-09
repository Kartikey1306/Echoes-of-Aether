// Shared helpers for the city lighting / atmosphere shaders (EOA/HeightFog, EOA/CityFx, EOA/Hologram,
// EOA/CityLights). All parameters are GLOBAL shader properties driven by CityFx.cs / Weather.cs, so every
// zone that never sets them gets the neutral defaults (no height fog, no neon list, dry).
//
//   _EOA_HFog        x density at the base height (1/m), y height falloff (1/m), z base height (m), w start distance (m)
//   _EOA_HFogColor   rgb haze colour (linear), a max opacity
//   _EOA_HFogGlow    rgb glow colour toward _EOA_HFogGlowDir and near the horizon, a glow strength
//   _EOA_HFogGlowDir xyz unit direction of the brightest city glow (Unity space), w ground glow (lit-from-below haze)
//   _EOA_NeonPos[8]  xyz position of the nearest neon emitters (street lamps, signs), w radius (m)
//   _EOA_NeonCol[8]  rgb colour (linear, intensity folded in)
//   _EOA_NeonCount   active entries
//   _EOA_Wetness     0 dry .. 1 soaked (for road / puddle shaders)
//   _EOA_RainAmount  current rain density 0..1 (rain veil in the fog, rain in the lamp cones)
#ifndef EOA_CITYFX_INCLUDED
#define EOA_CITYFX_INCLUDED

float4 _EOA_HFog;
float4 _EOA_HFogColor;
float4 _EOA_HFogGlow;
float4 _EOA_HFogGlowDir;
float4 _EOA_NeonPos[8];
float4 _EOA_NeonCol[8];
float _EOA_NeonCount;
float _EOA_Wetness;
float _EOA_RainAmount;

// Analytic exponential height fog along the ray camera -> world point. Returns the fog opacity 0..max.
float EOA_HeightFogAmount(float3 camPos, float3 worldPos)
{
    float density = _EOA_HFog.x;
    if (density <= 0.0) return 0.0;
    float3 rd = worldPos - camPos;
    float dist = length(rd);
    float3 dir = rd / max(dist, 1e-4);
    float start = _EOA_HFog.w;
    float d = max(dist - start, 0.0);
    float h0 = camPos.y + dir.y * min(start, dist) - _EOA_HFog.z;
    float k = _EOA_HFog.y;
    float ky = k * dir.y;
    // integral of density * exp(-k (h0 + t dir.y)) dt over [0, d]
    float base = density * exp(-k * max(h0, -40.0));
    float tau = abs(ky) > 1e-4 ? base * (1.0 - exp(min(-ky * d, 80.0))) / ky : base * d;
    return min(1.0 - exp(-max(tau, 0.0)), _EOA_HFogColor.a);
}

// Haze colour seen along a view direction (glow toward the brightest district, brighter near the horizon and
// low down where the streets light the mist from below).
float3 EOA_HeightFogColor(float3 dir, float worldY)
{
    float3 c = _EOA_HFogColor.rgb;
    float horizon = exp(-abs(dir.y) * 6.0);
    float toward = saturate(dot(normalize(float3(dir.x, 0.0, dir.z) + 1e-5), _EOA_HFogGlowDir.xyz)) ;
    toward = toward * toward;
    float ground = _EOA_HFogGlowDir.w * exp(-max(worldY - _EOA_HFog.z, 0.0) * 0.035);
    return c * (1.0 + ground) + _EOA_HFogGlow.rgb * _EOA_HFogGlow.a * (horizon * (0.35 + 0.65 * toward) + ground * 0.4);
}

// Fog for additive / premultiplied transparent FX: scales emission down by the height fog in front of it.
float EOA_FxFogFade(float3 worldPos)
{
    return 1.0 - EOA_HeightFogAmount(_WorldSpaceCameraPos.xyz, worldPos);
}

// Unity exponential-squared fog without keyword variants (the outdoor zones always use FogMode.ExponentialSquared).
float EOA_UnityFogKeep(float viewDepth)
{
    float f = unity_FogParams.x * viewDepth;
    return saturate(exp2(-f * f));
}

// Sum of the nearest neon emitters' light at a point (rain streaks, steam and mist catching the signs).
float3 EOA_NeonLight(float3 worldPos)
{
    float3 sum = 0;
    int n = (int)_EOA_NeonCount;
    [unroll] for (int i = 0; i < 8; i++)
    {
        if (i < n)
        {
            float3 d = _EOA_NeonPos[i].xyz - worldPos;
            float r = _EOA_NeonPos[i].w;
            float att = saturate(1.0 - dot(d, d) / (r * r));
            sum += _EOA_NeonCol[i].rgb * att * att;
        }
    }
    return sum;
}

// Hashes / value noise shared by the city shaders.
float EOA_Hash11(float n) { return frac(sin(n * 127.1) * 43758.5453); }
float EOA_Hash21(float2 p) { return frac(sin(dot(p, float2(127.1, 311.7))) * 43758.5453); }
float EOA_Hash31(float3 p) { return frac(sin(dot(p, float3(127.1, 311.7, 74.7))) * 43758.5453); }
float EOA_Noise2(float2 p)
{
    float2 i = floor(p), f = frac(p);
    f = f * f * (3.0 - 2.0 * f);
    return lerp(lerp(EOA_Hash21(i), EOA_Hash21(i + float2(1, 0)), f.x), lerp(EOA_Hash21(i + float2(0, 1)), EOA_Hash21(i + float2(1, 1)), f.x), f.y);
}

#endif
