using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Central Plaza (hub) + Collapsed Market, night, heavy rain (port of PlazaZone.ts).
    /// Layout (prototype metres): square x[-32,32] z[-32,32] with the Aether Monument at the origin; ring road to |44|;
    /// survivors' camp NE (22,-22); metro stairwell W (hole x[-30,-24] z[4,18]); facility gate N (z -46); elevated rail E
    /// (x 52); market street S to the market square z[70,112]. After the ending (flag game_complete) the city wakes at
    /// dawn: no rain, warm low sun, ending music.
    /// </summary>
    public sealed class PlazaZone : ProceduralZone
    {
        public override string ZoneId => "plaza";

        /// <summary>Dawn variant (post-ending epilogue).</summary>
        public bool Dawn { get; private set; }
        /// <summary>Floating Aether core (prototype space; cinematic target).</summary>
        public static readonly Vector3 CoreProto = new(0, 7.45f, 0);
        /// <summary>Survivors' camp fire barrel (prototype space; marker "fire").</summary>
        public static readonly Vector3 CampFireProto = new(22, 1.15f, -22);
        /// <summary>Metro entrance the heroes look at in cin_meeting (prototype space).</summary>
        public static readonly Vector3 MetroLookProto = new(-27, 1, 11);

        /// <summary>The Blender monument is modelled from y 0; it stands on the paving (0.15) so its steps meet the prototype step colliders (0.45 / 0.75).</summary>
        const float MonumentLift = 0.15f;
        /// <summary>The Blender core crystal is 2.15 m tall (prototype core: 1.8 m icosahedron); scaled so the pulse never touches the upper shard.</summary>
        const float CoreScale = 0.85f;
        /// <summary>FireBarrel asset (0.61 x 0.95 m) scaled to the prototype barrel (0.76 m wide, 1 m tall).</summary>
        const float FireBarrelScale = 1.2f;

        PzKit K;
        /// <summary>[OpenCity hook] The open district around the plaza (null when OpenCity.Enabled is false).</summary>
        OpenCity City;
        Vector3 saveScreen;
        GameObject core;
        readonly GameObject[] rings = new GameObject[2];
        static readonly float[] RingTilt = { 0.25f, -0.35f };
        static readonly float[] RingSpin = { 0.05f, -0.08f };
        readonly float[] ringAngle = new float[2];
        float coreAngle;
        Light monumentLight, fireLight;
        float monumentPerUnit, firePerUnit;

        struct Flicker
        {
            public Light Light;
            public GameObject Halo;
            public float Base, Seed;
            public bool On;
        }

        readonly List<Flicker> flickers = new();
        GameObject gateLeft, gateRight;
        float gateLX = -6, gateRX = 6;
        bool gateOpen, swapUnlocked;
        BoxCollider gateCollider;
        float flagPoll;
        readonly List<PzKit.ShopFront> marketWest = new(), marketEast = new();

        static readonly Vector3[] NiaRoute =
        {
            new(-8.6f, 0.16f, -5), new(-9, 0.16f, 4), new(-3, 0.16f, 8.5f), new(4, 0.16f, 8.5f), new(8.6f, 0.16f, 2), new(6, 0.16f, -7), new(-2, 0.16f, -9),
        };

        /// <summary>Walkable surface height of the prototype floor slabs at (x, z): paving / sidewalks 0.15, market square 0.16, road 0.</summary>
        static float GroundY(float x, float z)
        {
            float ax = Mathf.Abs(x), az = Mathf.Abs(z);
            if (ax <= 32 && az <= 32) return x > -30 && x < -24 && z > 4 && z < 18 ? -4.2f : 0.15f;
            if (x >= -30 && x <= 30 && z >= 70 && z <= 112) return 0.16f;
            if (z >= -50 && z <= -44 && ax <= 48) return 0.15f;
            if (ax >= 44 && ax <= 50 && az <= 50) return 0.15f;
            if (ax >= 12 && ax <= 18 && z >= 44 && z <= 70) return 0.15f;
            return 0;
        }

        // ================================================================== build

        protected override async Task BuildZone()
        {
            Dawn = Flag("game_complete");
            ZoneSettings(-12, false, Dawn ? "ending" : "explore", Dawn ? "none" : "rain_city");
            K = new PzKit(B);
            B.LightBudget = 24;

            // ---------------------------------------------------------------- Sky, light, fog
            SetAtmosphere(Dawn
                ? new AtmosphereSettings
                {
                    SkyTop = 0x2a4a7a, SkyHorizon = 0xf0a878, SkyBottom = 0x3a3030, Glow = 0xffc890, GlowStrength = 1.2f, Storm = false,
                    FogColor = 0x8a8a90, FogDensity = 0.008f,
                    HemiSky = 0xa8c4e8, HemiGround = 0x4a3a30, HemiIntensity = 1.8f, EnvIntensity = 1.0f,
                    SunPos = new Vector3(40, 18, 30), SunTarget = Vector3.zero, SunColor = 0xffc890, SunIntensity = 3.2f, SunShadows = true,
                    Exposure = 1.15f, Contrast = 1.05f, Saturation = 1.05f, Lift = new Vector3(0.02f, 0.01f, 0), Gain = new Vector3(1.05f, 1, 0.95f), BloomThreshold = 0.92f,
                    // Morning mist pooled in the streets after the storm.
                    HeightFogDensity = 0.003f, HeightFogFalloff = 0.05f, HeightFogStart = 15f, HeightFogMax = 0.68f,
                    HeightFogColor = 0x9a9ca8, HeightFogGlow = 0xffc890, HeightFogGlowStrength = 0.35f, HeightFogGlowDir = new Vector2(1, 0.75f), HeightFogGround = 0.1f,
                    // golden-hour grade: cool blue shadows, warm highlights
                    SplitShadows = 0x707f8c, SplitHighlights = 0x968470, GradeHighlights = new Vector3(1.04f, 1f, 0.95f), LensStreaks = 0.4f, CityPalette = true, WetGround = 0.4f,
                }
                : new AtmosphereSettings
                {
                    // Cinematic rain night: deep teal shadows and moonlit cloud ambient against warm sodium / amber street
                    // light and shop glow; the megacity's light pollution is orange on the low clouds, the haze teal with
                    // a warm glow toward the brightest districts. Neon accents come from the district palettes.
                    SkyTop = 0x04080d, SkyHorizon = 0x172429, SkyBottom = 0x07090b, Glow = 0xb8622c, GlowStrength = 0.55f, Storm = true,
                    SkyTint = 0xe2eaee, SkySaturation = 0.72f,
                    // Depth: a lighter, bluer haze than the facades, so distance reads as atmosphere (each block back is
                    // paler) instead of sinking into black; a stronger, lower moon key against less ambient, so faces
                    // turned to the moon separate from those turned away and shadows land. The moon stands in the
                    // north-west (~38 deg): looking south from the plaza and along the avenues one side of every street
                    // is moonlit, the other in shade, and shadows fall away from the camera.
                    FogColor = 0x182833, FogDensity = 0.0062f,
                    HemiSky = 0x7890a0, HemiGround = 0x2c2418, HemiIntensity = 1.5f, EnvIntensity = 1.05f,
                    SunPos = new Vector3(33, 37, 34), SunTarget = Vector3.zero, SunColor = 0xb4cadf, SunIntensity = 3.8f, SunShadows = true,
                    Exposure = 1.46f, Contrast = 1.18f, Saturation = 1.06f, Lift = new Vector3(0.002f, 0.002f, 0.004f), Gain = new Vector3(1.03f, 1f, 0.97f), BloomThreshold = 0.9f,
                    LightChroma = 0.72f,
                    // Layered city haze: exponential height fog swallowing street level and tower bases in a teal mist
                    // while tower tops stand clear, warm sodium glow toward the brightest districts and the light of the
                    // streets on the low clouds.
                    HeightFogDensity = 0.0055f, HeightFogFalloff = 0.045f, HeightFogStart = 14f, HeightFogMax = 0.8f,
                    HeightFogColor = 0x1b2e3a, HeightFogGlow = 0xd07a3a, HeightFogGlowStrength = 0.15f, HeightFogGlowDir = new Vector2(1, 0.2f), HeightFogGround = 0.42f,
                    CityGlow = 0xb0602e, CityGlowStrength = 0.36f,
                    // grade: teal shadows / amber highlights, a slight lift so unlit streets keep their shapes
                    SplitShadows = 0x6e8189, SplitHighlights = 0x96806a, SplitBalance = -8f,
                    GradeShadows = new Vector3(0.97f, 1f, 1.04f), GradeHighlights = new Vector3(1.05f, 1f, 0.93f), ShadowLift = 0.025f, Temperature = 6f,
                    Vignette = 0.32f, CityPalette = true, CharacterFill = 2.2f, WetGround = 0.85f,
                });
            await Progress(0.1f, "Sky and lighting");

            BuildGround();
            await Progress(0.2f, "Streets");

            BuildMonument();
            await Progress(0.3f, "Aether Monument");

            BuildStairwell();
            BuildBlocks();
            await Progress(0.45f, "Civic district");

            BuildGate(Flag("facility_gate_open"));
            BuildSkyline();
            BuildRail();
            await Progress(0.55f, "Transit line");

            BuildStreets();
            BuildSigns();
            await Progress(0.65f, "Abandoned streets");

            BuildCamp();
            BuildMarket();
            await Progress(0.75f, "Collapsed Market");

            // ---------------------------------------------------------------- Bounds
            // [OpenCity hook] the open district replaces the outer walls with the same walls minus the street openings.
            if (OpenCity.Enabled) OpenCity.PlazaWalls(B);
            else
            {
            B.Wall(0, 3, -48.5f, 120, 8, 1);
            B.Wall(0, 3, 115, 120, 8, 1);
            B.Wall(-48.5f, 3, 30, 1, 8, 170);
            B.Wall(48.5f, 3, 30, 1, 8, 170);
            // Market street side blocks (between the street buildings and the ring road)
            B.Wall(-18.5f, 3, 56, 1, 8, 26);
            B.Wall(18.5f, 3, 56, 1, 8, 26);
            B.Wall(-31, 3, 71.5f, 26, 8, 1);
            B.Wall(31, 3, 71.5f, 26, 8, 1);
            B.Wall(-31, 3, 44.5f, 26, 8, 1);
            B.Wall(31, 3, 44.5f, 26, 8, 1);
            }

            // ---------------------------------------------------------------- Weather
            MakeWeather(new WeatherSettings
            {
                // No rain (user request): a dry night after the storm; streets keep a light wet sheen from the wetness global.
                Rain = 0, Wind = new Vector2(2.5f, 1), Lightning = false, LightningInterval = new Vector2(14, 32), SplashHeight = 0.17f,
            });
            await Progress(0.85f, "Weather");

            // Cyberpunk city layer: neon shop signs, blade signs, holo adverts on the facades, a megatower skyline
            // and flying traffic overhead.
            var center = new Vector3(B.Bounds.center.x, 0, B.Bounds.center.z);
            CyberCity.DressFacades(B, center, 140, 9001, 1.3f, 200, groundY: 0.15f);
            DecalKit.ScatterGround(B.FxRoot, center, 95, 80, 9004);
            // [OpenCity hook] with the open district the skyline ring and sky lanes move out past the district edge.
            if (OpenCity.Enabled) OpenCity.SkylineAndSkyTraffic(B, transform, Dawn);
            else
            {
                CyberCity.Skyline(B, center, 190, 420, 40, 9002);
                SkyTraffic.Create(transform, center, Dawn ? 10 : 26, 40, 110, 70, 190, 9003);
            }
            await Progress(0.88f, "Neon city");

            LayoutGameplay();
            BuildMap();
            // [OpenCity hook] streets, blocks, crowds and traffic around the plaza; extends the zone map.
            if (OpenCity.Enabled) City = await OpenCity.Build(this, B, Dawn, (f, label) => Progress(f, label));
        }

        // ------------------------------------------------------------------ ground

        void BuildGround()
        {
            // Asphalt ring around the square (four slabs so the stairwell hole stays open).
            B.Box(0, -0.25f, -56, 160, 0.5f, 48, "asphalt");
            B.Box(0, -0.25f, 81, 160, 0.5f, 98, "asphalt");
            B.Box(-56, -0.25f, 0, 48, 0.5f, 64, "asphalt");
            B.Box(56, -0.25f, 0, 48, 0.5f, 64, "asphalt");
            // Plaza paving (raised 15 cm) with the metro stairwell cut out at x[-30,-24] z[4,18].
            B.Box(0, -0.075f, -14, 64, 0.45f, 36, "paving");
            B.Box(0, -0.075f, 25, 64, 0.45f, 14, "paving");
            B.Box(-31, -0.075f, 11, 2, 0.45f, 14, "paving");
            B.Box(4, -0.075f, 11, 56, 0.45f, 14, "paving");
            // Curbs
            B.Box(0, 0, -32.2f, 64.6f, 0.36f, 0.4f, "curb", collide: false);
            B.Box(0, 0, 32.2f, 64.6f, 0.36f, 0.4f, "curb", collide: false);
            B.Box(-32.2f, 0, 0, 0.4f, 0.36f, 64.6f, "curb", collide: false);
            B.Box(32.2f, 0, 0, 0.4f, 0.36f, 64.6f, "curb", collide: false);
            // Sidewalks outside the ring road
            B.Box(0, 0.05f, -47, 96, 0.2f, 6, "concrete_wet");
            B.Box(-47, 0.05f, 0, 6, 0.2f, 100, "concrete_wet");
            B.Box(47, 0.05f, 0, 6, 0.2f, 100, "concrete_wet");
            // Market street sidewalks and market square
            B.Box(-15, 0.05f, 57, 6, 0.2f, 26, "concrete_wet");
            B.Box(15, 0.05f, 57, 6, 0.2f, 26, "concrete_wet");
            B.Box(0, 0.06f, 91, 60, 0.2f, 42, "concrete_wet");
            // Lane markings (painted dashes; the prototype's were faintly emissive)
            for (var z = -28; z <= 28; z += 6)
            {
                B.Box(38, 0.005f, z, 0.15f, 0.01f, 2.5f, "metal_yellow", collide: false, shadow: false);
                B.Box(-38, 0.005f, z, 0.15f, 0.01f, 2.5f, "metal_yellow", collide: false, shadow: false);
            }
            // Rain puddles on the paving and the roads (visual only).
            var puddles = new (float x, float z, float r)[]
            {
                (-12, -8, 1.6f), (10, -14, 2.0f), (-18, 10, 1.4f), (6, 22, 1.8f), (24, -12, 1.2f), (-26, -20, 1.5f), (14, 6, 1.1f),
                (-38, 8, 2.2f), (38, 16, 1.8f), (-37, -26, 1.6f), (2, 46, 2.0f), (-4, 62, 1.5f), (-6, 84, 1.6f), (8, 104, 1.4f), (14, 92, 1.2f), (0, -40, 1.8f),
            };
            for (var i = 0; i < puddles.Length; i++)
            {
                var p = puddles[i];
                K.Puddle(p.x, GroundY(p.x, p.z), p.z, p.r, 4100 + i);
            }
        }

        // ------------------------------------------------------------------ monument

        void BuildMonument()
        {
            const float y = MonumentLift;
            // Plinth, fountain basin (water slot), pedestal with plaque, broken lower obelisk with cyan seams.
            K.Prop("Monument_Base", 0, y, 0, 0, 1, false);
            // Prototype colliders: two steps (tops 0.45 / 0.75), pedestal (top 1.5), obelisk shaft.
            K.CylCollider(0, 0.3f, 0, 7.6f, 0.3f, 48);
            K.CylCollider(0, 0.6f, 0, 6.6f, 0.3f, 48);
            K.CylCollider(0, 1.1f, 0, 2.6f, 0.8f, 32);
            K.CylCollider(0, 3.9f, 0, 1.3f, 5f, 12);
            K.Prop("Monument_CoreHolder", 0, 6.35f + y, 0, 0, 1, false);
            K.Prop("Monument_UpperShard", 0.2f, 8.6f + y, 0.1f, Mathf.PI / 6 + 0.1f, 1, false, 0, 0.07f);
            // Core floating in the break, broken halo rings (animated).
            core = K.DynamicProp("Monument_Crystal", CoreProto.x, CoreProto.y + y, CoreProto.z, 0, CoreScale);
            rings[0] = K.DynamicProp("Monument_Ring_A", 0, 7.45f + y, 0, 0, 1, false, RingTilt[0]);
            rings[1] = K.DynamicProp("Monument_Ring_B", 0, 9.3f + y, 0, 0, 1, false, RingTilt[1]);
            // Fallen ring segment on the base (long axis along the prototype collider's X).
            K.Prop("Monument_Ring_Fallen", 3.6f, 0.75f, 2.6f, 0.6f + Mathf.PI / 2, 1, false);
            B.SolidCollider(3.6f, 1.2f, 2.6f, 2.4f, 0.6f, 1.2f, 0.6f);
            // Whiter, tighter than the prototype's raw value so the paving isn't flooded with saturated cyan in URP.
            monumentLight = B.PointLight(0, 7.45f + y, 0, 0x9fe4ff, 380, 30, 1.5f);
            if (monumentLight != null) monumentPerUnit = monumentLight.intensity / 600f;
            B.GlowDecal(0, 0.8f + y, 0, 9, 0x5fd8ff, 0.25f);
            // Plaque on the pedestal front (manifest 'plaque': centre (0, 1.08, 2.5), tilted back 27 deg).
            K.Label(0, 1.08f + y + 0.02f, 2.54f, 0, 27 * Mathf.Deg2Rad, "AETHER-9  ·  WE LISTEN TO THE DEEP", 2.3f, 0.42f, 0x9fc8d8);
        }

        // ------------------------------------------------------------------ metro stairwell (west)

        void BuildStairwell()
        {
            // Hole x[-30,-24] z[4,18]; stairs descend southwards to y=-4.2, landing z[15.2,18].
            const float depth = 4.2f, run = 0.8f;
            const int steps = 14;
            for (var i = 0; i < steps; i++)
            {
                var top = -(i + 1) * (depth / steps);
                B.Box(-27, top, 4 + run * (i + 0.5f), 6, 0.3f, run, "concrete_dark", collide: false);
            }
            // Smooth ramp collider for the stairs.
            var ang = Mathf.Atan2(depth, steps * run);
            var hyp = Mathf.Sqrt(depth * depth + steps * run * steps * run);
            B.AddBoxCollider(V(-27, -depth / 2 - 0.12f, 4 + steps * run / 2), new Vector3(6, 0.2f, hyp), Rot(ang, 0, 0), CombatLayers.World);
            B.Box(-27, -depth - 0.15f, 16.6f, 6, 0.3f, 3.2f, "concrete_dark");
            // Walls of the well
            B.Box(-30.15f, -2.1f, 11, 0.3f, 4.5f, 14.4f, "concrete");
            B.Box(-23.85f, -2.1f, 11, 0.3f, 4.5f, 14.4f, "concrete");
            B.Box(-27, -2.1f, 18.15f, 6.6f, 4.5f, 0.3f, "concrete");
            B.Box(-27, -2.1f, 3.85f, 6.6f, 4.5f, 0.3f, "concrete", collide: false);
            // Tunnel doorway at the bottom: dark opening in a steel surround (amber header strip).
            B.Box(-27, -2.45f, 17.97f, 3.2f, 3.5f, 0.06f, "black", collide: false);
            K.Prop("DoorFrame_3x3_4", -27, -depth, 17.92f, Mathf.PI, 1, false);
            B.Box(-27, -0.32f, 17.98f, 3.0f, 0.05f, 0.04f, "emit_cyan", collide: false, shadow: false); // Line B accent above the surround
            B.GlowDecal(-27, -4.15f, 16.5f, 4, 0x5fd8ff, 0.5f);
            // Canopy: four posts, glass roof, steel edge beams.
            foreach (var x in new[] { -30.2f, -23.8f })
                foreach (var z in new[] { 4f, 18f })
                    B.Cyl(x, 1.8f, z, 0.08f, 0.08f, 3.6f, "metal_dark", 6, collide: false);
            B.Box(-27, 3.65f, 11, 7, 0.08f, 15, "glass", collide: false);
            B.Box(-27, 3.6f, 11, 7.2f, 0.15f, 0.2f, "metal_dark", collide: false);
            B.Box(-30.5f, 3.6f, 11, 0.12f, 0.15f, 15.2f, "metal_dark", collide: false);
            B.Box(-23.5f, 3.6f, 11, 0.12f, 0.15f, 15.2f, "metal_dark", collide: false);
            // Railings (with the prototype's blocking walls).
            K.Railing(-30.1f, 4, -30.1f, 18, 0.15f);
            K.Railing(-23.9f, 4, -23.9f, 18, 0.15f);
            K.Railing(-30.1f, 18.1f, -23.9f, 18.1f, 0.15f);
            B.PointLight(-27, -2.2f, 16, 0x8fd8ff, 80, 12, 1.6f);
        }

        // ------------------------------------------------------------------ city blocks

        void BuildBlocks()
        {
            var r = new PzRng(9);
            var blocks = new (float x, float z, float w, float d, float h)[]
            {
                // north row (gate gap at x[-12,12])
                (-58, -60, 24, 22, 26), (-34, -60, 20, 22, 18), (-20, -62, 12, 18, 12), (20, -62, 12, 18, 14), (34, -60, 20, 22, 22), (58, -60, 24, 22, 30),
                // west column
                (-60, -32, 22, 18, 20), (-62, -10, 22, 22, 15), (-60, 14, 22, 22, 24), (-62, 36, 22, 18, 17),
                // east column (behind elevated rail)
                (66, -34, 20, 20, 28), (66, -8, 20, 24, 18), (66, 18, 20, 22, 24), (66, 40, 20, 18, 16),
                // market street
                (-30, 52, 24, 16, 16), (30, 52, 24, 16, 20), (-30, 66, 24, 10, 12), (30, 66, 24, 10, 14),
                // market enclosure
                (-44, 82, 26, 22, 14), (-44, 104, 26, 20, 18), (44, 80, 26, 20, 16), (44, 102, 26, 22, 22), (0, 126, 64, 22, 20),
            };
            for (var i = 0; i < blocks.Length; i++)
            {
                var (x, z, w, d, h) = blocks[i];
                var faces = "";
                void Add(char c) { if (faces.IndexOf(c) < 0) faces += c; }
                if (z < -40) Add('s');
                if (x < -40 && z > -45 && z < 60) Add('e');
                if (x > 40 && z > -45 && z < 60) Add('w');
                if (z > 40 && z < 75 && x < 0) Add('e');
                if (z > 40 && z < 75 && x > 0) Add('w');
                if (z >= 75 && x < -20) Add('e');
                if (z >= 75 && x > 20) Add('w');
                if (z > 115) Add('n');
                if (faces.Length == 0) faces = "s";
                var lit = 0.05f + r.Next() * 0.06f;
                var shops = K.Building(x, z, w, d, h, 100 + i, lit, true, faces);
                if (z >= 75 && x < -20) marketWest.AddRange(shops);
                else if (z >= 75 && x > 20) marketEast.AddRange(shops);
            }
            // Lit shop fronts on the market enclosure (prototype storefronts: warm at z 76/96 west, cyan at 86/106 east).
            LitShop(marketWest, 76, true);
            LitShop(marketWest, 96, true);
            LitShop(marketEast, 86, false);
            LitShop(marketEast, 106, false);
        }

        void LitShop(List<PzKit.ShopFront> shops, float z, bool warm)
        {
            if (shops.Count == 0) return;
            var best = shops[0];
            foreach (var s in shops) if (Mathf.Abs(s.Pos.z - z) < Mathf.Abs(best.Pos.z - z)) best = s;
            var p = best.Pos;
            // Transom glass of Facade_Shop: 3.2 x 0.75 above the shutter (local y 2.0..2.75, z -0.06).
            var o = PzKit.Rot(p.x, p.z, best.Yaw, 0, -0.045f);
            K.Panel(o.x, p.y + 2.375f, o.y, 3.1f, 0.7f, best.Yaw, warm ? "win_warm" : "win_cool");
            var g = PzKit.Rot(p.x, p.z, best.Yaw, 0, 2.2f);
            B.GlowDecal(g.x, GroundY(g.x, g.y) + 0.02f, g.y, 5, warm ? 0xffb46au : 0x7fd8ffu, 0.35f);
        }

        // ------------------------------------------------------------------ facility gate (north) and skyline

        void BuildGate(bool open)
        {
            // Gate pylons + header for a 24 m opening; sliding leaves (animated when the flag flips during play).
            K.Prop("Gate_Facility_Frame", 0, 0, -46, 0, 1, false);
            B.SolidCollider(-13, 5, -46, 2, 10, 2);
            B.SolidCollider(13, 5, -46, 2, 10, 2);
            B.GlowSprite(-10, 9.0f, -44.6f, 0.6f, 0xff3a2e, 1.2f);
            B.GlowSprite(10, 9.0f, -44.6f, 0.6f, 0xff3a2e, 1.2f);
            gateOpen = open;
            gateLX = open ? -16 : -6;
            gateRX = open ? 16 : 6;
            gateLeft = K.DynamicProp("Gate_Facility_Leaf", gateLX, 0, -46);
            gateRight = K.DynamicProp("Gate_Facility_Leaf", gateRX, 0, -46);
            if (!open) gateCollider = B.AddBoxCollider(V(0, 4.3f, -46), new Vector3(24, 8.6f, 0.8f), Quaternion.identity, CombatLayers.World);
        }

        void OpenGate()
        {
            if (gateOpen) return;
            gateOpen = true;
            if (gateCollider != null)
            {
                gateCollider.gameObject.SetActive(false); // immediately out of physics and the NavMesh rebuild
                Destroy(gateCollider.gameObject);
                gateCollider = null;
                RefreshNavMesh();
            }
        }

        void BuildSkyline()
        {
            // Distant facility tower.
            B.Box(0, 22, -86, 30, 44, 22, "panel_lab", collide: false);
            for (var i = 0; i < 6; i++) B.Box(0, 6 + i * 6.5f, -74.9f, 26, 0.3f, 0.1f, "emit_cyan", collide: false, shadow: false);
            B.Box(0, 46, -86, 8, 4, 8, "metal_dark", collide: false);
            K.Antenna(0, 48, -86, 10, 0, false);
            // Background blocks beyond the perimeter (depth in the fog; no collision).
            // [OpenCity hook] the open district stands where these were: skip them.
            if (OpenCity.Enabled) return;
            var far = new (float x, float z, float h)[]
            {
                (-96, -92, 30), (-44, -104, 24), (46, -102, 34), (96, -82, 26), (-104, -24, 22), (-102, 52, 32),
                (104, 8, 30), (102, 72, 22), (-82, 124, 26), (76, 132, 30), (-30, 156, 36), (40, 162, 24),
            };
            for (var i = 0; i < far.Length; i++) K.SkylineBlock(far[i].x, 0, far[i].z, far[i].h, (i % 2) * Mathf.PI / 2);
        }

        // ------------------------------------------------------------------ elevated rail (east)

        void BuildRail()
        {
            for (var z = -70; z <= 70; z += 14)
            {
                K.Prop("ElevatedRail_Pier", 52, 0, z, 0, 1, false);
                B.SolidCollider(52, 4, z, 1.2f, 8, 1.2f);
            }
            // Deck spans (top at 9.2 like the prototype slab), joints over the piers.
            for (var k = 0; k < 12; k++) K.Prop("ElevatedRail_Deck_14m", 52, 9.2f, -77 + 14 * k, 0, 1, false);
            // Derailed tram hanging off the track, a chunk of the viaduct and rubble.
            K.Bus("Bus_Transit", 45.5f, 0, 20, 0.4f + Mathf.PI / 2, 77);
            K.Prop("Rubble_Chunk_L", 46, 0.15f, 21.5f, 0.3f, 2.0f, false);
            B.SolidCollider(46, 0.5f, 21.5f, 2, 1, 3, 0.3f);
            K.Debris(44, 0, 22, 3, 8, 78, ground: GroundY);
        }

        // ------------------------------------------------------------------ streets dressing

        void BuildStreets()
        {
            var cars = new (float x, float z, float yaw)[]
            {
                (-38, -20, 0.1f), (-39, 18, Mathf.PI + 0.3f), (38, -24, Mathf.PI - 0.15f), (37, 26, 0.6f), (-18, -38, Mathf.PI / 2 + 0.2f),
                (16, 38, -Mathf.PI / 2), (-5, 40, Mathf.PI / 2 + 0.5f), (6, 60, 0.15f), (-7, 66, Mathf.PI),
            };
            for (var i = 0; i < cars.Length; i++) K.Car(cars[i].x, GroundY(cars[i].x, cars[i].z), cars[i].z, cars[i].yaw, 300 + i);
            K.Bus("Bus_Transit", 39, 0, -6, 0.05f + Mathf.PI / 2, 401);
            var barriers = new (float x, float z, float yaw)[] { (-34, -34, 0.8f), (-33, -30, 0.4f), (34, 34, 2.4f), (30, -40, 0.2f), (-10, 44, 0.1f), (10, 44, -0.1f), (-26, 34, 1.4f) };
            for (var i = 0; i < barriers.Length; i++) K.Barrier(barriers[i].x, GroundY(barriers[i].x, barriers[i].z), barriers[i].z, barriers[i].yaw, i == 3 || i == 6);
            foreach (var (x, z) in new (float, float)[] { (-26, -26), (26, 26), (-22, 28), (36, 12), (-36, -6), (8, -38), (-4, 52), (12, 74), (-22, 106) })
                K.Debris(x, GroundY(x, z), z, 2.2f, 7, (int)(x * 31 + z), ground: GroundY);
            foreach (var (x, z, yaw) in new (float, float, float)[] { (-12, -18, 0.3f), (14, 16, 1.6f), (-16, 18, -0.9f), (-24, -10, 1.0f) }) K.Bench(x, 0.15f, z, yaw);
            foreach (var (x, z, tipped) in new (float, float, bool)[] { (-14, -20, false), (16, 18, true), (28, 10, false), (-20, 24, true) }) K.TrashBin(x, 0.15f, z, tipped);
            // Planters with dead trees around the square (collider 2.4 x 0.9 x 2.4 from y 0, as in the prototype).
            foreach (var (x, z) in new (float, float)[] { (-20, -20), (20, 20), (-20, 20), (24, -4), (-24, -4) }) K.Prop("Planter_DeadTree", x, 0, z, (x + z) * 0.1f);
            // A few cones and bollards at the facility approach and the market street mouth.
            foreach (var (x, z) in new (float, float)[] { (-9, -42.5f), (9, -42.5f), (-4, -43.2f), (4, -43.2f) }) K.Prop("Bollard", x, GroundY(x, z), z);
            foreach (var (x, z, yaw) in new (float, float, float)[] { (-8.5f, 42.5f, 0.2f), (-7.6f, 43.4f, 1.1f), (8.8f, 42.8f, 2.0f) }) K.Prop("TrafficCone", x, 0, z, yaw);

            // Street lights (some dead, a few flickering)
            var lamps = new (float x, float z, float yaw, bool on, bool flick)[]
            {
                (-30, -30, Mathf.PI / 4, true, false), (30, 30, -3 * Mathf.PI / 4, true, true), (-30, 30, 3 * Mathf.PI / 4, false, false),
                (-30, -6, Mathf.PI / 2, true, false), (30, -10, -Mathf.PI / 2, true, false), (0, -30, 0, true, true),
                (-13, 50, Mathf.PI / 2, true, false), (13, 62, -Mathf.PI / 2, true, true), (-20, 86, Mathf.PI / 2, true, false), (22, 100, -Mathf.PI / 2, false, false), (0, 108, Mathf.PI, true, false),
            };
            foreach (var l in lamps)
            {
                var lamp = K.StreetLamp(l.x, GroundY(l.x, l.z), l.z, l.yaw, l.on, l.on && Mathf.Abs(l.x) < 40, 0.9f);
                if (l.flick && lamp.Light != null) flickers.Add(new Flicker { Light = lamp.Light, Halo = lamp.Halo, Base = lamp.Base, Seed = l.x * 3 + l.z, On = true });
            }
        }

        void BuildSigns()
        {
            // Hung just under the canopy glass (the prototype board poked through it).
            B.Sign(-27, 3.0f, 3.6f, 5.5f, 1.1f, Mathf.PI, new[] { "TRANSIT  LINE B  ↓" }, fg: 0x7fe0ff, bg: 0x0a1a24, glow: 1.4f, border: 0x2d6f88);
            // On the gate header, in front of it (the prototype plane sat inside the header box).
            B.Sign(0, 9.5f, -44.68f, 14, 1.6f, 0, new[] { "AETHER RESEARCH DIVISION" }, fg: 0x9fd8ee, bg: 0x0c141a, glow: 1.1f, border: 0);
            // Market street signs mounted in front of the facade modules (prototype planes were behind the building faces).
            B.Sign(-17.3f, 6, 44.5f, 6, 1.4f, Mathf.PI / 2, new[] { "MARKET STREET" }, fg: 0xffb46a, bg: 0x1a120a, glow: 1.6f, border: 0x7a4a1e);
            B.Sign(17.3f, 8, 60, 5, 2.2f, -Mathf.PI / 2, new[] { "NOODLES", "24H" }, fg: 0xff7a8a, bg: 0x200a12, glow: 1.8f, border: 0);
            B.Sign(-17.3f, 7, 64, 4.6f, 1.8f, Mathf.PI / 2, new[] { "REPAIRS" }, fg: 0x7fffd0, bg: 0x08161a, glow: 1.3f, border: 0);
            // Hung on the elevated rail viaduct facing the plaza (the prototype sign floated above the sidewalk).
            B.Sign(49.3f, 8.6f, -20, 7, 1.6f, -Mathf.PI / 2, new[] { "CIVIC CENTER" }, fg: 0xc8d8ea, bg: 0x0b1016, glow: 0.9f, border: 0);
            B.PointLight(16.6f, 8, 60, 0xff7a8a, 30, 9, 1.6f);
        }

        // ------------------------------------------------------------------ survivors' camp (NE)

        void BuildCamp()
        {
            const float cx = 22, cz = -22, y = 0.15f;
            Shelter("TarpShelter_Large", cx + 4, cz - 4, 0.3f, 2.5f, 2.0f);
            Shelter("TarpShelter_Blue", cx - 3, cz - 6, -0.2f, 2.0f, 1.5f);
            Shelter("TarpShelter", cx + 6, cz + 3, 1.2f, 2.0f, 1.5f);
            for (var i = 0; i < 5; i++) K.CrateStack(cx - 6 + (i % 3) * 2.2f, y, cz + 5 + (i / 3) * 2, i * 0.4f, 500 + i);
            // Generator
            K.Prop("Generator_Industrial", cx - 7, y, cz - 1, 0);
            // Fire barrel
            K.Prop("FireBarrel", cx, y, cz, 0.4f, FireBarrelScale);
            // Manifest 'light' anchor (0, 1.15, 0) of the scaled barrel.
            fireLight = B.PointLight(cx, y + 1.15f * FireBarrelScale, cz, 0xff8a3a, 160, 16, 1.6f);
            if (fireLight != null) firePerUnit = fireLight.intensity / 160f;
            B.GlowDecal(cx, 0.17f, cz, 6, 0xff8a3a, 0.4f);
            // Radio table (Mira): workstation desk facing her, antenna mast.
            K.Prop("Terminal_Desk", cx + 4.5f, y, cz - 2.6f, 0);
            K.Antenna(cx + 6, y, cz - 3.4f, 6, 0.5f);
            // Sleeping mats, cases and a lantern.
            for (var i = 0; i < 3; i++) B.Box(cx + 3 + i * 1.2f, 0.2f, cz - 6, 0.9f, 0.06f, 2, "tarp_blue", collide: false, shadow: false);
            K.Prop("Crate_Small", cx + 1.6f, y, cz - 6.6f, 0.3f);
            K.Prop("Crate_Small", cx + 6.6f, y, cz - 5.2f, -0.5f);
            B.Box(cx + 3.5f, 1.95f, cz - 5, 0.16f, 0.24f, 0.16f, "emit_warm", collide: false, shadow: false);
            B.GlowSprite(cx + 3.5f, 2.0f, cz - 5, 0.8f, 0xffb46a, 1.2f);
            B.PointLight(cx + 3.5f, 1.85f, cz - 5, 0xffb46a, 18, 6, 1.6f);
            // Save terminal
            var scr = K.Terminal(cx - 8.5f, y, cz + 2.5f, Mathf.PI / 2 + 0.3f);
            saveScreen = new Vector3(scr.x, 1.37f, scr.y);
            // Barricade around the camp
            foreach (var (x, z, yaw) in new (float, float, float)[] { (cx - 10, cz - 8, 0.4f), (cx + 9, cz + 8, -0.7f), (cx - 10, cz + 8, 2.2f) })
                K.Barrier(x, GroundY(x, z), z, yaw);
            K.Prop("TrafficCone", cx - 11.4f, y, cz - 6.9f, 0.3f);
            K.Prop("Scrap_Metal", cx + 9.5f, y, cz - 7.5f, 1.1f, 0.8f, false);
        }

        /// <summary>Tarp shelter (P.tarpShelter): asset (taller back side at local -Z, like the prototype) with its four pole colliders.</summary>
        void Shelter(string name, float x, float z, float yaw, float hx, float hz)
        {
            K.Prop(name, x, 0.15f, z, yaw, 1, false);
            foreach (var (lx, lz) in new[] { (-hx, -hz), (hx, -hz), (-hx, hz), (hx, hz) })
            {
                var p = PzKit.Rot(x, z, yaw, lx, lz);
                K.PoleCollider(p.x, 0.15f, p.y, 0.06f, 2.4f);
            }
        }

        // ------------------------------------------------------------------ collapsed market

        void BuildMarket()
        {
            // Stalls in rows (same seeded jitter as the prototype); some collapsed.
            var r = new PzRng(77);
            var rows = new List<Vector3>();
            for (var z = 78; z <= 104; z += 7)
                foreach (var x in new[] { -20, -10, 10, 20 })
                {
                    var px = x + r.Range(-1, 1);
                    var pz = z + r.Range(-1, 1);
                    var yaw = (x < 0 ? Mathf.PI / 2 : -Mathf.PI / 2) + r.Range(-0.2f, 0.2f);
                    rows.Add(new Vector3(px, pz, yaw));
                }
            for (var i = 0; i < rows.Count; i++)
            {
                var (x, z, yaw) = (rows[i].x, rows[i].y, rows[i].z);
                if (i % 5 == 3)
                {
                    // Collapsed stall: tipped counter, tarp on the ground, scrap.
                    B.Box(x, 0.35f, z, 2.6f, 0.7f, 0.9f, "metal_painted", rotY: yaw, rotZ: 0.4f);
                    B.Box(x + 0.6f, 0.08f, z, 3, 0.04f, 1.6f, "tarp", rotY: yaw + 0.3f, collide: false, shadow: false);
                    var s = PzKit.Rot(x, z, yaw, -1.2f, 0.9f);
                    K.Prop("Debris_Pile_C", s.x, 0.16f, s.y, yaw, 0.8f, false);
                }
                else K.Prop(i % 2 == 1 ? "MarketStall" : "MarketStall_Blue", x, 0.16f, z, yaw);
            }
            // Goods and clutter between the stalls.
            foreach (var (x, z, yaw) in new (float, float, float)[] { (-14.5f, 80.5f, 0.3f), (14.8f, 88.2f, -0.6f), (-15.2f, 101.6f, 1.2f), (15.5f, 106.4f, 0.1f) })
                K.Prop("Crate_Wood", x, 0.16f, z, yaw);
            K.Prop("TrashBin_Tipped", -24.5f, 0.16f, 74.5f, 0.8f);
            K.Prop("TrashBin", 25.2f, 0.16f, 76.4f, 0);
            // Maintenance robots (deactivated)
            DeadRobot(4, 82, 0.5f);
            DeadRobot(-4, 100, 2.2f);
            // Fire escape + ladder on the east building (rooftop access, exit x_plaza_rooftops at (29.6, 91)).
            B.Box(30.0f, 4.5f, 92, 1.2f, 0.12f, 4, "grate", collide: false);
            B.Box(30.0f, 8.5f, 92, 1.2f, 0.12f, 4, "grate", collide: false);
            K.Railing(29.42f, 90.1f, 29.42f, 93.9f, 4.56f, false);
            K.Railing(29.42f, 90.1f, 29.42f, 93.9f, 8.56f, false);
            for (var k = 0; k < 3; k++) K.Prop("Ladder_4m", 31, 0.16f + k * 4, 91, -Mathf.PI / 2, 1, false);
            B.Box(30.93f, 2.4f, 92.1f, 0.06f, 0.18f, 0.4f, "emit_amber", collide: false, shadow: false);
            B.GlowSprite(30.8f, 2.4f, 92.1f, 0.7f, 0xffa21f, 0.8f);
            // Hanging cables and lanterns
            for (var i = 0; i < 6; i++)
            {
                var z = 78 + i * 5;
                const float sag = 0.6f;
                K.Cable(-28, 6, z, 28, 5.5f, z + 1, 0.02f, sag);
                var lx = -10 + i * 4f;
                var t = (lx + 28) / 56f;
                var ly = Mathf.Lerp(6, 5.5f, t) - sag * 4 * t * (1 - t) - 0.28f;
                var lz = z + t;
                B.Box(lx, ly, lz, 0.16f, 0.22f, 0.16f, "emit_warm", collide: false, shadow: false);
                B.GlowSprite(lx, ly, lz, 0.5f, i % 2 == 1 ? 0xff7a5au : 0xffd27au, 1.4f);
            }
            B.PointLight(0, 4.5f, 88, 0xffb46a, 160, 22, 1.6f);
            B.PointLight(-18, 3.5f, 102, 0x7fffd0, 90, 14, 1.6f);
            K.Debris(16, 0.16f, 108, 2.5f, 9, 911, true);
        }

        /// <summary>Deactivated maintenance robot lying on its side (capsule body, head, arm).</summary>
        void DeadRobot(float x, float z, float yaw)
        {
            B.AddMesh(FxMesh.RoundedBox(0.9f, 1.6f, 0.9f, 0.44f), "metal_yellow", new Vector3(x, 0.5f, z), Rot(0, yaw, Mathf.PI / 2 - 0.2f), colliderSize: Vector3.one);
            B.Box(x + 0.7f, 0.25f, z + 0.2f, 0.4f, 0.4f, 0.4f, "metal_dark", rotY: yaw, collide: false);
            B.Box(x + 0.7f, 0.3f, z + 0.41f, 0.22f, 0.06f, 0.02f, "black", rotY: yaw, collide: false, shadow: false);
            B.Cyl(x - 0.3f, 0.2f, z + 0.6f, 0.05f, 0.05f, 0.8f, "metal_dark", 6, collide: false, rotX: 1.3f);
            K.Prop("Scrap_Metal", x - 0.9f, 0.16f, z - 0.8f, yaw + 1.0f, 0.5f, false);
        }

        // ================================================================== gameplay layout

        void LayoutGameplay()
        {
            Spawn("start", -7, 0.16f, 12, Mathf.PI);
            Spawn("from_metro", -27, 0.16f, 1.5f, Mathf.PI);
            Spawn("from_facility", 0, 0.06f, -41, 0);
            Spawn("from_rooftops", 28.6f, 0.16f, 91, -Mathf.PI / 2);
            Spawn("camp", 16, 0.16f, -16, Mathf.PI * 0.75f);
            Marker("partner_wait", 19.5f, 0.16f, -18.5f);
            Marker("monument_drop", 3.5f, 0.2f, 9);
            Marker("fire", CampFireProto.x, CampFireProto.y, CampFireProto.z);
            Marker("save_screen", saveScreen.x, saveScreen.y, saveScreen.z);

            Exit("x_plaza_metro", "metro", "from_plaza", -27, -4.0f, 17.2f, 1.8f, "Enter the Metro", auto: true,
                lockedText: "Find the survivors first.", requiresFn: () => Flag("metro_open"));
            Exit("x_plaza_facility", "facility", "from_plaza", 0, 0.06f, -44.4f, 3, "Enter the Research Facility",
                lockedText: "The facility gate is sealed from the inside.", requiresFn: () => Flag("facility_gate_open"));
            Exit("x_plaza_rooftops", "rooftops", "from_market", 29.6f, 0.16f, 91, 1.6f, "Climb to the rooftops",
                lockedText: "Check in at the survivors' camp first.", requiresFn: () => Flag("swap_unlocked"));

            Trigger("t_plaza_camp", P(12, -1, -30), P(30, 4, -12));
            Trigger("t_market", P(-30, -1, 72), P(30, 6, 112));
            Trigger("t_plaza_monument", P(-9, -1, -9), P(9, 6, 9));

            Encounter("e_plaza_drones", "quest", new[] { Wave(E("drone", -9, 6, -22), E("drone", 0, 7.5f, -26), E("drone", 9, 6, -22)) }, P(0, 0, 0), 34);
            Encounter("e_market_patrol", "trigger:t_market", new[] { Wave(E("sentinel", -5, 0.2f, 86), E("sentinel", 7, 0.2f, 99), E("drone", 0, 6, 94)) }, P(0, 0, 92), 30);

            Collectible("c_frag_01", 39.4f, 3.3f, -6);
            Collectible("c_frag_02", -40, 0.8f, -32);
            Collectible("c_frag_03", 0.4f, 1.9f, -2.7f);
            Collectible("c_frag_04", 20, 1.5f, 82);
            Collectible("c_frag_05", -27, 0.8f, 110);
            Collectible("c_rec_01", 12.6f, 0.9f, -27.8f);
            Collectible("c_rec_02", 10.3f, 1.4f, 96);
            Collectible("c_cache_01", 27.5f, 0.6f, 74);

            Npc("oren", 19, 0.16f, -15.5f, Mathf.PI * 1.1f, "npc_crossed", "dlg_oren");
            Npc("mira", 26.5f, 0.16f, -23.6f, Mathf.PI * 0.5f, "npc_work", "dlg_mira");
            Npc("tomas", -9, 0.22f, 90, Mathf.PI * 0.4f, "npc_hips", "dlg_tomas");
            Npc("nia", NiaRoute[0].x, NiaRoute[0].y, NiaRoute[0].z, Mathf.PI * 0.3f, "wander", "dlg_nia", echoOnly: true);
            Marker("bolt", 14.5f, 0.16f, -26.5f);
            Npc("bolt", 14.5f, 0.16f, -26.5f, Mathf.PI * 0.8f, "idle", "dlg_bolt");

            QuestPoint("i_monument", P(0, 1.3f, 6.4f), "Inspect the Aether Monument", new[] { "stage:m1_awakening:monument" }, 3.4f);
            QuestPoint("i_bolt", P(14.5f, 1.0f, -25.2f), "Repair BOLT", new[] { "stage:sq_broken_guardian:repair" }, 2.4f);
            SaveTerminal("i_save_plaza", saveScreen, 2.2f);
            ItemPickup("i_market_cell", "q_power_cell_bolt", -19.6f, 1.15f, 92.2f, new[] { "quest:sq_broken_guardian:active" });
        }

        void BuildMap()
        {
            MapBounds(-50, -52, 50, 116);
            MapShape("road", 0, 0, 92, 92);
            MapShape("floor", 0, 0, 64, 64);
            MapShape("road", 0, 56, 24, 26);
            MapShape("floor", 0, 91, 60, 42);
            MapShape("block", -27, 11, 6, 14);
            MapShape("water", 0, 0, 14, 14);
            MapLabel("MONUMENT", 0, 0);
            MapLabel("CAMP", 22, -22);
            MapLabel("METRO", -27, 11);
            MapLabel("FACILITY GATE", 0, -46);
            MapLabel("MARKET", 0, 92);
            MapLabel("LADDER", 28, 92);
        }

        // ================================================================== runtime

        public override void OnLoaded()
        {
            base.OnLoaded();
            var nia = RT.FindNpc("nia");
            if (nia != null)
            {
                var route = new Vector3[NiaRoute.Length];
                for (var i = 0; i < route.Length; i++) route[i] = V(NiaRoute[i]);
                nia.gameObject.AddComponent<PzWander>().Init(nia, route);
            }
            swapUnlocked = Flag("swap_unlocked");
            City?.OnLoaded(RT); // [OpenCity hook] district points of interest
        }

        public override void OnEnter()
        {
            base.OnEnter();
            // Flames and smoke from the camp barrel, Aether motes rising from the monument basin.
            Emitter(CampFireProto.x, 0.15f + 0.954f * FireBarrelScale, CampFireProto.z, "fire", 14, 0.3f);
            Emitter(0, 0.95f, 0, "aether", 4, 4.5f);
            City?.OnEnter(); // [OpenCity hook] steam vents in the district
        }

        public override void OnFlag(string flag)
        {
            base.OnFlag(flag);
            if (flag == "facility_gate_open") OpenGate();
            else if (flag == "swap_unlocked") swapUnlocked = true;
            else if (flag == "bolt_repaired")
            {
                // The prototype only woke BOLT on the next zone load; wake it as soon as it is repaired.
                var bolt = RT != null ? RT.FindNpc("bolt") : null;
                if (bolt != null && !bolt.BoltActive)
                {
                    bolt.BoltActive = true;
                    bolt.ApplyBehaviour();
                }
            }
        }

        public override void Tick(float dt)
        {
            base.Tick(dt);
            var t = ZoneTime;
            flagPoll -= dt;
            if (flagPoll <= 0)
            {
                flagPoll = 0.25f;
                swapUnlocked = Flag("swap_unlocked");
                if (!gateOpen && Flag("facility_gate_open")) OpenGate();
            }
            if (core != null)
            {
                var pulse = 1 + Mathf.Sin(t * 2.2f) * 0.06f + (swapUnlocked ? 0 : Mathf.Max(0, Mathf.Sin(t * 6)) * 0.04f);
                coreAngle += dt * 0.3f;
                var sc = CoreScale * pulse;
                core.transform.localScale = new Vector3(sc, sc, sc);
                core.transform.localRotation = Quaternion.AngleAxis(-coreAngle * Mathf.Rad2Deg, Vector3.up);
            }
            for (var i = 0; i < rings.Length; i++)
            {
                if (rings[i] == null) continue;
                ringAngle[i] += dt * RingSpin[i];
                rings[i].transform.localRotation = Rot(RingTilt[i], 0, 0) * Quaternion.AngleAxis(ringAngle[i] * Mathf.Rad2Deg, Vector3.up);
            }
            if (monumentLight != null) monumentLight.intensity = monumentPerUnit * (560 + Mathf.Sin(t * 2.2f) * 80);
            if (fireLight != null) fireLight.intensity = firePerUnit * (150 + Mathf.Sin(t * 13) * 20 + Mathf.Sin(t * 7.3f) * 25);
            for (var i = 0; i < flickers.Count; i++)
            {
                var f = flickers[i];
                var on = Mathf.Sin(t * 1.3f + f.Seed) > -0.6f || Mathf.Sin(t * 37 + f.Seed) > 0.4f;
                if (on == f.On) continue;
                f.On = on;
                if (f.Light != null) f.Light.intensity = on ? f.Base : f.Base * 0.05f;
                if (f.Halo != null) f.Halo.SetActive(on);
                flickers[i] = f;
            }
            // Gate leaves slide open once the facility gate flag is set.
            if (gateOpen && gateLeft != null && gateRight != null && (gateLX > -15.99f || gateRX < 15.99f))
            {
                var k = Mathf.Min(1, dt * 0.8f);
                gateLX += (-16 - gateLX) * k;
                gateRX += (16 - gateRX) * k;
                gateLeft.transform.localPosition = V(gateLX, 0, -46);
                gateRight.transform.localPosition = V(gateRX, 0, -46);
            }
        }
    }
}
