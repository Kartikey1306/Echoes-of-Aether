// Lit-window facades for the city's window skins and the distant megatower skyline.
// UVs are metres: u around the building perimeter, v up from the skin's base.
//
// Facades are LIT (URP main light with cascaded shadows, Forward+ lamps with their shadows, ambient SH, GGX
// specular that wetness sharpens) so building faces separate by value, lamps throw pools of light up the walls and
// shadows land on them. Close up the flat skin gets procedural relief: every window sits in a reveal (analytic
// parallax: side reveals, lit sills, dark heads, the glass and its room shift with the view and the reveal shades
// the glass), every floor has a projecting slab ledge (top catches the moon, the underside the street lamps, a crisp
// shadow line below it), all faded to the flat look by pixel footprint. Window light stays emissive.
//
// Every building (and every tower segment of a few floors) gets its own character from a per-face key:
//   * a facade module: curtain wall, ribbon glazing, punched windows, paired residential windows or slot windows,
//     with mullions, transoms and dark spandrels at the floor slabs,
//   * a use: offices light whole floors in cool white with ceiling panels; homes scatter warm, cool and neon-tinted
//     rooms with curtains and blinds at random heights, occasional flickering TVs,
//   * a district palette (from the world position, same map as CityLayout.DistrictAt) for the rooms and for every
//     neon accent (DistrictNeon): Neon Market red / amber / gold, Kowloon Stacks fluorescent lime-yellow / orange,
//     Arcology Gate corporate cyan / white / gold, Canal Ward teal / warm, Foundry Row sodium orange; _NeonA (magenta)
//     survives only as a rare accent.
// Close up, lit rooms are interior-mapped (room depth with back and side walls, ceiling lights, floor, furniture and
// occupant silhouettes); far away they collapse to an anti-aliased average. Some towers also carry LED media bands,
// vertical LED chase strips and horizontal neon bands. Partial fog keeps the lit windows glowing through the haze.
//
// Keys: the face key is (u - along) where along is the world distance along the face, so it is constant per face
// and different per building (the builders start every building's u at a random offset). With _Skyline = 1 the
// tower id comes from UV2.x instead (merged skyline meshes).
Shader "EOA/CityLights"
{
    Properties
    {
        _Base ("Facade", Color) = (0.02, 0.025, 0.04, 1)
        _Warm ("Warm Windows (HDR)", Color) = (1.6, 1.0, 0.55, 1)
        _Cool ("Cool Windows (HDR)", Color) = (0.6, 1.2, 1.8, 1)
        _NeonA ("Neon A (HDR)", Color) = (3.0, 0.3, 2.4, 1)
        _NeonB ("Neon B (HDR)", Color) = (0.0, 2.6, 3.2, 1)
        _Cell ("Window Cell (m)", Vector) = (2.2, 3.4, 0, 0)
        _Lit ("Lit Fraction", Range(0, 1)) = 0.42
        _Bands ("Neon Band Spacing (m)", Float) = 38
        _Seed ("Seed", Float) = 0
        _FogKeep ("Fog Resistance", Range(0, 1)) = 0.55
        _Interior ("Room Depth (m)", Float) = 3.6
        _Detail ("Interior Detail Distance (m)", Float) = 170
        _Glass ("Glass Reflection", Range(0, 1)) = 0.6
        _Media ("Media Band Chance", Range(0, 1)) = 0.1
        _Strips ("LED Strip Chance", Range(0, 1)) = 0.18
        _Skyline ("Skyline Mode (tower id in UV2)", Float) = 0
        _Brightness ("Window Brightness", Float) = 1
        _FogScale ("Fog Distance Scale", Float) = 1
        _Albedo ("Facade Albedo (lit)", Color) = (0.3, 0.3, 0.31, 1)
        _Emit ("Facade Self-Glow (x Base)", Range(0, 1)) = 0.35
        _Relief ("Window Reveal Depth (m)", Float) = 0.3
        _Ledge ("Floor Ledge Projection (m)", Float) = 0.28
        _Rough ("Facade Roughness (dry)", Range(0.05, 1)) = 0.8
    }
    SubShader
    {
        Tags { "RenderType"="Opaque" "Queue"="Geometry" "RenderPipeline"="UniversalPipeline" }
        Pass
        {
            Name "Forward"
            Tags { "LightMode"="UniversalForward" }
            // Two-sided: the skins are roofless boxes, so their inner faces must read as solid dark walls from above.
            Cull Off
            HLSLPROGRAM
            #pragma target 3.5
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile _ _MAIN_LIGHT_SHADOWS _MAIN_LIGHT_SHADOWS_CASCADE
            #pragma multi_compile _ _ADDITIONAL_LIGHTS
            #pragma multi_compile_fragment _ _ADDITIONAL_LIGHT_SHADOWS
            #pragma multi_compile_fragment _ _SHADOWS_SOFT _SHADOWS_SOFT_LOW _SHADOWS_SOFT_MEDIUM _SHADOWS_SOFT_HIGH
            #pragma multi_compile _ _CLUSTER_LIGHT_LOOP
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Core.hlsl"
            #include "Packages/com.unity.render-pipelines.universal/ShaderLibrary/Lighting.hlsl"
            #include "EOA_CityFx.hlsl"

            CBUFFER_START(UnityPerMaterial)
            half4 _Base, _Warm, _Cool, _NeonA, _NeonB;
            float4 _Cell;
            float _Lit, _Bands, _Seed, _FogKeep, _Interior, _Detail, _Glass, _Media, _Strips, _Skyline, _Brightness, _FogScale;
            half4 _Albedo;
            float _Emit, _Relief, _Ledge, _Rough;
            CBUFFER_END

            struct Attributes
            {
                float4 positionOS : POSITION;
                float3 normalOS : NORMAL;
                float2 uv : TEXCOORD0;
                float4 uv2 : TEXCOORD1;
            };

            struct Varyings
            {
                float4 positionCS : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 posWS : TEXCOORD1;
                float3 normalWS : TEXCOORD2;
                float eye : TEXCOORD3;
                nointerpolation float3 key : TEXCOORD4;   // x key if u runs with +along, y key if against, z skyline tower id
            };

            Varyings vert(Attributes v)
            {
                Varyings o;
                o.posWS = TransformObjectToWorld(v.positionOS.xyz);
                o.positionCS = TransformWorldToHClip(o.posWS);
                o.normalWS = TransformObjectToWorldNormal(v.normalOS);
                o.uv = v.uv;
                o.eye = -TransformWorldToView(o.posWS).z;
                float3 n = normalize(o.normalWS);
                float3 t = normalize(cross(n, float3(0, 1, 0)) + 1e-5);
                float along = dot(t, o.posWS);
                o.key = float3(v.uv.x - along, v.uv.x + along, v.uv2.x);
                return o;
            }

            float H1(float n) { return frac(sin(n * 12.9898 + _Seed * 7.13) * 43758.5453); }
            float H2(float2 p) { return frac(sin(dot(p, float2(127.1, 311.7)) + _Seed * 13.7) * 43758.5453); }
            float H3(float3 p) { return frac(sin(dot(p, float3(127.1, 311.7, 74.7)) + _Seed * 3.1) * 43758.5453); }

            // Anti-aliased box mask on a 0..1 coordinate (w = filter width in the same units).
            float Band(float x, float a, float b, float w)
            {
                return saturate((x - a) / w + 0.5) * saturate((b - x) / w + 0.5);
            }

            // District style from the world position (prototype x is mirrored): officeP, neonP, warmP, litMul.
            float4 DistrictStyle(float3 ws, out float sodium)
            {
                float px = -ws.x, pz = ws.z;
                sodium = 0;
                if (pz >= 152.0) return float4(0.2, 0.25, 0.55, 1.0);                     // Canal Ward
                if (pz < -112.0)
                {
                    if (px > 96.0) { sodium = 1; return float4(0.25, 0.08, 0.85, 0.65); }   // Foundry Row
                    return float4(0.08, 0.3, 0.7, 1.15);                                     // Kowloon Stacks
                }
                if (px < 0.0) return float4(0.15, 0.45, 0.6, 1.05);                          // Neon Market
                return float4(0.75, 0.2, 0.3, 1.0);                                          // Arcology Gate
            }

            // District neon accents (HDR): media bands, LED strips, neon bands and neon-tinted rooms. Two colours per
            // building from the district identity (r picks the pair); a few buildings keep a magenta accent.
            //   Neon Market red / amber / gold, Kowloon Stacks lime-yellow fluorescent / orange, Arcology Gate cyan /
            //   cool white / gold, Canal Ward teal / amber / red, Foundry Row orange sodium / amber / red.
            void DistrictNeon(float3 ws, float r, out half3 a, out half3 b)
            {
                float px = -ws.x, pz = ws.z;
                half3 c0, c1, c2;
                if (pz >= 152.0) { c0 = half3(0.15, 2.7, 2.1); c1 = half3(3.0, 1.55, 0.35); c2 = half3(3.0, 0.42, 0.25); }
                else if (pz < -112.0)
                {
                    if (px > 96.0) { c0 = half3(3.2, 1.05, 0.12); c1 = half3(3.0, 1.65, 0.32); c2 = half3(3.0, 0.32, 0.14); }
                    else { c0 = half3(1.9, 2.9, 0.35); c1 = half3(3.1, 1.0, 0.18); c2 = half3(2.1, 2.7, 1.9); }
                }
                else if (px < 0.0) { c0 = half3(3.3, 0.32, 0.2); c1 = half3(3.1, 1.5, 0.28); c2 = half3(2.7, 1.95, 0.6); }
                else { c0 = half3(0.18, 2.4, 3.3); c1 = half3(2.4, 2.75, 3.1); c2 = half3(2.9, 2.0, 0.65); }
                float k = frac(r * 5.71);
                a = k < 0.4 ? c0 : (k < 0.75 ? c1 : c2);
                b = k < 0.4 ? c1 : (k < 0.75 ? c2 : c0);
                if (frac(r * 13.3) < 0.06) a = _NeonA.rgb;   // occasional magenta accent
                // same luminance for every accent (amber, cyan and white carry far more than red / magenta)
                const float3 lw = float3(0.2126, 0.7152, 0.0722);
                a *= 1.0 / max(dot(a, lw), 0.35);
                b *= 1.0 / max(dot(b, lw), 0.35);
            }

            // Module: x bay width (m), y bays per room, z/w pane x range in the bay, returns pane y range in out.
            float4 Module(float m, float rnd, out float2 py)
            {
                if (m < 1.0) { py = float2(0.12, 0.97); return float4(1.5, 3.0 + floor(rnd * 2.0), 0.035, 0.965); }  // curtain wall
                if (m < 2.0) { py = float2(0.34, 0.86); return float4(1.6, 2.0 + floor(rnd * 3.0), 0.02, 0.98); }    // ribbon
                if (m < 3.0) { py = float2(0.26, 0.8); return float4(_Cell.x * (0.85 + rnd * 0.45), 1.0 + floor(rnd * 2.0), 0.2, 0.8); } // punched
                if (m < 4.0) { py = float2(0.22, 0.84); return float4(1.35, 2.0, 0.1, 0.9); }                        // paired
                py = float2(0.12, 0.9); return float4(0.95, 1.0, 0.27, 0.73);                                           // slot
            }

            // Occupant / furniture silhouette in room space (metres): returns coverage.
            float Silhouette(float2 p, float roomW, float kind, float cx)
            {
                if (kind < 0.35)
                {
                    // Person: head + shoulders/body.
                    float2 hp = p - float2(cx, 1.62);
                    float head = step(dot(hp, hp), 0.012);
                    float body = step(abs(p.x - cx), 0.21 - max(0.0, p.y - 1.25) * 0.4) * step(p.y, 1.47);
                    return saturate(head + body);
                }
                if (kind < 0.7)
                {
                    // Sofa / desk with a lamp or monitor.
                    float w = roomW * 0.45;
                    float desk = step(abs(p.x - cx), w * 0.5) * step(p.y, 0.82);
                    float mon = step(abs(p.x - cx - w * 0.15), 0.22) * step(0.82, p.y) * step(p.y, 1.2);
                    return saturate(desk + mon);
                }
                // Shelf / tall plant.
                float shelf = step(abs(p.x - cx), 0.35) * step(p.y, 2.0);
                return shelf;
            }

            // ---------------------------------------------------------------- lighting helpers
            // URP's GGX specular (DirectBRDFSpecular form); rough = perceptual roughness.
            half SpecTerm(float3 n, float3 l, float3 v, half rough)
            {
                float3 h = SafeNormalize(l + v);
                half nh = saturate(dot(n, h));
                half lh = saturate(dot(l, h));
                half a = max(rough * rough, 0.002h);
                half a2 = a * a;
                half d = nh * nh * (a2 - 1.0h) + 1.00001h;
                return a2 / ((d * d) * max(0.1h, lh * lh) * (a * 4.0h + 2.0h));
            }

            // A point in a window recess (opening coords h in metres, depth z behind the facade plane) is lit by L only
            // if the ray toward the light leaves through the opening (rect = x0, y0, x1, y1).
            half RecessLit(float3 L, float3 Tu, float3 N, float2 h, float z, float4 rect)
            {
                float lz = dot(L, -N);
                if (lz > -0.02) return 0;
                float2 e = h + float2(dot(L, Tu), L.y) * (z / -lz);
                float2 a = saturate((e - rect.xy) * 30.0) * saturate((rect.zw - e) * 30.0);
                return a.x * a.y;
            }

            // Wall just under a floor ledge (below = metres under the ledge, p = projection): in its shadow when the
            // light comes from above.
            half LedgeLit(float3 L, float3 N, float below, float p)
            {
                float lz = dot(L, -N);
                if (lz > -0.02 || L.y <= 0.0 || below < 0.0) return 1;
                return saturate((below - p * L.y / -lz) * 25.0 + 0.5);
            }

            // Per-pixel surface for the light loop.
            //   kind 0 plain wall / ledge, 1 window reveal (rh, rz), 2 wall under a ledge (below)
            struct Facet
            {
                float3 n;
                float kind;
                float2 rh;
                float rz;
                float below;
                float glassZ;     // > 0: glass sits glassZ behind the facade at gh (recess shades the glass highlights)
                float2 gh;
            };

            void Accum(half3 rad, float3 L, Facet f, float3 Nn, float3 Tu, float4 rect, float ledgeP, float3 Vc, half rough,
                       inout half3 diff, inout half3 spec, inout half3 gspec)
            {
                half occ = 1;
                if (f.kind > 0.5 && f.kind < 1.5) occ = RecessLit(L, Tu, Nn, f.rh, f.rz, rect);
                else if (f.kind > 1.5) occ = LedgeLit(L, Nn, f.below, ledgeP);
                half ndl = saturate(dot(f.n, L)) * occ;
                diff += rad * ndl;
                spec += rad * (ndl * SpecTerm(f.n, L, Vc, rough));
                half g = f.glassZ > 0.0 ? RecessLit(L, Tu, Nn, f.gh, f.glassZ, rect) : 1.0h;
                gspec += rad * (saturate(dot(Nn, L)) * g * SpecTerm(Nn, L, Vc, 0.1h));
            }

            // Main light + Forward+ lamps (only lights on this renderer's rendering layers: the character key / fill /
            // rim never light the city).
            void LightFacet(float3 posWS, float4 positionCS, Facet f, float3 Nn, float3 Tu, float4 rect, float ledgeP, float3 Vc, half rough,
                            out half3 diff, out half3 spec, out half3 gspec)
            {
                diff = 0; spec = 0; gspec = 0;
                float4 shadowCoord = TransformWorldToShadowCoord(posWS);
                Light mainLight = GetMainLight(shadowCoord, posWS, half4(1, 1, 1, 1));
                Accum(mainLight.color * (mainLight.distanceAttenuation * mainLight.shadowAttenuation), mainLight.direction, f, Nn, Tu, rect, ledgeP, Vc, rough, diff, spec, gspec);
            #if defined(_ADDITIONAL_LIGHTS)
                uint meshLayers = GetMeshRenderingLayer();
                InputData inputData = (InputData)0;
                inputData.positionWS = posWS;
                inputData.normalizedScreenSpaceUV = GetNormalizedScreenSpaceUV(positionCS);
                uint pixelLightCount = GetAdditionalLightsCount();
            #if USE_CLUSTER_LIGHT_LOOP
                [loop] for (uint li = 0; li < min(URP_FP_DIRECTIONAL_LIGHTS_COUNT, MAX_VISIBLE_LIGHTS); li++)
                {
                    Light dl = GetAdditionalLight(li, posWS, half4(1, 1, 1, 1));
                    if ((dl.layerMask & meshLayers) != 0)
                        Accum(dl.color * (dl.distanceAttenuation * dl.shadowAttenuation), dl.direction, f, Nn, Tu, rect, ledgeP, Vc, rough, diff, spec, gspec);
                }
            #endif
                LIGHT_LOOP_BEGIN(pixelLightCount)
                    Light l = GetAdditionalLight(lightIndex, posWS, half4(1, 1, 1, 1));
                    if ((l.layerMask & meshLayers) != 0)
                        Accum(l.color * (l.distanceAttenuation * l.shadowAttenuation), l.direction, f, Nn, Tu, rect, ledgeP, Vc, rough, diff, spec, gspec);
                LIGHT_LOOP_END
            #endif
            }

            // Simple diffuse lighting (roofs of the skyline towers).
            half3 SimpleLit(float3 posWS, float4 positionCS, float3 n, half3 albedo)
            {
                Facet f = (Facet)0;
                f.n = n;
                half3 diff, spec, gspec;
                LightFacet(posWS, positionCS, f, n, float3(1, 0, 0), float4(0, 0, 1, 1), 0, n, 1, diff, spec, gspec);
                return albedo * (diff + SampleSH(n));
            }

            half4 frag(Varyings i) : SV_Target
            {
                float3 N = normalize(i.normalWS);
                float3 cam = _WorldSpaceCameraPos.xyz;
                float3 toP = i.posWS - cam;
                float dist = length(toP);
                float3 V = toP / max(dist, 1e-4);
                float3 Vc = -V;
                float t = _Time.y;
                float2 uv = i.uv;
                float3 Tc = normalize(cross(N, float3(0, 1, 0)) + 1e-5);
                float along = dot(Tc, i.posWS);
                // Which way u runs along this face (derivatives are taken before any branching).
                float corr = ddx(uv.x) * ddx(along) + ddy(uv.x) * ddy(along);
                float s = corr >= 0.0 ? 1.0 : -1.0;
                float2 fw = fwidth(uv);
                float wet = saturate(_EOA_Wetness);

                // Roofs and floors of the skin: lit dark roofing.
                if (abs(N.y) > 0.5)
                {
                    half3 roof = SimpleLit(i.posWS, i.positionCS, N, _Albedo.rgb * 0.7) + _Base.rgb * 0.7 * _Emit;
                    return half4(lerp(unity_FogColor.rgb, roof, EOA_UnityFogKeep(i.eye * _FogScale)), 1);
                }

                // Inside of a roofless skin box (seen from above): solid dark wall.
                if (dot(N, V) > 0.0)
                {
                    half3 inner = _Base.rgb * 0.55 + _Albedo.rgb * SampleSH(float3(0, 1, 0)) * 0.25;
                    return half4(lerp(unity_FogColor.rgb, inner, EOA_UnityFogKeep(i.eye * _FogScale)), 1);
                }

                // ---------------------------------------------------------------- building identity
                float key = s > 0.0 ? i.key.x : i.key.y;
                float bid = _Skyline > 0.5 ? i.key.z * 97.31 + 0.17 : floor(key * 2.0 + 0.5) * 0.0371;
                float r0 = H1(bid), r1 = H1(bid + 1.7), r2 = H1(bid + 3.1), r3 = H1(bid + 5.3), r4 = H1(bid + 7.9), r5 = H1(bid + 9.4);
                float sodium;
                float4 ds = DistrictStyle(i.posWS, sodium);
                half3 accA, accB;
                DistrictNeon(i.posWS, r2 + r4 * 0.37, accA, accB);
                bool office = r0 < ds.x;
                float floorH = _Cell.y;
                float fl = floor(uv.y / floorH);
                float fy = frac(uv.y / floorH);
                // Segments of a few floors may switch module (podium / mid / crown wings).
                float segLen = 4.0 + floor(r1 * 9.0);
                float seg = floor((fl + floor(r2 * segLen)) / segLen);
                float segR = H2(float2(bid, seg));
                float baseModule = office ? (r3 < 0.6 ? 0.5 : 1.5) : (r3 < 0.45 ? 2.5 : (r3 < 0.7 ? 3.5 : (r3 < 0.88 ? 4.5 : 1.5)));
                float module = segR < 0.22 ? floor(segR * 22.7) + 0.5 : baseModule;
                float2 py;
                float4 mod = Module(module, r4, py);
                float bay = mod.x * (0.9 + r5 * 0.25);
                float bpr = mod.y;
                float bayIdx = floor(uv.x / bay);
                float fx = frac(uv.x / bay);
                float roomIdx = floor(bayIdx / bpr);
                float rx = (bayIdx - roomIdx * bpr + fx) / bpr;
                float roomW = bay * bpr;
                float roomR = H3(float3(roomIdx, fl, bid));
                float roomR2 = H3(float3(roomIdx * 1.31, fl * 0.77, bid + 2.0));

                // ---------------------------------------------------------------- lighting state of the room
                float tick = floor(t * 0.02 + roomR * 13.0);
                float litP = _Lit * ds.w * (0.65 + r2 * 0.7);
                float lit;
                half3 L;
                bool tv = false;
                if (office)
                {
                    float floorOn = step(H2(float2(fl, bid + 4.0)), 0.35 + r4 * 0.45);
                    lit = floorOn * step(roomR, 0.9) + (1.0 - floorOn) * step(H3(float3(roomIdx, fl, tick + bid)), litP * 0.25);
                    // Per-floor fixture tint and level: cool LED, warm white, greenish fluorescent; some floors on night lighting.
                    float warmth = H2(float2(fl * 0.37, bid));
                    L = warmth < 0.55 ? half3(0.8, 0.92, 1.05) : (warmth < 0.82 ? half3(1.05, 0.93, 0.76) : half3(0.84, 1.0, 0.86));
                    L *= (0.38 + 0.32 * H2(float2(fl, bid + 7.0))) * (H2(float2(fl * 1.3, bid + 9.0)) < 0.18 ? 0.4 : 1.0);
                    L *= 0.85 + 0.3 * roomR2;
                    if (sodium > 0.5) L = half3(1.0, 0.58, 0.26) * 0.8;
                }
                else
                {
                    lit = step(H3(float3(roomIdx, fl, tick + bid * 3.0)), litP);
                    float pick = roomR2;
                    half3 warm = _Warm.rgb * 0.55 * (0.45 + 0.6 * H1(roomR * 31.0)) * half3(1.0, 0.92 + 0.16 * H1(roomR * 7.0), 0.85 + 0.3 * H1(roomR * 13.0));
                    half3 cool = _Cool.rgb * 0.5;
                    // Kowloon Stacks: greenish fluorescent tubes instead of cool LED
                    if (ds.w > 1.1) cool = half3(0.95, 1.35, 1.0) * 0.5;
                    half3 neon = (H1(roomR * 17.0) < 0.5 ? accA : accB) * 0.32;
                    L = pick < ds.z ? warm : (pick < ds.z + ds.y * 0.45 ? neon : cool);
                    if (sodium > 0.5) L = lerp(L, half3(1.2, 0.62, 0.25), 0.6);
                    tv = H1(roomR * 53.0 + fl) < 0.1;
                }
                float flick = 0.6 + 0.4 * EOA_Noise2(float2(t * 7.0 + roomR * 40.0, roomIdx));
                if (tv)
                {
                    half3 tvc = half3(0.45, 0.65, 1.2) * flick;
                    L = lit > 0.5 ? lerp(L, tvc, 0.35) : tvc * 0.45;
                    lit = max(lit, 0.6);
                }
                L *= _Brightness;

                // ---------------------------------------------------------------- pane / frame masks
                float wx = max(fw.x / bay, 1e-4) * 1.5;
                float wy = max(fw.y / floorH, 1e-4) * 1.5;
                float pane = Band(fx, mod.z, mod.w, wx) * Band(fy, py.x, py.y, wy);
                // Transom on tall panes and a mullion in the middle of wide punched windows.
                float detailVis = saturate(1.0 - max(wx, wy) * 6.0);
                if (module < 1.0) pane *= 1.0 - Band(fy, 0.78, 0.8, wy) * detailVis;
                if (module > 2.0 && module < 3.0) pane *= 1.0 - Band(fx, 0.49, 0.51, wx) * detailVis;
                // Closed windows / missing panes on some residential cells (variety).
                bool closed = !office && roomR2 > 0.97;
                if (closed) pane *= 0.0;

                // ---------------------------------------------------------------- relief (window reveals, floor ledges)
                float far = saturate((dist - _Detail * 0.75) / (_Detail * 0.5));
                float3 Tu = Tc * s;
                float3 Vl = float3(dot(V, Tu), V.y, max(dot(V, -N), 1e-3));   // view ray in facade space (z into the wall)
                float ox = fx * bay, oy = fy * floorH;
                float4 rect = float4(mod.z * bay, py.x * floorH, mod.w * bay, py.y * floorH);
                // reveal depth per module: shallow curtain wall, deep punched / slot openings
                float depthR = _Relief * (module < 1.0 ? 0.3 : module < 2.0 ? 0.55 : module < 3.0 ? 1.0 : module < 4.0 ? 0.8 : 1.15);
                float relief = (1.0 - far) * detailVis * step(_Skyline, 0.5);
                float ledgeP = _Ledge * (module < 1.0 ? 0.35 : module < 2.0 ? 0.9 : 1.0) * relief;
                Facet f = (Facet)0;
                f.n = N;
                float glassMask = pane;          // where the window (glass + room) shows
                float2 shiftG = 0;               // parallax of the glass / room behind the reveal
                half3 albedo = _Albedo.rgb;
                // building tint: concrete, warm brick, blue-grey, sandstone, soot (adjacent blocks separate by value)
                float tk = frac(r3 * 7.31 + r5 * 3.17);
                half3 tint = tk < 0.3 ? half3(1.0, 1.0, 1.02) : tk < 0.5 ? half3(1.25, 0.86, 0.7) : tk < 0.7 ? half3(0.78, 0.86, 1.05)
                           : tk < 0.85 ? half3(1.3, 1.15, 0.92) : half3(0.55, 0.55, 0.58);
                albedo *= tint * (0.85 + 0.3 * H2(float2(bayIdx * 0.13, fl * 0.07 + bid)));
                half ao = 1;
                if (relief > 0.01)
                {
                    bool inOpen = !closed && ox > rect.x && ox < rect.z && oy > rect.y && oy < rect.w && pane > 0.02;
                    if (inOpen)
                    {
                        float tG = depthR / Vl.z;
                        float2 hitG = float2(ox, oy) + Vl.xy * tG;
                        bool seesGlass = hitG.x > rect.x && hitG.x < rect.z && hitG.y > rect.y && hitG.y < rect.w;
                        if (seesGlass)
                        {
                            glassMask = lerp(pane, 1.0, relief);
                            shiftG = Vl.xy * tG * relief;
                            f.glassZ = depthR;
                            f.gh = hitG;
                        }
                        else
                        {
                            // side reveal, head or sill: the first wall of the opening the view ray meets
                            float tx = Vl.x > 0.0 ? (rect.z - ox) / max(Vl.x, 1e-4) : (rect.x - ox) / min(Vl.x, -1e-4);
                            float ty = Vl.y > 0.0 ? (rect.w - oy) / max(Vl.y, 1e-4) : (rect.y - oy) / min(Vl.y, -1e-4);
                            float tw = min(tx, ty);
                            float3 rn = tx < ty ? (Vl.x > 0.0 ? -Tu : Tu) : (Vl.y > 0.0 ? float3(0, -1, 0) : float3(0, 1, 0));
                            float zr = Vl.z * tw;
                            f.n = normalize(lerp(N, rn, relief));
                            f.kind = 1;
                            f.rh = float2(ox, oy) + Vl.xy * tw;
                            f.rz = zr;
                            glassMask = lerp(pane, 0.0, relief);
                            albedo *= 1.12;
                            // deeper into the reveal and toward the glass corner: occluded
                            ao = lerp(0.95, 0.5, saturate(zr / depthR));
                        }
                    }
                    else if (ledgeP > 0.005)
                    {
                        // floor slab ledge (projecting string course) at every floor line
                        float lh = 0.22;
                        float oyc = fy < 0.5 ? oy : oy - floorH;   // metres above (+) / below (-) the nearest floor line
                        float sh = clamp(ledgeP * Vl.y / Vl.z, -0.6, 0.6);
                        bool front = oyc >= sh && oyc < sh + lh;
                        bool under = sh > 0.0 && oyc >= 0.0 && oyc < sh;
                        bool top = sh < 0.0 && oyc >= sh + lh && oyc < lh;
                        if (front || under || top)
                        {
                            float3 ln = under ? float3(0, -1, 0) : top ? float3(0, 1, 0) : N;
                            f.n = normalize(lerp(N, ln, relief));
                            albedo *= front ? 1.18 : 1.05;
                            ao = under ? 0.8 : 1.0;
                            glassMask = 0;
                        }
                        else if (oyc < 0.0)
                        {
                            f.kind = 2;
                            f.below = -oyc;
                            ao = lerp(0.82, 1.0, saturate(-oyc / 0.45));
                        }
                    }
                }
                else
                {
                    // flat: the old dark spandrel line at the floor slabs
                    float slab = Band(fy, -0.02, 0.06, wy);
                    albedo *= 1.0 - 0.25 * slab * detailVis;
                }

                // ---------------------------------------------------------------- window colour
                half3 win;
                float glassF = 0.04 + 0.96 * pow(1.0 - saturate(abs(dot(V, N))), 5.0);
                float3 R = reflect(V, N);
                half3 refl = _EOA_HFogColor.rgb * 1.6 + _EOA_HFogGlow.rgb * _EOA_HFogGlow.a * 0.35 * exp(-abs(R.y) * 5.0);
                refl = lerp(refl, _Base.rgb, saturate(R.y * 1.5));
                if (far < 1.0 && glassMask > 0.001)
                {
                    // reflections of the real city (probes / sky) in the glass close up
                    float2 suv = GetNormalizedScreenSpaceUV(i.positionCS);
                    refl = lerp(refl, GlossyEnvironmentReflection(R, i.posWS, 0.08h, 1.0h, suv), 0.65 * (1.0 - far));
                    // Interior mapping (origin shifted by the reveal parallax).
                    float3 d = float3(dot(V, Tu), V.y, max(dot(V, -N), 1e-3));
                    float depth = _Interior * (0.75 + 0.5 * r5) * (office ? 1.4 : 1.0);
                    float3 o = float3(clamp(rx * roomW + shiftG.x, 0.01, roomW - 0.01), clamp(oy + shiftG.y, 0.01, floorH - 0.26), 0.0);
                    float fyW = o.y / floorH;
                    float rxW = o.x / roomW;
                    float tX = d.x > 0.0 ? (roomW - o.x) / max(d.x, 1e-4) : o.x / max(-d.x, 1e-4);
                    float tY = d.y > 0.0 ? (floorH - 0.25 - o.y) / max(d.y, 1e-4) : o.y / max(-d.y, 1e-4);
                    float tZ = depth / d.z;
                    float tm = min(tX, min(tY, tZ));
                    float3 hit = o + d * tm;
                    half3 rc;
                    // Wall colour per room (offices: warm grey, blue-grey or sage partitions; homes: painted walls).
                    half3 wallTint = office ? (roomR2 < 0.4 ? half3(0.95, 0.92, 0.86) : (roomR2 < 0.75 ? half3(0.78, 0.84, 0.95) : half3(0.82, 0.92, 0.84)))
                                            : lerp(half3(1.0, 0.9, 0.8), half3(0.85, 0.9, 1.0), H1(roomR * 19.0));
                    if (tm == tZ)
                    {
                        float paper = 0.85 + 0.15 * step(0.5, frac(hit.x * (office ? 0.6 : 1.7) + roomR * 3.0));
                        rc = L * 0.48 * paper * wallTint;
                        // Whiteboards / pictures / shelves on the back wall.
                        float2 wb = float2(abs(hit.x - roomW * (0.3 + 0.4 * H1(roomR * 37.0))), abs(hit.y - floorH * 0.55));
                        rc = lerp(rc, office ? L * 0.75 : L * half3(0.35, 0.28, 0.24), step(wb.x, office ? 0.9 : 0.35) * step(wb.y, office ? 0.45 : 0.3) * step(0.5, H1(roomR * 41.0)));
                    }
                    else if (tm == tX) rc = L * 0.3 * wallTint;
                    else if (d.y > 0.0)
                    {
                        // Ceiling with lights: office panel grid, homes a pendant / ceiling lamp.
                        float lamp;
                        if (office) lamp = step(abs(frac(hit.x / 1.8) - 0.5), 0.18) * step(abs(frac(hit.z / 2.4) - 0.5), 0.12) * 2.4;
                        else { float2 lp = float2(hit.x - roomW * 0.5, hit.z - depth * 0.5); lamp = exp(-dot(lp, lp) * 2.0) * 1.6; }
                        rc = L * (0.36 + lamp);
                    }
                    else rc = L * 0.17 * (office ? half3(0.72, 0.8, 0.95) : half3(1.0, 0.85, 0.7));
                    rc *= 1.0 - 0.35 * saturate(hit.z / depth);
                    // Contact shadow in the room's corners and along the floor / ceiling edges.
                    float aoX = saturate(min(hit.x, roomW - hit.x) * 1.4);
                    float aoY = saturate(min(hit.y, floorH - 0.25 - hit.y) * 2.2);
                    rc *= 0.55 + 0.45 * aoX * (0.4 + 0.6 * aoY);
                    // Light falls off away from the ceiling fixtures toward the floor.
                    rc *= 0.7 + 0.45 * saturate(hit.y / floorH);
                    // Furniture / occupant silhouettes on a plane part-way into the room.
                    float zf = depth * (0.35 + roomR * 0.4);
                    float tF = zf / d.z;
                    if (tF < tm)
                    {
                        float3 pf = o + d * tF;
                        float kind = H1(roomR * 71.0 + 0.3);
                        float cx = roomW * (0.2 + 0.6 * H1(roomR * 29.0));
                        float inside = step(0.0, pf.x) * step(pf.x, roomW);
                        if (office)
                        {
                            // Rows of workstations: low partitions with glowing monitors, someone working late now and then.
                            float cub = frac(pf.x / 1.8 + roomR);
                            float part = step(pf.y, 1.15) * step(cub, 0.9);
                            float mon = step(1.12, pf.y) * step(pf.y, 1.5) * step(abs(cub - 0.4), 0.15);
                            rc = lerp(rc, L * 0.07, part * inside * 0.9);
                            rc = lerp(rc, half3(0.32, 0.55, 0.95) * (0.75 + 0.25 * flick) * (0.4 + 0.6 * lit), mon * inside);
                            float person = Silhouette(pf.xy, roomW, 0.1, cx) * step(kind, 0.3);
                            rc = lerp(rc, L * 0.05, person * inside * 0.92);
                        }
                        else
                        {
                            float sil = Silhouette(pf.xy, roomW, kind, cx) * inside;
                            rc = lerp(rc, L * 0.05, sil * 0.92);
                        }
                    }
                    // Blinds (top down to a random height) and curtains (from the sides) on the glass.
                    float blindKind = H1(roomR * 11.0 + 1.0);
                    if (blindKind < (office ? 0.35 : 0.45))
                    {
                        float level = 1.0 - H1(roomR * 5.0) * 0.85;
                        float yIn = (fyW - py.x) / (py.y - py.x);
                        float cover = step(level, yIn);
                        float slat = 0.75 + 0.25 * sin((fl * floorH + o.y) * 70.0);
                        rc = lerp(rc, L * 0.5 * slat, cover * lerp(1.0, 0.3, saturate(wy * 20.0)));
                    }
                    else if (!office && blindKind < 0.8)
                    {
                        float open = 0.15 + H1(roomR * 9.0) * 0.3;
                        float cover = step(rxW, open) + step(1.0 - open, rxW);
                        half3 fabric = H1(roomR * 3.3) < 0.5 ? half3(1.0, 0.45, 0.3) : half3(0.55, 0.85, 0.9);
                        float folds = 0.8 + 0.2 * sin(rxW * roomW * 18.0);
                        rc = lerp(rc, L * fabric * 0.55 * folds, saturate(cover));
                    }
                    half3 nearWin = lerp(_Base.rgb * 0.5 + refl * 0.3, rc, lit);
                    half3 farWin = L * lit * 0.5;
                    win = lerp(nearWin, farWin, far);
                }
                else win = L * lit * 0.5;
                win = win * (1.0 - glassF * 0.5) + refl * glassF * _Glass;

                // ---------------------------------------------------------------- lit facade
                half rough = lerp(_Rough, min(_Rough, 0.42), wet);
                // rain-streaked wet walls: glossier runs under the sills
                rough *= 0.85 + 0.3 * EOA_Noise2(float2(uv.x * 3.1, uv.y * 0.12 + r1 * 9.0));
                albedo *= 1.0 - 0.25 * wet;
                half3 diff, spec, gspec;
                LightFacet(i.posWS, i.positionCS, f, N, Tu, rect, ledgeP, Vc, rough, diff, spec, gspec);
                // Neon spill: coloured light from the nearest signs and lamp heads (EOA_CityFx.hlsl emitter field) on the
                // walls around them, wrapped so a sign mounted flat on the wall still washes it.
                if (relief > 0.01)
                {
                    half3 spill = 0;
                    int nNeon = (int)_EOA_NeonCount;
                    [unroll] for (int k = 0; k < 8; k++)
                    {
                        if (k < nNeon)
                        {
                            float3 dn = _EOA_NeonPos[k].xyz - i.posWS;
                            float rr = _EOA_NeonPos[k].w;
                            float dd = dot(dn, dn);
                            float att = saturate(1.0 - dd / (rr * rr));
                            float wrap = saturate(dot(f.n, dn * rsqrt(max(dd, 1e-4))) * 0.7 + 0.3);
                            spill += _EOA_NeonCol[k].rgb * (att * att * wrap);
                        }
                    }
                    diff += spill * (0.4 * relief);
                }
                // street-canyon occlusion: low floors see little sky, upper floors more (darker streets, brighter tops)
                half canyon = lerp(0.55h, 1.1h, saturate((i.posWS.y - 4.0) / 45.0));
                half3 amb = SampleSH(f.n) * ao * canyon;
                // specular ambient: the sky / haze in the wet wall
                half3 ambSpec = SampleSH(reflect(V, f.n)) * (1.0 - rough) * 0.5;
                half3 facade = albedo * (diff + amb) + 0.04 * (spec + ambSpec) + _Base.rgb * _Emit * ao;
                // Street glow washing up the lower facade.
                facade += _EOA_HFogGlow.rgb * _EOA_HFogGlow.a * 0.03 * exp(-max(i.posWS.y, 0.0) / 50.0);
                // glass: sharp highlights of the moon and lamps, shaded by the reveal
                win += gspec * (0.06 + 0.5 * glassF);
                half3 c = lerp(facade, win, saturate(glassMask));

                // ---------------------------------------------------------------- LED media band / strips / neon bands
                half3 accentA = (r1 < 0.5) ? accA : accB;
                half3 accentB = (r1 < 0.5) ? accB : accA;
                if (r4 < _Media && uv.y > 18.0)
                {
                    float fb = 5.0 + floor(r2 * 14.0), nb = 3.0 + floor(r3 * 4.0);
                    float inBand = step(fb, fl) * step(fl, fb + nb - 1.0);
                    if (inBand > 0.5)
                    {
                        float2 m = float2(uv.x, uv.y - fb * floorH) / float2(1.2, floorH * nb);
                        float sweep = sin(m.x * 0.35 - t * 1.4 + r0 * 6.0) * 0.5 + 0.5;
                        float blocks = step(0.45, H2(floor(float2(m.x * 0.5 - t * 3.0, m.y * 6.0)) + bid));
                        float wave = 1.0 - smoothstep(0.0, 0.08, abs(frac(m.y) - (0.5 + 0.35 * sin(m.x * 0.6 + t * 2.0))));
                        half3 media = lerp(accentA, accentB, sweep) * (0.25 + 0.55 * blocks) + accentB * wave * 0.8;
                        float pix = 0.75 + 0.25 * step(0.2, frac(uv.x * 2.5)) * step(0.2, frac(uv.y * 2.5));
                        // LED walls stay below the neon tubes: deep colour with content, not a blank glowing slab
                        c = media * pix * 0.3;
                    }
                }
                if (r5 < _Strips)
                {
                    float sp = 9.0 + floor(r0 * 4.0) * 6.0;
                    float sx = abs(frac(uv.x / sp + r2) - 0.5) * sp;
                    // energy-conserving coverage: at grazing angles fwidth(u) spans metres and the old mask lit the
                    // whole facade as one glowing slab; now a sub-pixel strip fades to its true (tiny) share
                    float fwx = max(fw.x * 1.5, 0.02);
                    float strip = saturate(1.0 - (sx - 0.12) / fwx) * saturate(0.24 / (fwx + 0.22));
                    float chase = frac(uv.y * 0.02 - t * 0.35 + floor(uv.x / sp) * 0.37);
                    c += accentB * strip * (0.25 + exp(-chase * 14.0) * 1.6);
                }
                // Neon bands every _Bands metres: a 0.44 m line (metric width; the old 0.006 x spacing turned the
                // "no bands" value 1000 into a 6 m solid slab at the base of every such skin), off for _Bands >= 500.
                float bandP = abs(frac(uv.y / _Bands) - 0.5);
                float bandW = max(fw.y / _Bands, 1e-5) * 1.5;
                float bandHW = 0.22 / _Bands;
                float bandLine = saturate((bandP - (0.5 - bandHW)) / bandW + 0.5) * saturate(2.0 * bandHW / (bandW + 2.0 * bandHW)) * step(_Bands, 500.0);
                c += (fmod(floor(uv.y / _Bands), 2.0) < 1.0 ? accentA : accentB) * bandLine * 0.8 * step(r3, 0.75);

                // Partial exp2 fog (no keyword variants; every outdoor zone uses FogMode.ExponentialSquared): lit windows glow through.
                half3 fogged = lerp(unity_FogColor.rgb, c, EOA_UnityFogKeep(i.eye * _FogScale));
                c = lerp(fogged, c, _FogKeep * saturate(dot(c, 1)));
                return half4(c, 1);
            }
            ENDHLSL
        }
    }
    Fallback Off
}
