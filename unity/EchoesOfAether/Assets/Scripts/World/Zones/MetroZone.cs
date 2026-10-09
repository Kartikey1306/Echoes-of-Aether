using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Abandoned Metro (Line B), port of src/world/zones/MetroZone.ts. Platform level y=0; concourse and entry corridor at
    /// y=4. Concourse x[-18,18] z[12,36]; stairs x[-4,4] z[32,42] down to the platform hall x[-44,44] z[42,58].
    /// Power room x[28,40] z[34,42] (junction puzzle); signal room x[-40,-28] z[34,42] (transmitter); maintenance bay
    /// x[-26,-20] z[37,42]; spur tunnel east along the track pit to x=70.
    ///
    /// Gameplay geometry (floors, walls, stairs, colliders) and every gameplay id/position match the prototype; the
    /// prototype's primitive props are replaced by the Blender environment kit (tunnel and track modules, platform edge,
    /// ticket gates, hanging lamps, train cars, generator, transmitter console, door leaf/frames, kiosks, debris).
    /// Where a prop replaces architecture (stairs, platform edge, trains, tunnel) it has no collider of its own and the
    /// prototype collider is kept.
    /// </summary>
    public sealed class MetroZone : ProceduralZone
    {
        public override string ZoneId => "metro";

        /// <summary>Concourse/corridor level (prototype upper LevelBuilder offset).</summary>
        const float Up = 4f;
        /// <summary>Rail-top height of the track modules (the prototype rails sat at -1.075).</summary>
        const float RailTop = -1.075f;
        /// <summary>Signal door rise when open (prototype centre 1.7 → 5).</summary>
        const float DoorOpenLift = 3.3f;

        static readonly int[] JunctionTarget = { 3, 0, 2 }; // elbow orientations that complete the circuit
        static readonly int[] JunctionStart = { 0, 2, 1 };
        static readonly float[] JunctionX = { 32.5f, 35f, 37.5f };
        const float JunctionY = 1.8f, JunctionZ = 34.25f;

        sealed class Junction
        {
            public Vector3 Pos; // prototype space
            public Transform Piece;
            public Material Mat;
            public int State;
            public float Angle;
        }

        readonly Junction[] junctions = new Junction[3];
        readonly Material[] conduitMats = new Material[6];
        readonly List<MfSwitch> lamps = new();
        readonly List<GameObject> lampHalos = new();
        readonly List<Light> emergency = new();
        readonly List<float> emergencyX = new();
        readonly List<Material> emergencyHalos = new();
        readonly List<float> emergencyHaloX = new();
        readonly List<Light> powerLights = new();
        readonly List<float> powerLightOn = new();
        Light signalLight;
        float signalUnit, unitEmergencyOff, unitEmergencyOn;
        Transform dyn, signalDoor;
        float doorLift;
        BoxCollider doorCollider;
        Material screenMat;
        GameObject barrier, barrierDecal;
        Material barrierMat, barrierStripMat;
        float barrierOpacity = 0.5f;
        BoxCollider barrierCollider;
        bool powered, barrierOpen, spurFlag;
        float splashT;
        Action unsubFlag;
        MfFlicker flicker;
        // Water drips (Unity-space splash points) for the dripping-ceiling ambience.
        Vector3[] drips;
        float[] dripT;

        // ================================================================== build

        protected override async Task BuildZone()
        {
            ZoneSettings(-10, true, "tension", "metro_drip");
            SetAtmosphere(new AtmosphereSettings
            {
                // Prototype: background 0x020304, env gradient {0x101418, 0x181c20, 0x060708} at 0.6, FogExp2(0x0a0c0e, 0.03),
                // hemi 0x5a6878/0x1a1612 0.9, shadowed key 0x8a9cb4 0.6 from (20,30,10).
                SolidBackground = true,
                SkyTop = 0x101418, SkyHorizon = 0x181c20, SkyBottom = 0x060708, Glow = 0x181c20, GlowStrength = 0.5f,
                FogColor = 0x0a0c0e, FogDensity = 0.03f,
                // Teal-grey tile ambient with sodium warmth from the grade; red emergency and white work lights are accents.
                HemiSky = 0x6a7878, HemiGround = 0x1e1912, HemiIntensity = 1.3f, EnvIntensity = 0.6f, CharacterFill = 3.2f,
                SunPos = new Vector3(20, 30, 10), SunTarget = Vector3.zero, SunColor = 0xa8b0b4, SunIntensity = 0.6f, SunShadows = true,
                Exposure = 1.38f, Contrast = 1.14f, Saturation = 1.04f,
                Lift = new Vector3(0.004f, 0.002f, 0f), Gain = new Vector3(1.02f, 1.0f, 0.975f), BloomThreshold = 0.85f,
                // cinematic grade: teal tile shadows against sodium-amber highlights, warm practical light kept saturated
                LightChroma = 0.7f, SplitShadows = 0x5f8486, SplitHighlights = 0xa08262, SplitBalance = -5f,
                GradeShadows = new Vector3(0.95f, 1.01f, 1.04f), GradeHighlights = new Vector3(1.06f, 1f, 0.92f), ShadowLift = 0.02f,
                Temperature = 5f, Vignette = 0.36f, LensStreaks = 0.6f,
            });
            B.LightBudget = 24;
            dyn = MfKit.DynamicRoot(transform);
            powered = Flag("metro_power_on");
            barrierOpen = Flag("spur_open");
            spurFlag = barrierOpen;
            unitEmergencyOff = MfKit.LightUnit(B, 16, 1.6f);
            unitEmergencyOn = MfKit.LightUnit(B, 22, 1.6f);
            await Progress(0.1f, "Tunnels");

            BuildEntry();
            BuildConcourse();
            await Progress(0.3f, "Concourse");

            BuildStairs();
            BuildPlatform();
            await Progress(0.5f, "Platform");

            BuildPowerRoom();
            BuildMaintenanceBay();
            BuildSignalRoom();
            await Progress(0.62f, "Control rooms");

            BuildSpur();
            // Bounds
            B.Wall(0, 3, -3, 10, 10, 1);
            SetPowered(powered, true);
            await Progress(0.8f, "Lighting");
            Layout();
            BuildMap();
        }

        // ------------------------------------------------------------------ entry corridor (y=4, from the plaza stairs)

        void BuildEntry()
        {
            B.Box(0, Up - 0.25f, 5, 6, 0.5f, 14, "tile_lab");
            B.Box(-3.25f, Up + 1.8f, 5, 0.5f, 3.6f, 14, "tile_lab");
            B.Box(3.25f, Up + 1.8f, 5, 0.5f, 3.6f, 14, "tile_lab");
            B.Box(0, Up + 3.85f, 5, 7, 0.5f, 14, "concrete_dark");
            B.Box(0, Up + 1.8f, -2.25f, 7, 3.6f, 0.5f, "concrete_dark");
            // Readability: cold street light spilling down the plaza stairs behind the spawn lights the hero's back (the
            // side the camera sees), and a dim fill from the red ceiling strips gives the corridor a red top light.
            B.PointLight(0, Up + 3.1f, -1.4f, 0xb8c8d8, 34, 10, 1.7f);
            B.PointLight(0, Up + 3.2f, 7f, 0xff4a3a, 24, 9, 1.8f);
            for (var z = 0; z < 12; z += 4)
            {
                B.Box(0, Up + 3.55f, z, 0.2f, 0.06f, 1.6f, "emit_red", collide: false);
                B.Box(0, Up + 3.585f, z, 0.32f, 0.03f, 1.75f, "metal_dark", collide: false, shadow: false);
                B.GlowSprite(0, Up + 3.42f, z, 0.9f, 0xff3a2e, 0.35f);
            }
            Sign(0, Up + 2.6f, 11.7f, 3.4f, 0.7f, Mathf.PI, "LINE B  ·  PLATFORM 2", 0x9fd8ee, 0x0c1418, 1.0f);
            // Dressing: dark skirting and a cable conduit on brackets along the east wall.
            B.Box(-2.98f, Up + 0.1f, 5, 0.04f, 0.2f, 14, "concrete_dark", collide: false, shadow: false);
            B.Box(2.98f, Up + 0.1f, 5, 0.04f, 0.2f, 14, "concrete_dark", collide: false, shadow: false);
            B.Cyl(2.72f, Up + 3.15f, 5, 0.1f, 0.1f, 14, "metal_dark", 10, collide: false, rotX: Mathf.PI / 2);
            B.Cyl(2.84f, Up + 2.9f, 5, 0.035f, 0.035f, 14, "cable", 6, collide: false, shadow: false, rotX: Mathf.PI / 2);
            for (var z = -1f; z < 12; z += 4) B.Prop("Pipe_Bracket", 3.0f, Up + 3.15f, z, -Mathf.PI / 2, 1, collide: false);
            B.Prop("TrafficCone", -2.2f, Up, 9.6f, 0.4f);
            B.Prop("Rubble_Chunk_S", 2.3f, Up, 2.4f, 1.2f, 1, collide: false);
        }

        // ------------------------------------------------------------------ concourse (y=4)

        void BuildConcourse()
        {
            B.Box(0, Up - 0.25f, 22, 36, 0.5f, 20, "floor_lab");
            B.Box(-12, Up - 0.25f, 34, 16, 0.5f, 4, "floor_lab");
            B.Box(12, Up - 0.25f, 34, 16, 0.5f, 4, "floor_lab");
            B.Box(0, Up + 6.25f, 24, 37, 0.5f, 25, "concrete_dark", collide: false);
            B.Box(-18.25f, Up + 3, 24, 0.5f, 6.5f, 25, "tile_lab");
            B.Box(18.25f, Up + 3, 24, 0.5f, 6.5f, 25, "tile_lab");
            B.Box(-10.5f, Up + 3, 11.75f, 15, 6.5f, 0.5f, "tile_lab");
            B.Box(10.5f, Up + 3, 11.75f, 15, 6.5f, 0.5f, "tile_lab");
            B.Box(-11, Up + 3, 36.25f, 14, 6.5f, 0.5f, "tile_lab");
            B.Box(11, Up + 3, 36.25f, 14, 6.5f, 0.5f, "tile_lab");
            B.Box(0, Up + 4.9f, 36.25f, 8, 2.7f, 0.5f, "tile_lab");
            // Header above the entry corridor opening (the prototype left the wall open above the 3.6 m corridor).
            B.Box(0, Up + 4.9f, 11.75f, 6, 2.7f, 0.5f, "tile_lab");
            // Skirting along the long walls.
            B.Box(-17.98f, Up + 0.12f, 24, 0.04f, 0.24f, 24, "concrete_dark", collide: false, shadow: false);
            B.Box(17.98f, Up + 0.12f, 24, 0.04f, 0.24f, 24, "concrete_dark", collide: false, shadow: false);

            // Columns: Blender 10 m column sunk so its capital meets the ceiling; prototype 0.9 m collider.
            foreach (var x in new[] { -12f, -6f, 6f, 12f })
            foreach (var z in new[] { 17f, 24f, 31f })
            {
                B.Prop("Pillar_Concrete_10m", x, Up + 6.25f - 10f, z, 0, 1, collide: false);
                B.SolidBox(x, Up + 3, z, 0.9f, 6.5f, 0.9f);
            }

            // Ticket gates (prototype: |x| % 4.8 < 1 → red).
            for (var k = 0; k < 14; k++)
            {
                var x = -16 + 2.4f * k;
                if (Mathf.Abs(x) < 1.5f) continue;
                B.Prop(Mathf.Abs(x) % 4.8f < 1 ? "Metro_TicketGate_Red" : "Metro_TicketGate", x, Up, 27, 0);
            }

            // Kiosks, benches, debris, collapsed ceiling.
            B.Prop("Terminal_Kiosk_Off", -14, Up, 20, Mathf.PI / 2);
            B.Prop("Terminal_Kiosk", 14, Up, 20, -Mathf.PI / 2);
            B.Prop("Terminal_Kiosk", -12, Up, 12.9f, 0); // save terminal
            B.Prop("Bench_Metal", -8, Up, 15, 0);
            B.Prop("Bench_Metal", 8, Up, 15, 0);
            // Fallen ceiling slab on its rubble heap; the prototype's tilted slab stays the (walkable) collider.
            B.Prop("Slab_Collapsed", 4, Up + 0.1f, 20, 0.4f, 1, collide: false);
            B.SolidBox(4, Up + 1.2f, 20, 5, 0.4f, 3, rotY: 0.4f, rotZ: 0.35f);
            B.Prop("Debris_Pile_A", 6.6f, Up, 22.4f, 1.1f);
            B.Prop("Rubble_Chunk_L", 2.6f, Up, 22.7f, 2.3f);
            B.Prop("Rubble_Chunk_S", 7.4f, Up, 19.2f, 0.6f);
            B.Prop("Rubble_Chunk_S", 1.9f, Up, 18.6f, 1.9f, 1, collide: false);
            B.Prop("Rubble_Chunk_S", 5.2f, Up, 23.6f, 2.8f, 1, collide: false);
            B.Prop("Rebar_Cluster", 5.4f, Up + 1.82f, 19.4f, 0.4f, 1, rotZ: 0.35f, collide: false);
            // The hole it fell from: dark void patch, rebar and cables hanging from the slab edge.
            B.Box(4.6f, Up + 5.99f, 19.8f, 4.4f, 0.02f, 2.6f, "black", rotY: 0.4f, collide: false, shadow: false);
            B.Prop("Rebar_Cluster", 3.0f, Up + 6.0f, 20.6f, 0.9f, 1, rotX: Mathf.PI, collide: false);
            B.Prop("Rebar_Cluster", 6.3f, Up + 6.0f, 19.1f, 2.6f, 1, rotX: Mathf.PI, collide: false);
            B.Box(2.6f, Up + 5.25f, 19.3f, 0.03f, 1.5f, 0.03f, "cable", collide: false, shadow: false, rotZ: 0.12f);
            B.Box(5.8f, Up + 5.0f, 21.0f, 0.03f, 2.0f, 0.03f, "cable", collide: false, shadow: false, rotX: 0.2f);

            Sign(0, Up + 4.4f, 35.9f, 5, 1.0f, Mathf.PI, "PLATFORM 2  ↓", 0x9fd8ee, 0x0c1418, 1.2f);
            Sign(-17.9f, Up + 3.5f, 22, 6, 1.3f, Mathf.PI / 2, "AETHER-9 TRANSIT AUTHORITY", 0xc8d8e8, 0x10161c, 0.7f);

            // Red emergency lights with ceiling beacons.
            B.PointLight(0, Up + 5.4f, 18, 0xff5a40, 60, 18, 1.6f);
            B.PointLight(0, Up + 5.4f, 30, 0xff5a40, 50, 16, 1.6f);
            foreach (var z in new[] { 18f, 30f })
            {
                B.Box(0, Up + 5.93f, z, 0.5f, 0.14f, 0.3f, "metal_dark", collide: false);
                B.Box(0, Up + 5.84f, z, 0.36f, 0.05f, 0.2f, "emit_red", collide: false, shadow: false);
                B.GlowSprite(0, Up + 5.72f, z, 1.5f, 0xff5a40, 0.5f);
            }
            // Fluorescent fixtures (dark until power is restored).
            foreach (var x in new[] { -9f, 0f, 9f })
            foreach (var z in new[] { 16f, 24f, 32f })
                Lamp(x, Up + 6.0f, z);
            // Puddles under the drips.
            Puddle(-6.5f, Up, 20.5f, 2.2f, 1.4f);
            Puddle(10.5f, Up, 30.2f, 1.6f, 1.1f);
        }

        // ------------------------------------------------------------------ stairs down to the platform

        void BuildStairs()
        {
            // Blender station stairs (4 m over 10 m, 8 m wide) + the prototype's ramp collider.
            B.Prop("Stairs_Concrete_8m", 0, 0, 42, Mathf.PI, 1, collide: false);
            B.StairsCollider(0, 0, 42, Mathf.PI, 8, 10, 0.4f, 1.0f);
            B.Box(-4.25f, 2.6f, 37, 0.5f, 5.2f, 10, "tile_lab");
            B.Box(4.25f, 2.6f, 37, 0.5f, 5.2f, 10, "tile_lab");
            // Close the stairwell above the flight (the prototype left it open to the void).
            B.Box(-4.25f, 6.4f, 39, 0.5f, 2.4f, 5.5f, "tile_lab");
            B.Box(4.25f, 6.4f, 39, 0.5f, 2.4f, 5.5f, "tile_lab");
            B.Box(0, 7.85f, 39, 9, 0.5f, 5.5f, "concrete_dark", collide: false);
            B.Box(0, 6.3f, 41.75f, 9, 2.6f, 0.5f, "tile_lab");
            Lamp(0, 7.6f, 39);
            // Handrails following the slope (prototype: a level rail at x=-3.8).
            var ang = Mathf.Atan2(4, 10);
            foreach (var s in new[] { -1f, 1f })
            {
                var x = s * 3.8f;
                B.Box(x, 3.0f, 37, 0.06f, 0.06f, 9.91f, "metal_yellow", collide: false, rotX: ang);
                for (var z = 33f; z <= 41.5f; z += 2.1f) B.Prop("Railing_Post", x, StairY(z) - 0.08f, z, 0, 1, collide: false);
            }
        }

        static float StairY(float z) => 4f * (42f - z) / 10f;

        // ------------------------------------------------------------------ platform hall (y=0)

        void BuildPlatform()
        {
            // Platform slab: visual up to the Blender edge modules, the prototype's full slab as collider.
            B.Box(0, -0.25f, 46.1f, 88, 0.5f, 8.21f, "concrete", collide: false);
            B.SolidBox(0, -0.25f, 47, 88, 0.5f, 10);
            for (var i = 0; i < 22; i++) B.Prop("Platform_Edge_4m", -42 + 4 * i, 0, 52.2f, 0, 1, collide: false);
            B.SolidBox(0, -0.65f, 52.1f, 88, 1.3f, 0.2f);
            // Track pit (y=-1.3): floor slab + Blender track modules (third rail on the far side).
            B.Box(0, -1.55f, 55, 88, 0.5f, 6, "concrete_dark");
            for (var i = 0; i < 11; i++) B.Prop("Metro_Track_8m", -40 + 8 * i, RailTop, 55, -Mathf.PI / 2, 1, collide: false);
            // Walls & ceiling
            B.Box(0, 1.5f, 58.25f, 90, 6, 0.5f, "tile_lab");
            B.Box(0, 4.75f, 50, 90, 0.5f, 17, "concrete_dark", collide: false);
            B.Box(-44.25f, 1.5f, 50, 0.5f, 6, 17, "tile_lab");
            // East end wall: the prototype left the platform end (x>44, z<51.5) open to the void.
            B.Box(44.25f, 1.5f, 46.75f, 0.5f, 6, 10.5f, "tile_lab");
            // North wall with openings: stairs x[-4,4], power door x[32.5,35.5], signal door x[-35.5,-32.5], bay x[-26,-20]
            float[] segA = { -44, -32.5f, -20, 4, 35.5f };
            float[] segB = { -35.5f, -26, -4, 32.5f, 44 };
            for (var i = 0; i < segA.Length; i++)
            {
                float a = segA[i], c = segB[i];
                B.Box((a + c) / 2, 1.5f, 41.75f, c - a, 6, 0.5f, "tile_lab");
                B.Box((a + c) / 2, 0.12f, 42.02f, c - a, 0.24f, 0.04f, "concrete_dark", collide: false, shadow: false);
            }
            B.Box(0, 3.75f, 41.75f, 8, 1.5f, 0.5f, "tile_lab");
            // Door headers at the 3.4 m door leaf / frame height (prototype header started at 2.0 m).
            B.Box(34, 3.95f, 41.75f, 3, 1.1f, 0.5f, "tile_lab");
            B.Box(-34, 3.95f, 41.75f, 3, 1.1f, 0.5f, "tile_lab");
            // Maintenance bay: half-open roller shutter in the prototype's 2.0-4.5 m header.
            B.Box(-23, 2.3f, 41.75f, 6, 0.6f, 0.44f, "corrugated");
            B.Box(-23, 2.03f, 41.75f, 6.02f, 0.06f, 0.46f, "metal_yellow", collide: false, shadow: false);
            B.Box(-23, 3.55f, 41.75f, 6, 1.9f, 0.5f, "tile_lab");
            // Columns along the platform (tiled Blender column, 4.4 m like the prototype).
            for (var x = -40; x <= 40; x += 8)
            {
                B.Prop("Pillar_Metro_4m", x, 0, 45.5f, 0);
                B.Box(x, 4.45f, 45.5f, 1.05f, 0.1f, 1.05f, "concrete_dark", collide: false);
            }
            // Platform lights (off until power is restored) and emergency lights.
            for (var x = -36; x <= 36; x += 12) Lamp(x, 4.5f, 48);
            foreach (var x in new[] { -24f, 0f, 24f })
            {
                var l = B.PointLight(x, 4.0f, 48, 0xe8f0ff, 70, 16, 1.7f);
                if (l != null) { powerLights.Add(l); powerLightOn.Add(l.intensity); }
            }
            foreach (var x in new[] { -30f, -6f, 18f, 38f })
            {
                var l = B.PointLight(x, 3.6f, 47, 0xff4030, 60, 16, 1.6f);
                if (l != null) { emergency.Add(l); emergencyX.Add(x); }
                B.Box(x, 4.3f, 46.2f, 0.4f, 0.2f, 0.2f, "emit_red", collide: false);
                B.Box(x, 4.45f, 46.2f, 0.5f, 0.1f, 0.3f, "metal_dark", collide: false);
                var halo = B.GlowSprite(x, 4.28f, 46.02f, 1.2f, 0xff4030, 0.55f);
                emergencyHalos.Add(MfKit.SpriteMat(halo));
                emergencyHaloX.Add(x);
            }
            // Derailed train on the track: Blender cars on the rails (vehicle front is local +X in the prototype → +π/2),
            // prototype footprint as the collider (extended down to the pit floor so nothing walks under the bogies).
            B.Prop("TrainCar_Metro_Lit", -22, RailTop, 55, 0.03f + Mathf.PI / 2, 1, collide: false);
            B.SolidBox(-22, 0.8f, 55, 16, 4.2f, 3, rotY: 0.03f);
            B.Prop("TrainCar_Metro", -4, RailTop, 56.2f, 0.12f + Mathf.PI / 2, 1, rotZ: 0.05f, collide: false);
            B.SolidBox(-4, 0.8f, 56.2f, 16, 4.2f, 3, rotY: 0.12f);
            B.PointLight(-22, 1.2f, 55, 0xffb878, 22, 9, 2); // warm spill from the lit car's windows
            B.Prop("Scrap_Metal", -34.5f, -1.3f, 54.6f, 0.7f);
            // Flooded section of track.
            B.Box(26, -0.96f, 55, 36, 0.02f, 5.8f, "water", collide: false, shadow: false);
            // Platform clutter
            B.Prop("Bench_Metal", -12, 0, 44, 0);
            B.Prop("Bench_Metal", 12, 0, 44, 0);
            B.Prop("Crate_Stack", 24, 0, 44, 0.2f);
            B.Prop("Crate_Cargo_Red", -40, 0, 47, 1.1f);
            B.Prop("Crate_Wood", -40.3f, 0, 48.6f, 0.5f);
            B.Prop("TrashBin_Tipped", 8, 0, 43.5f, 2.4f);
            B.Prop("Debris_Pile_C", 30, 0, 48, 0.8f);
            B.Prop("Rubble_Chunk_S", 31.5f, 0, 47.1f, 2.1f, 1, collide: false);
            B.Prop("Rubble_Chunk_L", 28.5f, 0, 49.2f, 0.3f);
            B.Prop("TrafficCone", 21.2f, 0, 50.6f, 0.2f);
            B.Prop("TrafficCone", 22.4f, 0.17f, 50.9f, 1.3f, 1, rotZ: Mathf.PI / 2 - 0.1f, collide: false);
            // Service pipe along the back wall.
            B.Cyl(0, 3.7f, 57.72f, 0.14f, 0.14f, 88, "metal_rusted", 10, collide: false, rotZ: Mathf.PI / 2);
            for (var x = -40; x <= 40; x += 8) B.Prop("Pipe_Bracket", x + 4, 3.7f, 58.0f, Mathf.PI, 1, collide: false);
            Puddle(-20, 0, 47.2f, 2.6f, 1.6f);
            Puddle(10, 0, 49.2f, 1.8f, 1.2f);
            Puddle(-34, 0, 44.4f, 2.2f, 1.3f);

            Sign(0, 3.2f, 58, 6, 1.1f, Mathf.PI, "LINE B  ·  WESTBOUND", 0xc8d8e8, 0x10161c, 0.8f);
            // Room signs above the doors, facing the platform (the prototype mounted them on the rooms' side of the wall).
            Sign(34, 4.02f, 42.03f, 3.4f, 0.6f, 0, "POWER CONTROL", 0xffb46a, 0x1a1008, 1.2f);
            Sign(-34, 4.02f, 42.03f, 3.4f, 0.6f, 0, "SIGNAL ROOM", 0x7fe0ff, 0x08141a, 1.2f);
            Sign(-23, 3.0f, 42.03f, 3.6f, 0.6f, 0, "MAINTENANCE", 0xd0d0d0, 0x141414, 0.8f);

            // Drip points (prototype space x, ceiling-to-floor) over the puddles.
            drips = new[] { V(-20, 0.02f, 47.2f), V(10, 0.02f, 49.2f), V(-34, 0.02f, 44.4f), V(-6.5f, Up + 0.02f, 20.5f), V(10.5f, Up + 0.02f, 30.2f), V(30, -0.93f, 55.5f) };
            dripT = new float[drips.Length];
            for (var i = 0; i < dripT.Length; i++) dripT[i] = 0.4f + i * 0.37f;
        }

        // ------------------------------------------------------------------ power room (junction puzzle)

        void BuildPowerRoom()
        {
            ServiceRoom(28, 40, 34, 42, "panel_lab");
            B.Prop("Generator_Industrial", 30, 0, 35.2f, 0);
            Marker("generator", 30, 1, 36.2f);
            // Wall-mounted junction board
            B.Box(35, 2.2f, 34.15f, 9, 3.2f, 0.1f, "metal_dark", collide: false);
            B.Box(35, 3.83f, 34.17f, 9.1f, 0.06f, 0.14f, "metal_bare", collide: false, shadow: false);
            B.Box(35, 0.57f, 34.17f, 9.1f, 0.06f, 0.14f, "metal_bare", collide: false, shadow: false);
            for (var i = 0; i < 3; i++) junctions[i] = MakeJunction(i);
            // Fixed conduits between junctions (light up as the circuit completes).
            const float jy = JunctionY;
            Conduit(0, 31.1f, jy, 32.1f, jy); // generator -> J1 (left)
            Conduit(1, 32.5f, jy + 0.4f, 32.5f, jy + 1.0f); // J1 up
            Conduit(2, 32.5f, jy + 1.0f, 35, jy + 1.0f); // over
            Conduit(3, 35, jy + 1.0f, 35, jy + 0.4f); // into J2 top
            Conduit(4, 35.4f, jy, 37.1f, jy); // J2 right -> J3 left
            Conduit(5, 37.5f, jy - 0.4f, 37.5f, jy - 0.9f); // J3 down -> breaker
            B.Box(37.5f, jy - 1.15f, 34.25f, 0.5f, 0.4f, 0.12f, "metal_red", collide: false);
            B.Box(37.5f, jy - 1.15f, 34.32f, 0.12f, 0.2f, 0.04f, "metal_bare", collide: false, shadow: false);
            Sign(35, 3.55f, 34.22f, 4, 0.45f, 0, "ROUTE POWER: GENERATOR → BREAKER", 0xffb46a, 0x140c06, 1.0f);
            B.PointLight(35, 3, 38, 0xffa060, 40, 10, 1.6f);
            B.Prop("Lab_CeilingLight_Warm", 35, 4.0f, 38, 0, 1, collide: false);
            B.Prop("Junction_Box", 40, 0, 37.4f, -Mathf.PI / 2);
            B.Prop("Crate_Small", 38.9f, 0, 40.6f, 0.3f);
            B.Prop("DoorFrame_3x3_4", 34, 0, 41.75f, 0, 1, collide: false);
        }

        /// <summary>Prototype MetroZone.room(): floor, ceiling and three walls (the platform wall closes the fourth side).</summary>
        void ServiceRoom(float x0, float x1, float z0, float z1, string mat)
        {
            B.Box((x0 + x1) / 2, -0.25f, (z0 + z1) / 2, x1 - x0, 0.5f, z1 - z0, "floor_lab");
            B.Box((x0 + x1) / 2, 4.25f, (z0 + z1) / 2, x1 - x0, 0.5f, z1 - z0, "concrete_dark", collide: false);
            B.Box(x0 - 0.25f, 2, (z0 + z1) / 2, 0.5f, 4.5f, z1 - z0, mat);
            B.Box(x1 + 0.25f, 2, (z0 + z1) / 2, 0.5f, 4.5f, z1 - z0, mat);
            B.Box((x0 + x1) / 2, 2, z0 - 0.25f, x1 - x0 + 1, 4.5f, 0.5f, mat);
            B.Box((x0 + x1) / 2, 0.08f, z0 + 0.02f, x1 - x0, 0.16f, 0.04f, "metal_dark", collide: false, shadow: false);
        }

        Junction MakeJunction(int i)
        {
            var pos = new Vector3(JunctionX[i], JunctionY, JunctionZ);
            var g = new GameObject("Junction" + (i + 1)) { layer = CombatLayers.World }.transform;
            g.SetParent(dyn, false);
            g.localPosition = V(pos);
            B.MeshObject("Back", FxMesh.CylinderZ(0.42f, 0.42f, 0.02f, 32), EnvMaterials.Get("metal_dark"), new Vector3(0, 0, -0.01f), Quaternion.identity, false, g);
            B.MeshObject("Ring", FxMesh.Torus(0.42f, 0.05f, 8, 32), EnvMaterials.Get("metal"), Vector3.zero, Quaternion.identity, false, g);
            var mat = MfKit.Glow(0xff8040, 2, "junction");
            var piece = new GameObject("Piece") { layer = CombatLayers.World }.transform;
            piece.SetParent(g, false);
            B.MeshObject("Bar1", FxMesh.Box(0.08f, 0.4f, 0.05f), mat, new Vector3(0, 0.2f, 0.03f), Quaternion.identity, false, piece);
            B.MeshObject("Bar2", FxMesh.Box(0.4f, 0.08f, 0.05f), mat, new Vector3(0.2f, 0, 0.03f), Quaternion.identity, false, piece);
            B.MeshObject("Hub", FxMesh.CylinderZ(0.07f, 0.07f, 0.06f, 12), mat, new Vector3(0, 0, 0.03f), Quaternion.identity, false, piece);
            var j = new Junction { Pos = pos, Piece = piece, Mat = mat, State = JunctionStart[i] };
            j.Angle = -j.State * (Mathf.PI / 2);
            piece.localRotation = Rot(0, 0, j.Angle);
            return j;
        }

        void Conduit(int index, float x1, float y1, float x2, float y2)
        {
            var m = MfKit.Glow(0x401010, 1, "conduit");
            var len = Mathf.Sqrt((x2 - x1) * (x2 - x1) + (y2 - y1) * (y2 - y1));
            B.MeshObject("Conduit", FxMesh.Box(len, 0.07f, 0.04f), m, new Vector3((x1 + x2) / 2, (y1 + y2) / 2, 34.24f), Rot(0, 0, Mathf.Atan2(y2 - y1, x2 - x1)), false, dyn);
            conduitMats[index] = m;
        }

        // ------------------------------------------------------------------ maintenance bay

        void BuildMaintenanceBay()
        {
            ServiceRoom(-26, -20, 37, 42, "concrete_dark");
            B.Prop("Crate_Stack", -24.5f, 0, 38.2f, 0.3f);
            // Workbench (prototype top + collider; the actuator pickup sits on it).
            B.Box(-21, 0.9f, 38, 1.2f, 0.06f, 0.8f, "wood");
            foreach (var lx in new[] { -0.52f, 0.52f })
            foreach (var lz in new[] { -0.32f, 0.32f })
                B.Box(-21 + lx, 0.435f, 38 + lz, 0.05f, 0.87f, 0.05f, "metal_dark", collide: false);
            B.Box(-21, 0.25f, 38, 1.1f, 0.03f, 0.7f, "metal_dark", collide: false);
            B.Prop("Crate_Small", -21.1f, 0.265f, 38.05f, 0.2f, 0.9f, collide: false);
            B.Prop("Shelving_Unit", -25.67f, 0, 40.4f, Mathf.PI / 2);
            Lamp(-23, 4.0f, 39.5f);
        }

        // ------------------------------------------------------------------ signal room (locked until powered)

        void BuildSignalRoom()
        {
            ServiceRoom(-40, -28, 34, 42, "panel_lab");
            var door = B.Prop("Door_Sliding_Metal", -34, 0, 41.8f, 0, 1, collide: false);
            door.transform.SetParent(dyn, true);
            signalDoor = door.transform;
            if (!powered) doorCollider = B.SolidBox(-34, 1.7f, 41.8f, 3, 3.4f, 0.3f);
            B.Prop("DoorFrame_3x3_4", -34, 0, 41.75f, 0, 1, collide: false);
            // Transmitter console; its screen slot is tinted by power (prototype transmitterGlow).
            B.Prop("Console_Transmitter", -34, 0, 35.2f, 0);
            screenMat = MfKit.Glow(0x101820, 1, "transmitter_screen");
            B.Quad("TransmitterScreen", dyn, -34, 2.3f, 34.885f, 0, 2.6f, 2.2f, screenMat);
            B.Prop("Antenna_Mast_3m", -38.5f, 0, 35.3f, 0.3f);
            B.GlowSprite(-38.5f, 3.12f, 35.3f, 0.6f, 0xff3030, 1.2f);
            signalLight = B.PointLight(-34, 3.4f, 38.5f, 0x8fd8ff, 70, 14, 1.6f);
            signalUnit = MfKit.LightUnit(B, 14, 1.6f);
            if (signalLight != null) signalLight.intensity = 0;
            Marker("transmitter", -34, 1.4f, 36.4f);
            var fixture = B.Prop("Lab_CeilingLight", -34, 4.0f, 38.5f, 0, 1, collide: false);
            lamps.Add(MfSwitch.Find(fixture, "emit_", null, EnvMaterials.Get("black")));
            B.Prop("Shelving_Unit", -28.33f, 0, 38.8f, -Mathf.PI / 2);
            B.Prop("Crate_Small", -29.0f, 0, 36.0f, 1.2f);
            B.Prop("Terminal_Desk", -38.6f, 0, 40.2f, Mathf.PI / 2);
        }

        // ------------------------------------------------------------------ spur tunnel east (to the facility)

        void BuildSpur()
        {
            B.Box(57, -1.55f, 55, 26, 0.5f, 6, "concrete_dark");
            // Blender tunnel lining replaces the prototype's wall/ceiling boxes (their colliders are kept). The lining continues
            // past the prototype's end wall (now an invisible blocker) and fades into darkness.
            B.SolidBox(57, 1.5f, 51.75f, 26, 6, 0.5f);
            B.SolidBox(57, 1.5f, 58.25f, 26, 6, 0.5f);
            B.Wall(70.25f, 1.5f, 55, 0.5f, 6, 7);
            B.Box(81, -1.55f, 55, 22, 0.5f, 6, "concrete_dark", collide: false);
            B.Box(92.3f, 1.0f, 55, 0.5f, 6, 7.2f, "black", collide: false, shadow: false);
            for (var i = 0; i < 6; i++)
            {
                var x = 48 + 8 * i;
                B.Prop("Metro_Tunnel_8m_NoWalk", x, RailTop, 55, -Mathf.PI / 2, 1, collide: false);
                B.Prop("Metro_Track_8m", x, RailTop, 55, -Mathf.PI / 2, 1, collide: false);
                // Halos on the lining's wall lamps (local ±2 m, 3 m above rail, on the south wall).
                B.GlowSprite(x - 2, RailTop + 3.0f, 57.7f, 0.8f, 0xffb46a, 0.45f);
                B.GlowSprite(x + 2, RailTop + 3.0f, 57.7f, 0.8f, 0xffb46a, 0.45f);
            }
            PortalFill(44);
            B.PointLight(51, 1.4f, 56.6f, 0xffb46a, 26, 12, 1.8f);

            // Energy barrier
            barrierMat = MfKit.Additive(0xff3a2e, 1.6f, 0.5f);
            barrier = B.MeshObject("Barrier", LevelKit.QuadMesh, barrierMat, new Vector3(45, 0.7f, 55), YawQ(Mathf.PI / 2), false, dyn);
            barrier.transform.localScale = new Vector3(6, 4, 1);
            barrierStripMat = EnvMaterials.EmissiveInstance(Hex(0xff3a2e), 3f);
            foreach (var z in new[] { 52.14f, 57.86f })
            {
                B.Box(45, 0.55f, z, 0.32f, 3.7f, 0.26f, "metal_dark", collide: false);
                B.MeshObject("BarrierEmitter", FxMesh.Box(0.08f, 3.3f, 0.04f), barrierStripMat, new Vector3(44.82f, 0.55f, z), Quaternion.identity, false, dyn);
                B.MeshObject("BarrierEmitter", FxMesh.Box(0.08f, 3.3f, 0.04f), barrierStripMat, new Vector3(45.18f, 0.55f, z), Quaternion.identity, false, dyn);
            }
            barrierDecal = B.GlowDecal(45, -1.27f, 55, 4.5f, 0xff3a2e, 0.25f);
            if (!barrierOpen) barrierCollider = B.SolidBox(45, 0.7f, 55, 0.4f, 6, 6);
            else OpenBarrier(true);
            Sign(46, 1.65f, 52.03f, 3.2f, 0.55f, 0, "SPUR → RESEARCH FACILITY", 0x7fe0ff, 0x08141a, 1.0f);

            // Steps between platform and track pit (to reach the tunnel): prototype stairs; tops 1 cm low so the
            // platform edge module on top doesn't z-fight, collider unchanged.
            const float sx = 41.5f, sy = -1.3f, sz = 53.6f, rise = 0.433f, run = 0.6f;
            for (var i = 0; i < 3; i++)
            {
                var h = rise * (i + 1) - 0.01f;
                B.Box(sx, sy + h / 2, sz - run * (i + 0.5f), 2.5f, h, run, "metal_dark", rotY: Mathf.PI, collide: false);
                B.Box(sx, sy + h + 0.004f, sz - run * i - 0.04f, 2.5f, 0.008f, 0.08f, "metal_yellow", collide: false, shadow: false);
            }
            B.StairsCollider(sx, sy, sz, Mathf.PI, 2.5f, 3, rise, run);
        }

        /// <summary>
        /// Tile wall around the tunnel mouth in the hall's east end: stepped boxes whose inner corners follow the lining's
        /// arch (spring 3.2, crown 4.6 above rail, half width 3), so the gap between the arch and the hall ceiling is closed.
        /// </summary>
        void PortalFill(float x)
        {
            const int n = 7;
            const float hw = 3f, spring = 3.2f, crown = 4.6f, top = 4.5f, outer = 3.6f;
            var px = x - 0.12f;
            for (var k = 0; k < n; k++)
            {
                float a0 = k / (float)n * (Mathf.PI / 2), a1 = (k + 1) / (float)n * (Mathf.PI / 2);
                float y0 = RailTop + spring + (crown - spring) * Mathf.Sin(a0), y1 = RailTop + spring + (crown - spring) * Mathf.Sin(a1);
                var w = hw * Mathf.Cos(a0);
                foreach (var s in new[] { -1f, 1f })
                {
                    float zi = 55 + s * w, zo = 55 + s * outer;
                    B.Box(px, (y0 + y1) / 2, (zi + zo) / 2, 0.3f, y1 - y0, Mathf.Abs(zo - zi), "tile_lab", collide: false);
                }
            }
            var yc = RailTop + crown;
            B.Box(px, (yc + top) / 2, 55, 0.3f, top - yc, outer * 2, "tile_lab", collide: false);
        }

        // ------------------------------------------------------------------ set dressing helpers

        void Lamp(float x, float yCeil, float z)
        {
            var go = B.Prop("Metro_LampTube", x, yCeil, z, Mathf.PI / 2, 1, collide: false);
            lamps.Add(MfSwitch.Find(go, "emit_", EnvMaterials.Get("emit_white"), EnvMaterials.Get("black")));
            lampHalos.Add(B.GlowSprite(x, yCeil - 0.5f, z, 1.3f, 0xe8f0ff, 0.35f));
            if (flicker == null && Mathf.Approximately(x, -36) && Mathf.Approximately(z, 48))
                flicker = new MfFlicker { Switch = lamps[lamps.Count - 1], Halo = lampHalos[lampHalos.Count - 1] };
        }

        void Puddle(float x, float y, float z, float w, float d) =>
            B.Box(x, y + 0.006f, z, w, 0.01f, d, "water", rotY: x * 0.37f, collide: false, shadow: false);

        void Sign(float x, float y, float z, float w, float h, float yaw, string text, uint fg, uint bg, float glow) =>
            B.Sign(x, y, z, w, h, yaw, new[] { text }, fg, bg, glow * 0.5f, fg);

        // ================================================================== gameplay layout

        void Layout()
        {
            Spawn("start", 0, 4.05f, 1, 0);
            Spawn("from_plaza", 0, 4.05f, 1, 0);
            Spawn("from_facility", 62, -1.25f, 55, -Mathf.PI / 2);

            Exit("x_metro_plaza", "plaza", "from_metro", 0, 4.05f, -1.2f, 1.6f, "Return to the plaza", auto: true);
            Exit("x_metro_facility", "facility", "from_metro", 66, -1.25f, 55, 2.5f, "Follow the spur tunnel", auto: true,
                requires: new[] { "flag:spur_open" }, lockedText: "An energy barrier seals the spur tunnel.");

            Trigger("t_metro_concourse", P(-18, 3, 12), P(18, 9, 36));
            Trigger("t_metro_platform", P(-44, -2, 42), P(44, 5, 52));

            Encounter("e_metro_concourse", "quest", new[]
            {
                Wave(E("drone", -8, 8.5f, 26), E("drone", 8, 8.6f, 24), E("drone", 0, 8.8f, 31)),
            }, P(0, 4, 24), 20);
            Encounter("e_metro_platform", "quest", new[]
            {
                Wave(E("sentinel", -14, 0.05f, 47), E("sentinel", 16, 0.05f, 48)),
                Wave(E("drone", 0, 3.4f, 49), E("sentinel", 26, 0.05f, 46)),
            }, P(0, 0, 47), 46);
            Encounter("e_metro_tunnel", "quest", new[]
            {
                Wave(E("sentinel", 36, 0.05f, 47), E("sentinel", 40, 0.05f, 45), E("drone", 30, 3.4f, 50)),
            }, P(30, 0, 50), 30);

            Collectible("c_frag_06", -42.5f, 1.0f, 46);
            Collectible("c_frag_07", 34, -0.4f, 56.5f);
            Collectible("c_rec_03", -18, 1.0f, 51.0f);
            Collectible("c_cache_02", -21.2f, 0.6f, 40.8f);
            ItemPickup("i_metro_actuator", "q_actuator", -21, 1.15f, 38, new[] { "quest:sq_broken_guardian:active" });

            // Junctions
            for (var i = 0; i < 3; i++)
            {
                var idx = i;
                Interactable($"i_junction_{i + 1}", "puzzle", junctions[i].Pos + new Vector3(0, 0, 0.8f), 1.4f, $"Rotate junction {i + 1}",
                    () => RotateJunction(idx), () => !powered);
            }
            Interactable("i_generator", "inspect", P(30, 1, 36.2f), 2.2f, "Inspect generator",
                () => Hint("The generator is running, but power isn't reaching the breaker. Rotate the three junctions so the conduit runs from the generator to the breaker."),
                () => !powered);
            QuestPoint("i_transmitter", P(-34, 1.4f, 36.4f), "Investigate the transmitter", new[] { "stage:m2_dead_signal:transmitter" }, 2.6f);
            SaveTerminal("i_save_metro", P(-12, 5.3f, 13.3f), 2);
        }

        void BuildMap()
        {
            MapBounds(-46, -4, 72, 60);
            MapShape("floor", 0, 5, 6, 14);
            MapShape("floor", 0, 24, 36, 24);
            MapShape("road", 0, 37, 8, 10);
            MapShape("floor", 0, 47, 88, 10);
            MapShape("road", 0, 55, 88, 6);
            MapShape("water", 26, 55, 36, 6);
            MapShape("block", 34, 38, 12, 8);
            MapShape("block", -34, 38, 12, 8);
            MapShape("block", -23, 39.5f, 6, 5);
            MapShape("road", 57, 55, 26, 6);
            MapLabel("CONCOURSE", 0, 22);
            MapLabel("PLATFORM 2", 0, 47);
            MapLabel("POWER", 34, 38);
            MapLabel("SIGNAL", -34, 38);
            MapLabel("SPUR", 58, 55);
        }

        // ================================================================== puzzle / power

        void RotateJunction(int i)
        {
            var j = junctions[i];
            j.State = (j.State + 1) % 4;
            Sfx("metal_impact", V(j.Pos));
            UpdateCircuit();
        }

        void UpdateCircuit()
        {
            bool ok0 = junctions[0].State == JunctionTarget[0], ok1 = junctions[1].State == JunctionTarget[1], ok2 = junctions[2].State == JunctionTarget[2];
            SetJunctionColor(0, ok0);
            SetJunctionColor(1, ok1);
            SetJunctionColor(2, ok2);
            var all = ok0 && ok1 && ok2;
            // Conduits light progressively along the path.
            SetConduit(0, true);
            SetConduit(1, ok0);
            SetConduit(2, ok0);
            SetConduit(3, ok0 && ok1);
            SetConduit(4, ok0 && ok1);
            SetConduit(5, all);
            if (all && !powered)
            {
                SetPowered(true, false);
                SetFlag("metro_power_on");
                Sfx("door", signalDoor != null ? signalDoor.position : (Vector3?)null);
                Hint("Power restored. The signal room is open.");
            }
        }

        void SetJunctionColor(int i, bool ok) => MfKit.SetGlow(junctions[i].Mat, ok ? 0x52ff9au : 0xff8040u, 2);

        void SetConduit(int i, bool lit) => MfKit.SetGlow(conduitMats[i], lit ? 0x5fd8ffu : 0x401010u, lit ? 2.2f : 1);

        void SetPowered(bool on, bool instant)
        {
            powered = on;
            foreach (var l in lamps) l.Set(on);
            foreach (var h in lampHalos) if (h != null) h.SetActive(on);
            if (flicker != null) { flicker.Enabled = on; if (on) flicker.Apply(true); }
            for (var i = 0; i < emergency.Count; i++)
            {
                var e = emergency[i];
                e.color = Hex(on ? 0xdfe8ffu : 0xff4030u);
                e.range = on ? 22 : 16;
                e.intensity = on ? 110 * unitEmergencyOn : 60 * unitEmergencyOff;
            }
            for (var i = 0; i < powerLights.Count; i++) powerLights[i].intensity = on ? powerLightOn[i] : 0;
            if (signalLight != null) signalLight.intensity = on ? 70 * signalUnit : 0;
            if (on)
            {
                if (doorCollider != null)
                {
                    doorCollider.gameObject.SetActive(false);
                    Destroy(doorCollider.gameObject);
                    doorCollider = null;
                    RefreshNavMesh();
                }
                MfKit.SetGlow(screenMat, 0x5fd8ff, 1.5f);
                if (instant)
                {
                    doorLift = DoorOpenLift;
                    ApplyDoor();
                }
                for (var i = 0; i < 3; i++)
                {
                    var j = junctions[i];
                    j.State = JunctionTarget[i];
                    j.Angle = -j.State * (Mathf.PI / 2);
                    j.Piece.localRotation = Rot(0, 0, j.Angle);
                }
            }
            for (var i = 0; i < 3; i++) SetJunctionColor(i, junctions[i].State == JunctionTarget[i]);
            if (on) for (var i = 0; i < conduitMats.Length; i++) SetConduit(i, true);
        }

        void ApplyDoor()
        {
            if (signalDoor != null) signalDoor.localPosition = V(-34, doorLift, 41.8f);
        }

        void OpenBarrier(bool instant)
        {
            barrierOpen = true;
            if (barrierCollider != null)
            {
                barrierCollider.gameObject.SetActive(false);
                Destroy(barrierCollider.gameObject);
                barrierCollider = null;
                RefreshNavMesh();
            }
            EnvMaterials.SetEmission(barrierStripMat, Hex(0xff3a2e), 0.15f);
            if (barrierDecal != null) barrierDecal.SetActive(false);
            if (instant && barrier != null) barrier.SetActive(false);
        }

        // ================================================================== runtime

        public override void OnLoaded()
        {
            base.OnLoaded();
            unsubFlag = Bus.On<FlagSet>(OnFlagSet);
        }

        void OnFlagSet(FlagSet e)
        {
            if (e.Flag == "spur_open") spurFlag = Flag("spur_open");
        }

        void OnDestroy()
        {
            unsubFlag?.Invoke();
            unsubFlag = null;
        }

        public override void OnEnter()
        {
            base.OnEnter();
            // Sparks from broken fixtures and drips.
            Emitter(4, 5.8f, 20, "sparks", 3);
            Emitter(-30, 4.3f, 46.3f, "sparks", 3);
            Emitter(18, 4.3f, 46.3f, "sparks", 2);
            Emitter(30, 1.7f, 35.2f, "steam", 2);
            UpdateCircuit();
            if (powered) SetPowered(true, true);
        }

        public override void Tick(float dt)
        {
            base.Tick(dt);
            // Junction pieces animate toward their target rotation.
            var k = Mathf.Min(1, dt * 12);
            for (var i = 0; i < 3; i++)
            {
                var j = junctions[i];
                var want = -j.State * (Mathf.PI / 2);
                j.Angle += (want - j.Angle) * k;
                j.Piece.localRotation = Rot(0, 0, j.Angle);
            }
            if (powered && doorLift < DoorOpenLift)
            {
                doorLift = Mathf.Min(DoorOpenLift, doorLift + dt * 1.5f);
                ApplyDoor();
            }
            if (!barrierOpen && spurFlag) OpenBarrier(false);
            if (barrier != null && barrier.activeSelf)
            {
                if (barrierOpen)
                {
                    barrierOpacity = Mathf.Max(0, barrierOpacity - dt * 0.5f);
                    if (barrierOpacity <= 0) barrier.SetActive(false);
                }
                else barrierOpacity = 0.35f + Mathf.Sin(ZoneTime * 4) * 0.12f;
                FxMaterials.SetAlpha(barrierMat, barrierOpacity);
            }
            if (!powered)
            {
                for (var i = 0; i < emergency.Count; i++)
                    emergency[i].intensity = (45 + Mathf.Sin(ZoneTime * 3 + emergencyX[i]) * 15) * unitEmergencyOff;
                for (var i = 0; i < emergencyHalos.Count; i++)
                    MfKit.SetSprite(emergencyHalos[i], 0xff4030, 0.55f * (0.75f + Mathf.Sin(ZoneTime * 3 + emergencyHaloX[i]) * 0.25f));
            }
            flicker?.Tick(dt);
            TickWater(dt);
        }

        void TickWater(float dt)
        {
            var player = Player;
            if (player != null)
            {
                // Splashes while wading through the flooded track (prototype box (8,-2,52)-(44,0.2,58)).
                var p = PlayerProto;
                if (p.x >= 8 && p.x <= 44 && p.y >= -2 && p.y <= 0.2f && p.z >= 52 && p.z <= 58)
                {
                    splashT -= dt;
                    var v = player.Velocity;
                    if (v.x * v.x + v.z * v.z > 1 && splashT <= 0)
                    {
                        splashT = 0.18f;
                        var pos = PlayerPos;
                        pos.y = -0.9f;
                        Vfx?.SparksDir(pos, Vector3.up, 6, Hex(0x8ab0c8), 2.5f);
                    }
                }
            }
            if (drips == null) return;
            for (var i = 0; i < drips.Length; i++)
            {
                dripT[i] -= dt;
                if (dripT[i] > 0) continue;
                dripT[i] = 0.9f + UnityEngine.Random.value * 2.2f;
                Vfx?.SparksDir(drips[i], Vector3.up, 3, Hex(0x9ab8cc), 1.3f);
            }
        }
    }
}
