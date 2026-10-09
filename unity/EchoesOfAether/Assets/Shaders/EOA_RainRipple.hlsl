// Rain surface helpers for road / puddle / wall / glass shaders. All inputs are GLOBAL shader properties set every
// frame by Weather (RainField.PublishGlobals); zones without rain leave the strengths at 0 so every function returns
// a flat normal (0, 0, 1) and costs nothing visible.
//
//   _EOA_RainRipple          Texture2D  puddle ripple NORMAL flipbook (Blender/numpy: blender/fx/scripts/rain_ripples.py),
//                                       1024^2, 4x4 frames (frame i: column i % 4, row i / 4 counted from the TOP),
//                                       each frame tiles; 16 frames loop.
//   _EOA_RainRippleParams    float4     x frame position (0..16, continuous: frac = blend to the next frame),
//                                       y atlas columns (4), z frame count (16), w ripple strength (0..1, rain amount)
//   _EOA_RainDrops           Texture2D  tileable droplet-bead NORMAL map (static wet surface, 1024^2)
//   _EOA_RainStreaks         Texture2D  tileable rivulets: RG normal (0.5 centred, linear), B mask, A flow phase
//   _EOA_RainSurfaceParams   float4     x time (s), y rivulet flow speed (phase/s), z drop strength, w rivulet strength
//   _EOA_Wetness, _EOA_RainAmount (EOA_CityFx.hlsl / CityFx.cs) still give the overall wet / raining factors.
//
// Usage (tangent-space normals, blend with your own normal, e.g. BlendNormalRNM or simple xy add):
//   #include "Assets/Shaders/EOA_RainRipple.hlsl"   (or a relative path from Assets/Shaders)
//   float3 n = EOA_RainRippleNormal(positionWS.xz, 1.2);              // horizontal puddles, ~1.2 m per tile
//   n = EOA_BlendRainNormal(n, EOA_RainSurfaceNormal(uv * 2.0, vertical01));   // walls / glass / car paint
// Puddle masks are yours (e.g. where your puddle mask > 0.5 use the ripples at full strength).
#ifndef EOA_RAIN_RIPPLE_INCLUDED
#define EOA_RAIN_RIPPLE_INCLUDED

TEXTURE2D(_EOA_RainRipple);  SAMPLER(sampler_EOA_RainRipple);
TEXTURE2D(_EOA_RainDrops);   SAMPLER(sampler_EOA_RainDrops);
TEXTURE2D(_EOA_RainStreaks); SAMPLER(sampler_EOA_RainStreaks);
float4 _EOA_RainRippleParams;
float4 _EOA_RainSurfaceParams;

// Unpack an RGB normal map sample (Unity "Normal map" import: UnpackNormal handles DXT5nm / BC5 / RGB).
float3 EOA_RainUnpack(half4 s)
{
    return UnpackNormal(s);
}

float2 EOA_RainFrameUV(float2 cellUV, float frame, float cols)
{
    float f = fmod(frame, cols * cols);
    float col = fmod(f, cols);
    float rowTop = floor(f / cols);
    return (cellUV + float2(col, cols - 1.0 - rowTop)) / cols;
}

// Ripple normal for a horizontal wet surface at world xz, tileMeters = world size of one ripple tile.
float3 EOA_RainRippleNormal(float2 worldXZ, float tileMeters)
{
    float strength = _EOA_RainRippleParams.w;
    if (strength <= 0.001) return float3(0, 0, 1);
    float cols = max(_EOA_RainRippleParams.y, 1.0);
    float frames = max(_EOA_RainRippleParams.z, 1.0);
    float fpos = _EOA_RainRippleParams.x;
    float f0 = floor(fpos);
    float bl = fpos - f0;
    float2 p = worldXZ / tileMeters;
    float2 cell = frac(p);
    // gradients of the unwrapped coordinate: no mip seam at the cell borders
    float2 dx = ddx(p) / cols, dy = ddy(p) / cols;
    float3 a = EOA_RainUnpack(SAMPLE_TEXTURE2D_GRAD(_EOA_RainRipple, sampler_EOA_RainRipple, EOA_RainFrameUV(cell, f0, cols), dx, dy));
    float3 b = EOA_RainUnpack(SAMPLE_TEXTURE2D_GRAD(_EOA_RainRipple, sampler_EOA_RainRipple, EOA_RainFrameUV(cell, fmod(f0 + 1.0, frames), cols), dx, dy));
    float3 n = lerp(a, b, bl);
    // second, offset layer at another scale breaks the tiling
    float2 p2 = worldXZ / (tileMeters * 1.37) + 0.43;
    float f2 = fmod(f0 + 7.0, frames);
    float3 c = EOA_RainUnpack(SAMPLE_TEXTURE2D_GRAD(_EOA_RainRipple, sampler_EOA_RainRipple, EOA_RainFrameUV(frac(p2), f2, cols), ddx(p2) / cols, ddy(p2) / cols));
    float2 xy = (n.xy + c.xy * 0.7) * strength;
    return normalize(float3(xy, 1.0));
}

// Droplets + running rivulets for any wet surface. vertical01: 0 = horizontal (beads only), 1 = vertical (rivulets).
float3 EOA_RainSurfaceNormal(float2 uv, float vertical01)
{
    float dropsK = _EOA_RainSurfaceParams.z;
    float streakK = _EOA_RainSurfaceParams.w * saturate(vertical01);
    if (dropsK + streakK <= 0.001) return float3(0, 0, 1);
    float3 drops = EOA_RainUnpack(SAMPLE_TEXTURE2D(_EOA_RainDrops, sampler_EOA_RainDrops, uv));
    half4 s = SAMPLE_TEXTURE2D(_EOA_RainStreaks, sampler_EOA_RainStreaks, uv * float2(1.0, 0.5));
    // a bright moving "head" travels down each rivulet; the trail stays faintly wet
    float ph = frac(s.a - _EOA_RainSurfaceParams.x * _EOA_RainSurfaceParams.y);
    float head = smoothstep(0.0, 0.05, ph) * (1.0 - smoothstep(0.05, 0.35, ph));
    float trail = 0.25;
    float2 sxy = (s.rg * 2.0 - 1.0) * s.b * (trail + head);
    float2 xy = drops.xy * dropsK * (1.0 - 0.6 * saturate(vertical01)) + sxy * streakK * 2.0;
    return normalize(float3(xy, 1.0));
}

// Whiteout-style blend of two tangent-space normals.
float3 EOA_BlendRainNormal(float3 base, float3 detail)
{
    return normalize(float3(base.xy + detail.xy, base.z * detail.z));
}

#endif
