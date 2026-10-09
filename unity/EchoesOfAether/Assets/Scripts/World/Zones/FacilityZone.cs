using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Aether Research Division, port of src/world/zones/FacilityZone.ts. Grid layout (x east, z south):
    ///  North row z[-20,0]:  lift room x[-44,-30] | hidden office x[-30,-14] | north hall x[-14,14] | Maren's lab x[14,34]
    ///  Middle  z[0,30]:     west wing x[-44,-14] (containment, server / corridor / Lab A, Lab B) | atrium x[-14,14] | offices x[14,34]
    ///  South   z[30,46]:    lobby x[-12,12]  (main gate to the plaza)
    ///  East:                spur station x[34,48] z[0,20] (to the metro)
    ///
    /// Rooms, walls and all gameplay data are the prototype's; furniture and equipment are Blender environment props
    /// (reception desk, lab benches, server racks, cryo pods, workstations, chairs, kiosks, hologram pedestal, columns,
    /// railings, ceiling lights, metro car and track, sliding gate leaves). Props that replace prototype architecture
    /// keep the prototype collider (pedestal, train).
    /// </summary>
    public sealed class FacilityZone : ProceduralZone
    {
        public override string ZoneId => "facility";

        const string HiddenDoorId = "i_maren_hidden_door";

        Transform dyn;
        // Hologram: core + three rings (prototype holo[]), rotation accumulators in prototype Euler XYZ radians.
        readonly Transform[] holo = new Transform[4];
        readonly float[] holoRx = new float[4], holoRy = new float[4];
        // Server-room security field.
        GameObject fieldMesh;
        Material fieldMat;
        bool fieldOn = true;
        float fieldT, fieldHitCd;
        Light alarm;
        float alarmUnit;
        Material alarmHalo;
        Vector3 fieldPosUnity;
        // Hidden office door (Echo Sight).
        GameObject hiddenWall;
        // Main gate (visual; the exit itself is gated by facility_gate_open as in the prototype).
        Transform gateL, gateR;
        Material gateLamp, gateLampHalo;
        float gateT;
        bool gateOpen;
        Action unsubFlag;
        readonly List<MfFlicker> flickers = new();

        // ================================================================== build

        protected override async Task BuildZone()
        {
            ZoneSettings(-10, true, "tension", "facility_hum");
            SetAtmosphere(new AtmosphereSettings
            {
                // Prototype: background 0x05080b, env gradient {0x1a2530, 0x223040, 0x0a0e12} at 0.8, FogExp2(0x0a0f14, 0.009),
                // hemi 0x9ab4cc/0x20242a 1.0, shadowed key 0xc8dcf0 1.2 from (10,40,18).
                SolidBackground = true,
                SkyTop = 0x1a2530, SkyHorizon = 0x223040, SkyBottom = 0x0a0e12, Glow = 0x223040, GlowStrength = 0.5f,
                // Clinical cool-white base (neutral ambient, white key); colour comes from the warm office lamps, cyan lab
                // screens and the red alarms.
                FogColor = 0x0c1014, FogDensity = 0.009f,
                HemiSky = 0xb4c2ce, HemiGround = 0x24262a, HemiIntensity = 1.25f, EnvIntensity = 0.8f,
                SunPos = new Vector3(10, 40, 18), SunTarget = Vector3.zero, SunColor = 0xe4ebf2, SunIntensity = 1.3f, SunShadows = true,
                Exposure = 1.2f, Contrast = 1.1f, Saturation = 1.02f,
                Lift = new Vector3(0f, 0.001f, 0.003f), Gain = new Vector3(0.995f, 1.0f, 1.01f), BloomThreshold = 0.88f,
                // cinematic grade: cool blue-teal shadows, faintly warm highlights (office lamps), a touch more colour
                SplitShadows = 0x72868f, SplitHighlights = 0x8e8478, GradeShadows = new Vector3(0.97f, 1f, 1.04f), GradeHighlights = new Vector3(1.03f, 1f, 0.97f),
                ShadowLift = 0.015f, Temperature = -2f, Vignette = 0.3f, LensStreaks = 0.5f,
            });
            B.LightBudget = 24;
            dyn = MfKit.DynamicRoot(transform);
            gateOpen = Flag("facility_gate_open");
            gateT = gateOpen ? 1 : 0;
            await Progress(0.1f, "Facility shell");

            BuildLobby();
            BuildAtrium();
            await Progress(0.3f, "Atrium");

            BuildWestWing();
            await Progress(0.45f, "Laboratories");

            BuildOffices();
            BuildSpurStation();
            BuildNorthRow();
            await Progress(0.6f, "Offices");

            Layout();
            BuildMap();
        }

        static MfRoomOptions Lab() => new() { Floor = "floor_lab", Wall = "panel_lab", Ceiling = "panel_lab", Panels = "emit_white", Trim = "metal_dark" };

        // ------------------------------------------------------------------ lobby + main gate

        void BuildLobby()
        {
            var o = Lab();
            o.Skip = "n";
            o.Doors = new[] { new MfDoor('s', 0, 6, 3.6f) };
            B.Room(-12, 30, 12, 46, 5, o);
            // Reception (staff side north, toward the atrium) with the gate control and save terminals.
            B.Prop("Desk_Reception", 0, 0, 37, 0);
            B.Prop("Terminal_Kiosk", -2, 0, 36.4f, Mathf.PI);
            B.Prop("Terminal_Kiosk_Off", 2, 0, 36.4f, Mathf.PI);
            B.Prop("Office_Chair", -0.4f, 0, 35.3f, 2.7f);
            B.GlassWall(-12, 34, -5, 34, 3.2f);
            B.GlassWall(5, 34, 12, 34, 3.2f);
            Sign(0, 3.9f, 30.3f, 9, 1.0f, Mathf.PI, "AETHER RESEARCH DIVISION", 0x9fd8ee, 0x0b1218, 1.1f);
            foreach (var x in new[] { -9f, 9f }) B.Prop("Bench_Street", x, 0, 42, 0);
            B.Prop("Planter_DeadTree", -10.2f, 0, 31.7f, 0.4f);
            B.Prop("Planter_DeadTree", 10.2f, 0, 31.7f, 2.1f);
            B.Prop("Debris_Pile_C", 8.4f, 0, 44.6f, 1.4f);
            B.Prop("TrashBin", -11.3f, 0, 44.9f, 0);
            // Vestibule outside the main door (prototype: floor + invisible walls).
            B.Box(0, -0.25f, 48, 10, 0.5f, 4, "concrete_wet");
            B.Wall(0, 2, 50.2f, 10, 4, 0.4f);
            B.Wall(-5.2f, 2, 48, 0.4f, 4, 4);
            B.Wall(5.2f, 2, 48, 0.4f, 4, 4);
            B.PointLight(0, 4, 40, 0xe8f2ff, 70, 18, 1.6f);
            BuildGate();
        }

        /// <summary>Visual vestibule and sliding gate (two heavy door leaves) that open with facility_gate_open.</summary>
        void BuildGate()
        {
            B.Box(-5.2f, 2, 48.2f, 0.4f, 4, 4.4f, "concrete", collide: false);
            B.Box(5.2f, 2, 48.2f, 0.4f, 4, 4.4f, "concrete", collide: false);
            B.Box(0, 4.15f, 48.3f, 10.8f, 0.3f, 4.6f, "concrete_dark", collide: false);
            B.Box(-4.2f, 2, 50.4f, 2.4f, 4, 0.4f, "concrete", collide: false);
            B.Box(4.2f, 2, 50.4f, 2.4f, 4, 0.4f, "concrete", collide: false);
            B.Box(0, 3.7f, 50.4f, 6, 0.6f, 0.4f, "concrete", collide: false);
            B.Box(0, -0.25f, 53.8f, 12, 0.5f, 6.4f, "concrete_wet", collide: false);
            B.Prop("Lab_CeilingLight", 0, 4.0f, 48.2f, 0, 1, collide: false);
            gateL = B.Prop("Door_Sliding_Metal", -1.5f, 0, 50.75f, 0, 1, collide: false).transform;
            gateR = B.Prop("Door_Sliding_Metal", 1.5f, 0, 50.75f, 0, 1, collide: false).transform;
            gateL.SetParent(dyn, true);
            gateR.SetParent(dyn, true);
            gateLamp = EnvMaterials.EmissiveInstance(Hex(0xff3a2e), 3);
            B.MeshObject("GateLamp", FxMesh.Box(0.36f, 0.12f, 0.06f), gateLamp, new Vector3(0, 3.55f, 50.17f), Quaternion.identity, false, dyn);
            gateLampHalo = MfKit.SpriteMat(B.GlowSprite(0, 3.55f, 50.05f, 0.7f, 0xff3a2e, 0.6f));
            ApplyGate();
        }

        void ApplyGate()
        {
            var e = gateT * gateT * (3 - 2 * gateT);
            if (gateL != null) gateL.localPosition = V(-1.5f - 3f * e, 0, 50.75f);
            if (gateR != null) gateR.localPosition = V(1.5f + 3f * e, 0, 50.75f);
            var c = gateOpen ? 0x52ff9au : 0xff3a2eu;
            EnvMaterials.SetEmission(gateLamp, Hex(c), 3);
            MfKit.SetSprite(gateLampHalo, c, 0.6f);
        }

        // ------------------------------------------------------------------ atrium

        void BuildAtrium()
        {
            var o = Lab();
            o.Ceiling = "glass_dark";
            o.Panels = null;
            o.Doors = new[] { new MfDoor('n', 0, 4, 3.2f), new MfDoor('s', 0, 12, 5), new MfDoor('w', 15, 4, 3.2f), new MfDoor('e', 10, 4, 3.2f) };
            B.Room(-14, 0, 14, 30, 10, o);
            // Skylight frame under the dark glass roof.
            foreach (var x in new[] { -7f, 0f, 7f }) B.Box(x, 9.85f, 15, 0.3f, 0.3f, 30.8f, "metal_dark", collide: false);
            foreach (var z in new[] { 7.5f, 15f, 22.5f }) B.Box(0, 9.85f, z, 28.8f, 0.3f, 0.3f, "metal_dark", collide: false);
            // Balcony ring (visual) and columns
            foreach (var x in new[] { -10f, 10f })
            foreach (var z in new[] { 5f, 15f, 25f })
                B.Prop("Pillar_Concrete_10m", x, 0, z, 0);
            B.Box(-12.5f, 5, 15, 3, 0.3f, 30, "panel_lab", collide: false);
            B.Box(12.5f, 5, 15, 3, 0.3f, 30, "panel_lab", collide: false);
            B.Box(-11.02f, 4.87f, 15, 0.04f, 0.03f, 29.6f, "emit_cyan", collide: false, shadow: false);
            B.Box(11.02f, 4.87f, 15, 0.04f, 0.03f, 29.6f, "emit_cyan", collide: false, shadow: false);
            B.RailingRun(-11, 0.5f, -11, 29.5f, 5.15f);
            B.RailingRun(11, 0.5f, 11, 29.5f, 5.15f);
            // Aether hologram centrepiece: Blender pedestal (prototype cylinder collider r 2.8, h 0.8), animated core and rings.
            B.Prop("Holo_Pedestal", 0, 0, 15, 0, 1, collide: false);
            B.SolidCylinder(0, 0.4f, 15, 2.8f, 0.8f);
            holo[0] = B.MeshObject("HoloCore", FxMesh.Sphere(1.1f, 32, 20), EnvMaterials.Aether(new Color(0.37f, 0.85f, 1f), 1f), new Vector3(0, 3.6f, 15), Quaternion.identity, false, dyn).transform;
            var ringMat = EnvMaterials.Get("emit_cyan");
            for (var i = 0; i < 3; i++)
            {
                holoRx[i + 1] = Mathf.PI / 2 + i * 0.5f;
                holoRy[i + 1] = i;
                holo[i + 1] = B.MeshObject("HoloRing", FxMesh.Torus(1.8f + i * 0.5f, 0.02f, 6, 64), ringMat, new Vector3(0, 3.6f, 15), Rot(holoRx[i + 1], holoRy[i + 1], 0), false, dyn).transform;
            }
            B.GlowSprite(0, 3.6f, 15, 4.5f, 0x5fd8ff, 0.18f);
            B.GlowDecal(0, 0.9f, 15, 6, 0x5fd8ff, 0.2f);
            B.PointLight(0, 3.6f, 15, 0x5fd8ff, 160, 22, 1.6f);
            B.PointLight(0, 8.5f, 6, 0xe8f2ff, 90, 24, 1.5f);
            Marker("warden_drop", 0, 1.2f, 9);
        }

        // ------------------------------------------------------------------ west wing

        void BuildWestWing()
        {
            B.Box(-29, -0.25f, 15, 30, 0.5f, 30, "floor_lab");
            B.Box(-29, 4.25f, 15, 30.8f, 0.5f, 30.8f, "panel_lab", collide: false);
            // Outer walls (n with door to the lift room; w; s)
            B.Box(-41.3f, 2, -0.2f, 6.2f, 4, 0.4f, "panel_lab");
            B.Box(-24.8f, 2, -0.2f, 22, 4, 0.4f, "panel_lab");
            B.Box(-37, 3.5f, -0.2f, 2.8f, 1, 0.4f, "panel_lab");
            B.Box(-44.2f, 2, 15, 0.4f, 4, 30.8f, "panel_lab");
            B.Box(-29, 2, 30.2f, 30.8f, 4, 0.4f, "panel_lab");
            // Internal walls: z=13 (doors at -37, -22) and glass at z=17 for the labs
            WallZ(13, -37, -22);
            B.GlassWall(-44, 17, -38.2f, 17, 3);
            B.GlassWall(-35.8f, 17, -23.2f, 17, 3);
            B.GlassWall(-20.8f, 17, -14, 17, 3);
            B.Box(-30, 2, 6.5f, 0.3f, 4, 13, "panel_lab");
            B.GlassWall(-30, 17, -30, 30, 3);
            // Corridor ceiling lights (prototype emissive panels); one of them is failing.
            for (var x = -42; x < -15; x += 5)
            {
                var p = B.Prop("Lab_CeilingLight", x, 4.0f, 15, 0, 1, collide: false);
                if (x == -27) AddFlicker(p);
            }

            // Lab A & B
            LabBench(-40, 22, 0, 1);
            LabBench(-34, 22, 0, 2);
            LabBench(-40, 26.5f, 0, 3);
            B.Prop("Terminal_Kiosk", -41, 0, 28.6f, Mathf.PI);
            LabBench(-26, 21.5f, 0, 4);
            LabBench(-19, 21.5f, 0, 5);
            LabBench(-26, 26, 0.1f, 6);
            B.Prop("Terminal_Kiosk", -24, 0, 28.6f, Mathf.PI);
            B.PointLight(-37, 3.6f, 23, 0xe8f2ff, 60, 14, 1.6f);
            B.PointLight(-22, 3.6f, 23, 0xe8f2ff, 50, 14, 1.6f);
            foreach (var x in new[] { -40f, -34f, -25.5f, -19f })
                B.Prop("Lab_CeilingLight", x, 4.0f, 23.5f, 0, 1, collide: false);
            B.Prop("Office_Chair", -34.6f, 0, 23.0f, 2.9f);
            B.Prop("Office_Chair", -18.4f, 0, 22.6f, 3.5f);
            B.Prop("Office_Chair", -36.5f, 0.3f, 27.6f, 0.6f, 1, rotX: 1.45f, collide: false); // knocked over
            B.Prop("Crate_Small", -43.2f, 0, 29.2f, 0.2f);
            B.Prop("Debris_Pile_C", -15.6f, 0, 18.4f, 0.5f);

            // Containment (pods) and server room
            Pod(-41, 4, true);
            Pod(-36.5f, 4, false);
            Pod(-33, 4, true);
            Pod(-41, 9, true);
            Pod(-33, 9, false);
            for (var i = 0; i < 6; i++)
            {
                var x = -28 + 2.2f * i;
                B.Prop("Server_Rack", x, 0, 2, 0);
                B.Prop("Server_Rack", x, 0, 11, Mathf.PI);
            }
            B.Prop("Terminal_Kiosk", -15.2f, 0, 6.5f, -Mathf.PI / 2);
            alarm = B.PointLight(-22, 3.4f, 6.5f, 0xff3a2e, 40, 12, 1.6f);
            alarmUnit = MfKit.LightUnit(B, 12, 1.6f);
            B.Box(-22, 3.93f, 6.5f, 0.5f, 0.14f, 0.5f, "metal_dark", collide: false);
            B.Box(-22, 3.83f, 6.5f, 0.3f, 0.08f, 0.3f, "emit_red", collide: false, shadow: false);
            alarmHalo = MfKit.SpriteMat(B.GlowSprite(-22, 3.7f, 6.5f, 1.4f, 0xff3a2e, 0.6f));
            fieldMat = MfKit.Additive(0xff3a2e, 1.8f, 0.4f);
            fieldMesh = B.MeshObject("SecurityField", FxMesh.Box(12, 2.6f, 2.6f), fieldMat, new Vector3(-22, 1.3f, 6.5f), Quaternion.identity, false, dyn);
            fieldPosUnity = fieldMesh.transform.position;
            foreach (var x in new[] { -28.2f, -15.8f })
            {
                B.Box(x, 1.4f, 6.5f, 0.3f, 2.8f, 0.3f, "metal_red", collide: false);
                B.Box(x, 2.86f, 6.5f, 0.4f, 0.12f, 0.4f, "metal_dark", collide: false);
                B.Box(x, 0.06f, 6.5f, 0.4f, 0.12f, 0.4f, "metal_dark", collide: false);
            }
        }

        /// <summary>Prototype wallZ: lab-panel wall along x at `z` from -44 to -14 with 2.4 m doors (3 m tall) at the gaps.</summary>
        void WallZ(float z, params float[] gaps)
        {
            var cur = -44f;
            foreach (var g in gaps)
            {
                B.Box((cur + g - 1.2f) / 2, 2, z, g - 1.2f - cur, 4, 0.3f, "panel_lab");
                B.Box(g, 3.5f, z, 2.4f, 1, 0.3f, "panel_lab");
                cur = g + 1.2f;
            }
            B.Box((cur - 14) / 2, 2, z, -14 - cur, 4, 0.3f, "panel_lab");
        }

        void LabBench(float x, float z, float yaw, int seed) => B.Prop(seed % 2 == 1 ? "Lab_Bench" : "Lab_Bench_B", x, 0, z, yaw);

        void Pod(float x, float z, bool glowing)
        {
            B.Prop(glowing ? "CryoPod" : "CryoPod_Empty", x, 0, z, 0);
            if (glowing) B.GlowSprite(x, 1.4f, z, 1.8f, 0x5fd8ff, 0.22f);
        }

        // ------------------------------------------------------------------ offices (east) + spur station

        void BuildOffices()
        {
            var o = Lab();
            o.Skip = "w";
            o.Doors = new[] { new MfDoor('e', 10, 4, 3.2f) };
            var panels = B.Room(14, 0, 34, 30, 4, o);
            if (panels.Count > 9) AddFlicker(panels[9]);
            B.GlassWall(14, 12.5f, 22, 12.5f, 2.8f);
            B.GlassWall(26, 12.5f, 34, 12.5f, 2.8f);
            B.GlassWall(14, 7.5f, 34, 7.5f, 2.8f);
            float[] dx = { 17, 22, 27, 31, 17, 22, 27, 31 };
            float[] dz = { 17, 17, 17, 17, 23, 23, 23, 23 };
            var dark = EnvMaterials.Get("glass_dark");
            for (var i = 0; i < dx.Length; i++)
            {
                var desk = B.Prop("Terminal_Desk", dx[i], 0, dz[i], 0);
                // Prototype: random screen on/off; here a fixed pattern with a dark overlay on the monitor's screen rect.
                if (i % 3 == 1) MfKit.LocalQuad(desk.transform, new Vector3(-0.1f, 1.15f, -0.044f), 0.6f, 0.36f, dark);
                if (i != 5) B.Prop("Office_Chair", dx[i] + (i % 2 == 0 ? 0.15f : -0.2f), 0, dz[i] + 0.75f, Mathf.PI + (i % 3 - 1) * 0.35f);
            }
            B.Prop("Office_Chair", 22.6f, 0.3f, 24.9f, 1.1f, 1, rotZ: 1.5f, collide: false); // knocked over
            B.Prop("Crate_Stack", 31, 0, 3, 0.4f);
            B.Prop("Shelving_Unit", 33.67f, 0, 27.5f, -Mathf.PI / 2);
            B.Prop("Debris_Pile_C", 19.2f, 0, 27.6f, 2.2f);
            B.PointLight(24, 3.6f, 20, 0xe8f2ff, 60, 16, 1.6f);
        }

        void BuildSpurStation()
        {
            var o = new MfRoomOptions { Floor = "concrete", Wall = "concrete_dark", Ceiling = "concrete_dark", Panels = null, Trim = null, Skip = "e", Doors = new[] { new MfDoor('w', 10, 4, 3.2f) } };
            B.Room(34, 0, 48, 20, 5, o);
            B.Box(50, 2, 10, 4, 6, 22, "concrete_dark");
            // Track set into the floor (rails proud by 17 cm) and the metro car on it; prototype car collider (down to the floor).
            foreach (var z in new[] { 4f, 12f, 20f }) B.Prop("Metro_Track_8m", 46, 0.17f, z, 0, 1, collide: false);
            B.Prop("TrainCar_Metro_Lit", 46, 0.17f, 11.88f, Mathf.PI / 2 + Mathf.PI / 2, 1, collide: false);
            B.SolidBox(46, 1.7f, 12.2f, 16, 3.4f, 3, rotY: Mathf.PI / 2);
            B.Box(41.8f, 0.02f, 10, 0.3f, 0.04f, 20, "metal_yellow", collide: false, shadow: false);
            Sign(34.3f, 3.4f, 10, 4, 0.7f, Mathf.PI / 2, "SPUR STATION", 0x7fe0ff, 0x08141a, 1.0f);
            B.PointLight(40, 4, 10, 0xffc890, 60, 16, 1.6f);
            foreach (var z in new[] { 4f, 10f, 16f })
            {
                B.Prop("Metro_LampTube", 40, 5, z, Mathf.PI / 2, 1, collide: false);
                B.GlowSprite(40, 4.5f, z, 1.2f, 0xffd2a0, 0.3f);
            }
            B.Prop("Bench_Metal", 35.6f, 0, 15.5f, Mathf.PI / 2);
            B.Prop("Crate_Cargo_Yellow", 35.2f, 0, 1.3f, 0.15f);
            B.Prop("TrafficCone", 42.6f, 0, 2.2f, 0.5f);
        }

        // ------------------------------------------------------------------ north row

        void BuildNorthRow()
        {
            var o = Lab();
            o.Skip = "s";
            o.Doors = new[] { new MfDoor('w', -10, 2.4f, 3), new MfDoor('e', -10, 2.6f, 3) };
            var panels = B.Room(-14, -20, 14, 0, 4.5f, o);
            if (panels.Count > 6) AddFlicker(panels[6]);
            Sign(0, 3.6f, -19.75f, 6, 0.8f, 0, "DIRECTOR · DR. I. MAREN", 0x9fd8ee, 0x0b1218, 1.0f);
            B.Prop("Bench_Street", -8, 0, -19.4f, 0);
            B.Prop("Planter_DeadTree", 11.2f, 0, -17.3f, 1.2f);
            // The hidden office door is a wall panel that Echo Sight reveals: its own mesh + collider, removed on reveal.
            if (!Revealed(HiddenDoorId))
            {
                hiddenWall = new GameObject("HiddenDoorPanel") { layer = CombatLayers.World };
                hiddenWall.transform.SetParent(transform, false);
                var hk = new LevelKit(hiddenWall.transform);
                hk.Box(-14.2f, 1.5f, -10, 0.42f, 3, 2.4f, "panel_lab");
                hk.Finish();
            }

            // Maren's lab
            o = Lab();
            o.Skip = "ws";
            B.Room(14, -20, 34, 0, 4.5f, o);
            LabBench(20, -14, 0, 11);
            LabBench(27, -14, 0, 12);
            Pod(30, -5, true);
            B.Prop("Terminal_Kiosk", 24, 0, -18.2f, 0);
            B.Box(24, 2.4f, -19.75f, 6, 2.2f, 0.06f, "screen", collide: false);
            B.Box(24, 2.4f, -19.8f, 6.24f, 2.44f, 0.04f, "metal_dark", collide: false);
            B.PointLight(24, 3.8f, -10, 0xd8ecff, 60, 16, 1.6f);
            B.Prop("Terminal_Desk", 17.5f, 0, -3.2f, Mathf.PI);
            B.Prop("Office_Chair", 17.4f, 0, -4.0f, 0.2f);
            B.Prop("Server_Rack_Dark", 33.4f, 0, -9.5f, -Mathf.PI / 2);
            B.Prop("Server_Rack_Dark", 33.4f, 0, -10.5f, -Mathf.PI / 2);

            // Hidden office
            o = new MfRoomOptions { Floor = "wood", Wall = "plaster", Ceiling = "plaster", Panels = null, Trim = "metal_dark", Skip = "e" };
            B.Room(-30, -20, -14, 0, 4, o);
            B.Box(-26, 0.75f, -17, 3, 0.08f, 1.4f, "wood");
            B.Box(-26, 0.37f, -17, 2.8f, 0.74f, 0.2f, "wood");
            B.Box(-27.2f, 0.355f, -17, 0.55f, 0.71f, 1.25f, "wood", collide: false);
            B.Box(-24.8f, 0.355f, -17, 0.55f, 0.71f, 1.25f, "wood", collide: false);
            B.Prop("Terminal_Kiosk", -26, 0, -18.6f, 0);
            B.Prop("Shelving_Unit", -29.67f, 0, -11, Mathf.PI / 2);
            B.Prop("Shelving_Unit", -29.67f, 0, -9, Mathf.PI / 2);
            B.Prop("Crate_Small", -17.2f, 0, -18.9f, 0.4f);
            B.PointLight(-22, 3.2f, -10, 0xffd6a0, 90, 14, 1.6f);
            B.Prop("Lab_CeilingLight_Warm", -22, 4.0f, -10, 0, 1, collide: false);

            // Lift room: grating floor over a dark service void (prototype: solid 'grate' slab — same collider).
            o = new MfRoomOptions { NoFloor = true, Wall = "metal_dark", Ceiling = "metal_dark", Panels = null, Trim = "metal_yellow", Skip = "s" };
            B.Room(-44, -20, -30, 0, 6, o);
            B.SolidBox(-37, -0.25f, -10, 14, 0.5f, 20);
            B.Box(-37, -0.03f, -10, 14, 0.06f, 20, "grate", collide: false, shadow: false);
            B.Box(-37, -0.8f, -10, 14, 0.1f, 20, "concrete_dark", collide: false);
            B.Box(-43.98f, -0.4f, -10, 0.04f, 0.8f, 20, "concrete_dark", collide: false, shadow: false);
            B.Box(-30.02f, -0.4f, -10, 0.04f, 0.8f, 20, "concrete_dark", collide: false, shadow: false);
            B.Box(-37, -0.4f, -19.98f, 14, 0.8f, 0.04f, "concrete_dark", collide: false, shadow: false);
            B.Box(-37, -0.4f, -0.02f, 14, 0.8f, 0.04f, "concrete_dark", collide: false, shadow: false);
            B.Cyl(-41.5f, -0.45f, -10, 0.12f, 0.12f, 20, "metal_rusted", 10, collide: false, rotX: Mathf.PI / 2);
            B.Cyl(-32.5f, -0.5f, -10, 0.09f, 0.09f, 20, "metal_dark", 10, collide: false, rotX: Mathf.PI / 2);
            B.Box(-37, 0.05f, -10, 6, 0.1f, 6, "metal_yellow", collide: false);
            foreach (var (x, z) in new[] { (-40f, -13f), (-34f, -13f), (-40f, -7f), (-34f, -7f) })
                B.Box(x, 3, z, 0.3f, 6, 0.3f, "metal_dark", collide: false);
            B.Box(-37, 0.11f, -10, 5.6f, 0.02f, 5.6f, "emit_amber", collide: false, shadow: false);
            B.Prop("Terminal_Kiosk", -33, 0, -4, -Mathf.PI / 2);
            Sign(-37, 4.8f, -19.75f, 5, 0.8f, 0, "FREIGHT LIFT · VAULT ACCESS", 0xffb46a, 0x1a1008, 1.2f);
            B.Prop("Junction_Box", -30.0f, 0, -14.5f, -Mathf.PI / 2);
            B.Prop("Crate_Cargo_Yellow", -42.6f, 0, -18.2f, 0.1f);
            B.Prop("Crate_Cargo", -42.4f, 0, -16.8f, -0.2f);
            B.Prop("Lab_CeilingLight_Warm", -37, 6.0f, -10, 0, 1, collide: false);
            B.PointLight(-37, 4.6f, -10, 0xffb060, 35, 12, 1.8f);
            B.GlowDecal(-37, 0.13f, -10, 7, 0xffa21f, 0.18f);
        }

        // ------------------------------------------------------------------ helpers

        void AddFlicker(GameObject panel)
        {
            if (panel != null) flickers.Add(new MfFlicker { Switch = MfSwitch.Find(panel, "emit_", null, EnvMaterials.Get("black")) });
        }

        void Sign(float x, float y, float z, float w, float h, float yaw, string text, uint fg, uint bg, float glow) =>
            B.Sign(x, y, z, w, h, yaw, new[] { text }, fg, bg, glow * 0.5f, fg);

        static bool HasItem(string id) => G.Inventory != null && G.Inventory.Has(id);

        // ================================================================== gameplay layout

        void Layout()
        {
            Spawn("start", 40, 0.05f, 10, -Mathf.PI / 2);
            Spawn("from_metro", 40, 0.05f, 10, -Mathf.PI / 2);
            Spawn("from_plaza", 0, 0.05f, 43, Mathf.PI);
            Spawn("from_vault", -37, 0.1f, -6, 0);

            Exit("x_facility_metro", "metro", "from_facility", 46.5f, 0.05f, 2.5f, 1.8f, "Back to the metro", auto: true);
            Exit("x_facility_plaza", "plaza", "from_facility", 0, 0.05f, 47.5f, 2.4f, "Exit to the Central Plaza",
                requires: new[] { "flag:facility_gate_open" }, lockedText: "The gate is sealed. The control panel by reception can open it.");
            Exit("i_freight_lift", "vault", "from_facility", -37, 0.1f, -10, 3, "Take the freight lift down to the Vault",
                requires: new[] { "item:q_vault_clearance" }, lockedText: "The lift requires Dr. Maren's vault clearance.");

            Trigger("t_fac_labs", P(-20, -1, 12), P(-12, 4, 18));
            Trigger("t_fac_atrium", P(-14, -1, 0), P(14, 8, 30));

            Encounter("e_fac_labs", "quest", new[]
            {
                Wave(E("sentinel", -36, 0.05f, 15), E("sentinel", -25, 0.05f, 22), E("drone", -30, 3.2f, 15)),
            }, P(-29, 0, 15), 24);
            Encounter("e_fac_offices", "quest", new[]
            {
                Wave(E("drone", 24, 3.0f, 20), E("drone", 20, 3.0f, 4), E("sentinel", 28, 0.05f, 10)),
            }, P(24, 0, 15), 22);
            Encounter("e_fac_warden", "quest", new[]
            {
                Wave(E("warden", 0, 0.05f, 6, 0), E("drone", -8, 6, 10), E("drone", 8, 6, 10)),
            }, P(0, 0, 15), 18);

            Collectible("c_frag_08", -17, 1.1f, 27.5f);
            Collectible("c_frag_09", 0, 1.6f, 21.5f);
            Collectible("c_rec_04", 31, 1.15f, 23);
            Collectible("c_rec_05", -42.6f, 0.8f, 1.6f);
            Collectible("c_cache_03", -15.4f, 0.6f, 1.3f);

            // Research logs: completing quest objectives and recovering lore.
            Log("i_log_echo", "lore_log_echo", P(-41, 1.3f, 27.6f), "Project Echo");
            Log("i_log_keys", "lore_log_keys", P(-24, 1.3f, 27.6f), "Resonance Keys");
            Log("i_log_cascade", "lore_log_cascade", P(-15.9f, 1.3f, 6.5f), "Cascade Projection");
            QuestPoint("i_maren_terminal", P(24, 1.3f, -17.2f), "Recover Dr. Maren's research data", new[] { "stage:m3_researcher:data" }, 2.2f);
            Interactable(HiddenDoorId, "door", P(-14.2f, 1.5f, -10), 3, "Hidden door", () => { }, () => false, hidden: true,
                onRevealAction: () => OpenHidden(true));
            Interactable("i_maren_final", "terminal", P(-26, 1.3f, -17.8f), 2, "Read Maren's final entry", () =>
            {
                Sfx("terminal");
                GiveItem("lore_log_final");
                EmitInteract("i_maren_final");
            }, () => !HasItem("lore_log_final"));
            Interactable("i_gate_control", "inspect", P(-2, 1.3f, 35.8f), 2, "Open the main gate (shortcut to the plaza)", () =>
            {
                SetFlag("facility_gate_open");
                Sfx("door");
                Hint("Main gate unlocked. The facility now connects directly to the Central Plaza.");
            }, () => !gateOpen);
            SaveTerminal("i_save_facility", P(2, 1.3f, 35.8f), 2);
        }

        void Log(string id, string item, Vector3 protoPos, string label)
        {
            var unityPos = V(protoPos);
            Interactable(id, "terminal", protoPos, 2, "Read log: " + label, () =>
            {
                Sfx("terminal", unityPos);
                GiveItem(item);
                PlayDialogue(item);
                EmitInteract(id);
            }, () => !HasItem(item));
        }

        void BuildMap()
        {
            MapBounds(-46, -22, 50, 50);
            MapShape("floor", 0, 38, 24, 16);
            MapShape("floor", 0, 15, 28, 30);
            MapShape("floor", -29, 15, 30, 30);
            MapShape("floor", 24, 15, 20, 30);
            MapShape("floor", 41, 10, 14, 20);
            MapShape("floor", 0, -10, 28, 20);
            MapShape("floor", 24, -10, 20, 20);
            MapShape("floor", -37, -10, 14, 20);
            MapShape("block", -29, 15, 30, 4);
            MapLabel("LOBBY", 0, 38);
            MapLabel("ATRIUM", 0, 15);
            MapLabel("LABS", -29, 23);
            MapLabel("OFFICES", 24, 20);
            MapLabel("MAREN", 24, -10);
            MapLabel("LIFT", -37, -10);
            MapLabel("SPUR", 41, 10);
        }

        // ================================================================== runtime

        void OpenHidden(bool sound)
        {
            if (hiddenWall == null || !hiddenWall.activeSelf) return;
            hiddenWall.SetActive(false);
            RefreshNavMesh();
            if (sound) Sfx("door", V(-14.2f, 1.5f, -10));
        }

        public override void OnLoaded()
        {
            base.OnLoaded();
            unsubFlag = Bus.On<FlagSet>(OnFlagSet);
        }

        void OnFlagSet(FlagSet e)
        {
            if (e.Flag == "facility_gate_open") gateOpen = Flag("facility_gate_open");
        }

        void OnDestroy()
        {
            unsubFlag?.Invoke();
            unsubFlag = null;
        }

        public override void OnEnter()
        {
            base.OnEnter();
            if (Revealed(HiddenDoorId)) OpenHidden(false);
            Emitter(0, 0.9f, 15, "aether", 6, 2.2f);
            Emitter(-36.5f, 2.6f, 4, "sparks", 2);
            ApplyGate();
        }

        public override void Tick(float dt)
        {
            base.Tick(dt);
            for (var i = 0; i < holo.Length; i++)
            {
                if (holo[i] == null) continue;
                holoRy[i] += dt * (0.2f + i * 0.15f);
                if (i > 0) holoRx[i] += dt * 0.1f * i;
                holo[i].localRotation = Rot(holoRx[i], holoRy[i], 0);
            }
            TickField(dt);
            // Main gate slides open once unlocked.
            var target = gateOpen ? 1f : 0f;
            if (!Mathf.Approximately(gateT, target))
            {
                gateT = Mathf.MoveTowards(gateT, target, dt * 0.45f);
                ApplyGate();
            }
            for (var i = 0; i < flickers.Count; i++) flickers[i].Tick(dt);
        }

        void TickField(float dt)
        {
            if (fieldMesh == null) return;
            // Security field in the server room pulses on and off.
            fieldT += dt;
            var cycle = fieldT % 4;
            var wasOn = fieldOn;
            fieldOn = cycle < 2.2f;
            if (fieldOn != wasOn) Sfx(fieldOn ? "enemy_telegraph" : "shield_hit", fieldPosUnity);
            FxMaterials.SetAlpha(fieldMat, fieldOn ? 0.32f + Mathf.Sin(ZoneTime * 30) * 0.06f : cycle > 3.5f ? 0.12f : 0.02f);
            if (alarm != null) alarm.intensity = (fieldOn ? 40 : 6) * alarmUnit;
            MfKit.SetSprite(alarmHalo, 0xff3a2e, fieldOn ? 0.6f : 0.1f);
            fieldHitCd -= dt;
            var player = Player;
            if (!fieldOn || fieldHitCd > 0 || player == null) return;
            // Prototype box (-28,0,5.2)-(-16,3,7.8) against the player position + 0.5 m.
            var p = PlayerProto;
            var py = p.y + 0.5f;
            if (p.x < -28 || p.x > -16 || py < 0 || py > 3 || p.z < 5.2f || p.z > 7.8f) return;
            fieldHitCd = 0.8f;
            DamagePlayer(9, "security field", V(p.x, 1, 6.5f));
            Vfx?.SparksDir(PlayerPos + Vector3.up, null, 14, Hex(0xff5a3a), 5);
        }
    }
}
