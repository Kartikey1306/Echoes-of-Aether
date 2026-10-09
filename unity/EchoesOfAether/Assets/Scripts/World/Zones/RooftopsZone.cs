using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Rooftop Sector above the Collapsed Market (port of RooftopsZone.ts). Prototype layout:
    ///  R1 entry roof x[-6,10] z[-6,10] top 14 (ladder from the market)
    ///  R2 hollow building x[14,28] z[-4,8] roof 15.5 (Anya's hidden room inside, hatch at x=20, z=6)
    ///  R3 shed roof x[-4,12] z[16,30] top 16 (stair ramp from R1)
    ///  R4 x[18,30] z[18,32] top 16 (6 m gap from R3: Phase Dash, or the beam from R2)
    ///  R5 relay roof x[30,44] z[-10,6] top 19 (ladder from R2)
    /// </summary>
    public sealed class RooftopsZone : ProceduralZone
    {
        public override string ZoneId => "rooftops";

        PzKit K;
        GameObject hatchLid;
        BoxCollider hatchCollider;
        float hatchOpen, hatchTarget;
        bool relayOn;
        Material relayMat, beaconMat;
        Color beaconColor;

        protected override async Task BuildZone()
        {
            ZoneSettings(6, false, "sidequest", "wind_roof");
            K = new PzKit(B);
            B.LightBudget = 16;
            SetAtmosphere(new AtmosphereSettings
            {
                // Rain night above the city, matched to the plaza's open district: teal haze and moonlit clouds, warm
                // sodium light pollution under the low clouds, height fog pooling in the streets below the roofs (the
                // roofs stand above its densest layer) with an amber glow toward the brightest districts.
                SkyTop = 0x04080d, SkyHorizon = 0x172429, SkyBottom = 0x07090b, Glow = 0xc06a2e, GlowStrength = 0.65f, Storm = true,
                SkyTint = 0xe2eaee, SkySaturation = 0.72f,
                FogColor = 0x182833, FogDensity = 0.0055f,
                HeightFogDensity = 0.0075f, HeightFogFalloff = 0.05f, HeightFogBase = 0f, HeightFogStart = 14f, HeightFogMax = 0.82f,
                HeightFogColor = 0x1b2e3a, HeightFogGlow = 0xd07a3a, HeightFogGlowStrength = 0.14f, HeightFogGlowDir = new Vector2(1, 0.2f), HeightFogGround = 0.42f,
                CityGlow = 0xb0602e, CityGlowStrength = 0.36f,
                HemiSky = 0x7890a0, HemiGround = 0x2a2219, HemiIntensity = 1.45f, EnvIntensity = 0.95f,
                SunPos = new Vector3(40, 50, 36), SunTarget = Vector3.zero, SunColor = 0xb8cce0, SunIntensity = 3.8f, SunShadows = true,
                Exposure = 1.42f, Contrast = 1.18f, Saturation = 1.06f, Lift = new Vector3(0.002f, 0.002f, 0.004f), Gain = new Vector3(1.03f, 1f, 0.97f), BloomThreshold = 0.9f,
                LightChroma = 0.7f,
                SplitShadows = 0x6e8189, SplitHighlights = 0x96806a, SplitBalance = -8f,
                GradeShadows = new Vector3(0.97f, 1f, 1.04f), GradeHighlights = new Vector3(1.05f, 1f, 0.93f), ShadowLift = 0.025f, Temperature = 6f,
                Vignette = 0.32f, CityPalette = true, CharacterFill = 2.2f, WetGround = 0.85f,
            });
            await Progress(0.1f, "Skyline");

            // ---------------------------------------------------------------- Buildings under the roofs
            Block(-6, -6, 10, 10, 14, "brick");
            Block(-4, 16, 12, 30, 16, "concrete");
            Block(18, 18, 30, 32, 16, "plaster");
            Block(30, -10, 44, 6, 19, "concrete_dark");
            BuildHollowBuilding();
            await Progress(0.3f, "Rooftops");

            // ---------------------------------------------------------------- Connections
            // R1 -> R2 plank ramp (14 -> 15.5); rails follow the slope, blocking walls as in the prototype.
            B.Ramp(10, 14, 2, Mathf.PI / 2, 1.6f, 4.4f, 1.5f, 0.15f, "wood");
            var railEnd = 14 + 1.5f * 4 / 4.4f;
            K.Railing(10, 1.2f, 14, 1.2f, 14, true, railEnd);
            K.Railing(10, 2.8f, 14, 2.8f, 14, true, railEnd);
            // R1 -> R3 stair ramp (14 -> 16) with handrails.
            B.Stairs(2, 14, 10, 0, 2.4f, 6, 0.333f, 1.0f, "metal_dark");
            B.Box(2, 15.9f, 15.5f, 2.4f, 0.2f, 1.2f, "grate");
            K.Railing(0.78f, 10, 0.78f, 16, 14, false, 16);
            K.Railing(3.22f, 10, 3.22f, 16, 14, false, 16);
            // R2 -> R4 balance beam (optional route) from (24, 15.5, 8) to (24, 16, 18): I-beam.
            B.Box(24, 15.65f, 13, 0.45f, 0.25f, 10.4f, "metal_yellow", rotX: -0.05f);
            B.Box(24, 15.38f, 13, 0.08f, 0.3f, 10.4f, "metal_dark", collide: false, rotX: -0.05f);
            B.Box(24, 15.22f, 13, 0.4f, 0.05f, 10.4f, "metal_dark", collide: false, shadow: false, rotX: -0.05f);
            // R2 -> R5 ladder (climb) on R5's west wall.
            K.Prop("Ladder_4m", 30, 15.5f, 0, -Mathf.PI / 2, 1, false);

            // ---------------------------------------------------------------- Rooftop dressing
            K.WaterTank(-3, 14, -3);
            K.AcUnit(6, 14, 6, 0.3f);
            K.Vent(-2, 14, 7);
            K.AcUnit(25, 15.5f, -2, 1.2f);
            K.Vent(17, 15.5f, -1);
            K.Antenna(9, 16, 28, 5);
            K.AcUnit(26, 16, 28, 0);
            K.Vent(20, 16, 22);
            K.CrateStack(28, 16, 30, 0.6f, 1202);
            K.Terminal(6, 14, 1.6f, 0);
            K.Prop("Roof_TurbineVent", 7.5f, 14, -3.5f);
            K.Prop("Roof_TurbineVent", 41.5f, 19, 4.2f);
            K.Prop("Roof_TurbineVent", -1.5f, 16, 19.5f);
            K.Prop("Scrap_Metal", 3.5f, 14, -4.2f, 0.6f, 1, false);
            K.Prop("Debris_Pile_C", 19.3f, 16, 19.3f, 1.3f, 1, false);
            K.Prop("Slab_Broken_Flat", 9.2f, 16, 18.4f, 0.4f, 0.6f, false);
            K.Prop("Crate_Small", 0.2f, 16, 26.6f, 0.4f);
            // Roof hatch the market ladder comes up through (exit x_roof_market).
            K.Prop("Roof_Hatch_Frame", -1.2f, 14, -1.5f, 0, 1, false);
            B.Box(-1.2f, 14.005f, -1.5f, 1.2f, 0.01f, 1.2f, "black", collide: false, shadow: false);
            var lid = K.Prop("Roof_Hatch_Lid", -1.2f, 14.35f, -2.25f, 0, 1, false);
            lid.transform.localRotation = Quaternion.AngleAxis(-105, Vector3.right);
            K.Prop("Ladder_4m", -1.2f, 10.0f, -2.05f, 0, 1, false);
            // Drop-down shortcut to the camp: grab rails over R4's east parapet.
            K.Prop("Ladder_4m", 30, 12, 20, Mathf.PI / 2, 1, false);
            // Power lines between the roofs.
            K.Cable(9.88f, 14.95f, 9.6f, 14.12f, 16.45f, 7.6f, 0.025f, 0.35f);
            K.Cable(30.12f, 19.95f, -3.2f, 27.88f, 16.45f, -3.6f, 0.025f, 0.3f);

            // Maintenance shed on R3 (door +Z with amber light); prototype collider; electrical box the control component sits on.
            K.Prop("Roof_Shed", 3, 16, 23, 0, 1, false);
            B.SolidCollider(3, 17.4f, 23, 5, 2.8f, 4);
            B.Box(6, 16.5f, 25.6f, 1.4f, 1.0f, 0.7f, "metal_dark");
            B.PointLight(3, 18.7f, 25.5f, 0xffa21f, 14, 6, 1.6f);

            // Relay tower on R5 (leg colliders as the prototype's four posts) and its transmitter.
            K.Prop("RelayTower", 38, 19, -2, 0, 1, false);
            foreach (var (x, z) in new (float, float)[] { (36, -4), (40, -4), (36, 0), (40, 0) }) B.SolidCollider(x, 25, z, 0.25f, 12, 0.25f);
            var beacon = B.GlowSprite(38, 19 + 15.95f + 0.25f, -2, 2, 0xff3030, 1.2f);
            beaconMat = beacon != null ? beacon.GetComponent<MeshRenderer>().sharedMaterial : null;
            K.Prop("Relay_Transmitter", 38, 19, 2.2f, 0, 1, false);
            B.SolidCollider(38, 19.8f, 2.2f, 3, 1.6f, 1);
            B.SolidCollider(35.5f, 19.6f, 2.2f, 0.6f, 0.6f, 0.6f);
            relayMat = EnvMaterials.EmissiveInstance(Hex(0x101820), 0);
            relayMat.SetColor("_BaseColor", Hex(0x101820));
            var screen = B.MeshObject("RelayScreen", LevelKit.QuadMesh, relayMat, P(38, 19.8f, 2.745f), Quaternion.Euler(0, 180, 0), false, K.Dynamic);
            screen.transform.localScale = new Vector3(2.36f, 0.96f, 1);
            B.PointLight(38, 22, 3, 0x8fd8ff, 40, 14, 1.6f);
            SetRelay(false);

            // Street-level glow far below and the surrounding skyline
            B.Box(15, 0, 10, 200, 0.2f, 200, "asphalt", collide: false);
            for (var i = 0; i < 18; i++) K.StreetLamp(-40 + (i % 6) * 22, 0.1f, -40 + (i / 6) * 40, 0, true, false, 1.5f);
            var r = new PzRng(77);
            for (var i = 0; i < 22; i++)
            {
                var a = i / 22f * Mathf.PI * 2;
                var d = 70 + r.Next() * 40;
                var w = 12 + r.Next() * 10;
                var dd = 12 + r.Next() * 10;
                var h = 20 + r.Next() * 45;
                K.SkylineBlock(15 + Mathf.Cos(a) * d, 0, 10 + Mathf.Sin(a) * d, h, w > dd ? 0 : Mathf.PI / 2);
            }
            // Distant Aether core glow on the horizon
            B.GlowSprite(-60, 30, -140, 60, 0x5fd8ff, 0.6f);
            B.GlowSprite(-60, 30, -140, 25, 0xa47dff, 0.8f);
            await Progress(0.5f, "Relay tower");

            // Bounds: invisible walls around the roof cluster at parapet height
            B.Wall(2, 15, -6.3f, 16.6f, 4, 0.4f);
            B.Wall(-6.3f, 15, 2, 0.4f, 4, 16.6f);
            B.Wall(37, 20.5f, -10.3f, 14.6f, 4, 0.4f);
            B.Wall(44.3f, 20.5f, -2, 0.4f, 4, 16.6f);
            B.Wall(24, 17.5f, 32.3f, 12.6f, 4, 0.4f);
            B.Wall(30.3f, 17.5f, 25, 0.4f, 4, 14.6f);
            B.Wall(4, 17.5f, 30.3f, 16.6f, 4, 0.4f);
            B.Wall(-4.3f, 17.5f, 23, 0.4f, 4, 14.6f);

            MakeWeather(new WeatherSettings { Rain = 0, Wind = new Vector2(6, 2), Lightning = false, LightningInterval = new Vector2(8, 18), SplashHeight = 14.05f }); // no rain (user request)
            // Cyberpunk city layer around and below the rooftops.
            var center = new Vector3(B.Bounds.center.x, 0, B.Bounds.center.z);
            CyberCity.DressFacades(B, center, 160, 7101, 1.2f, 160, groundY: 0f);
            // Merge the static neon (boards, tubes) per material: one draw per colour instead of one per sign piece.
            var dress = B.FxRoot.Find("CyberDressing");
            if (dress != null) CityHarvest.Static(dress, B.FxRoot, 64f, null);
            DecalKit.ScatterGround(B.FxRoot, center, 60, 40, 7104);
            CyberCity.Skyline(B, center, 150, 380, 46, 7102);
            SkyTraffic.Create(transform, center, 30, 30, 95, 50, 170, 7103);
            Layout();
            BuildMap();
        }

        /// <summary>
        /// Building under a roof (prototype block()): mass (closed up to the roof slab), wet roof slab, parapets (no
        /// collision) with coping and corner blocks, facade modules on the z faces where the prototype had window grids.
        /// </summary>
        void Block(float x0, float z0, float x1, float z1, float top, string mat)
        {
            float cx = (x0 + x1) / 2, cz = (z0 + z1) / 2, w = x1 - x0, d = z1 - z0;
            B.Box(cx, (top - 0.3f) / 2, cz, w, top - 0.3f, d, mat);
            B.Box(cx, top - 0.15f, cz, w, 0.3f, d, "concrete_wet");
            K.Parapet(x0, z0, x1, z1, top, mat, 0.9f);
            foreach (var (px, pz) in new[] { (x0 + 0.12f, z0 + 0.12f), (x1 - 0.12f, z0 + 0.12f), (x0 + 0.12f, z1 - 0.12f), (x1 - 0.12f, z1 - 0.12f) })
                K.Prop("Roof_Parapet_Corner", px, top, pz, 0, 1, false);
            Facades(x0, z0, x1, z1, top - 0.3f, mat, new PzRng(Mathf.Round(x0 * 7 + z0 * 13)));
        }

        void Facades(float x0, float z0, float x1, float z1, float height, string mat, PzRng r)
        {
            var module = mat == "brick" ? "Facade_Brick_Window" : mat == "plaster" ? "Facade_Plaster_Window" : "Facade_Concrete_Window";
            var w = x1 - x0;
            var n = Mathf.FloorToInt(w / 4);
            var floors = Mathf.FloorToInt(height / 3.4f);
            var start = (x0 + x1) / 2 - n * 2 + 2;
            for (var f = 0; f < floors; f++)
                for (var c = 0; c < n; c++)
                    foreach (var (z, yaw) in new[] { (z0 - 0.16f, Mathf.PI), (z1 + 0.16f, 0f) })
                    {
                        var x = start + c * 4;
                        var lit = r.Next() < 0.08f;
                        var name = f == 0 ? "Facade_Shop_Broken" : lit && mat == "plaster" ? "Facade_Plaster_Window_Lit" : module;
                        K.Prop(name, x, f * 3.4f, z, yaw, 1, false);
                        if (lit && f > 0 && mat != "plaster")
                        {
                            var o = PzKit.Rot(x, z, yaw, 0, -0.026f);
                            K.Panel(o.x, f * 3.4f + 1.7f, o.y, 1.56f, 1.56f, yaw, "win_warm");
                        }
                    }
        }

        /// <summary>R2: hollow building with Anya's hidden room (floor 11.65, roof 15.5 with a 1.2 m hatch at x[19.4,20.6] z[5.4,6.6]).</summary>
        void BuildHollowBuilding()
        {
            // (base closed up to the room floor: the prototype left a 10 cm slit under it)
            B.Box(21, 5.55f, 2, 14, 11.6f, 12, "concrete");
            B.Box(21, 11.5f, 2, 14, 0.3f, 12, "wood");
            foreach (var (x, z, w, d) in new (float, float, float, float)[] { (21, -3.85f, 14, 0.3f), (21, 7.85f, 14, 0.3f), (14.15f, 2, 0.3f, 12), (27.85f, 2, 0.3f, 12) })
                B.Box(x, 13.5f, z, w, 4, d, "concrete");
            // Roof slabs leaving the hatch opening
            B.Box(16.7f, 15.35f, 2, 5.4f, 0.3f, 12, "concrete_wet");
            B.Box(24.3f, 15.35f, 2, 7.4f, 0.3f, 12, "concrete_wet");
            B.Box(20, 15.35f, -0.7f, 1.2f, 0.3f, 6.6f, "concrete_wet");
            B.Box(20, 15.35f, 7.3f, 1.2f, 0.3f, 1.4f, "concrete_wet");
            // Hatch: hinged lid (opens instead of vanishing) + the prototype's blocking collider while closed.
            hatchLid = K.DynamicProp("Roof_Hatch_Lid", 20, 15.5f, 5.25f, 0);
            if (!Flag("anya_hatch_open")) hatchCollider = B.AddBoxCollider(V(20, 15.4f, 6), new Vector3(1.2f, 0.2f, 1.2f), Quaternion.identity, CombatLayers.World);
            else hatchOpen = hatchTarget = 1;
            ApplyHatch();
            K.Parapet(14, -4, 28, 8, 15.5f, "concrete", 0.9f);
            Facades(14, -4, 28, 8, 11.25f, "concrete", new PzRng(1207));
            // Anya's room: desk with her console (the recording lies on it), chair, shelves, crates, ladder to the hatch.
            K.Prop("Terminal_Desk", 24, 11.65f, 5.6f, Mathf.PI);
            K.Prop("Office_Chair", 24.2f, 11.65f, 4.6f, 0.25f);
            K.Prop("Shelving_Unit", 14.65f, 11.65f, 1.5f, Mathf.PI / 2);
            K.CrateStack(16.5f, 11.65f, -1.5f, 0.2f, 1201);
            B.Box(20, 11.66f, 6, 1, 0.02f, 1, "tarp_blue", collide: false, shadow: false);
            K.Prop("Ladder_4m", 20.8f, 11.65f, 6, -Mathf.PI / 2, 1, false);
            K.Prop("Lab_CeilingLight_Warm", 22, 15.2f, 2, 0, 1, false);
            B.PointLight(22, 14, 2, 0xffc890, 30, 9, 1.6f);
        }

        // ------------------------------------------------------------------ gameplay layout

        void Layout()
        {
            Spawn("start", 0, 14.05f, 1, Mathf.PI * 0.5f);
            Spawn("from_market", 0, 14.05f, 1, Mathf.PI * 0.5f);
            Exit("x_roof_market", "plaza", "from_rooftops", -1.2f, 14.05f, -1.5f, 1.4f, "Climb down to the market");
            Exit("i_drop_plaza", "plaza", "camp", 29, 16.05f, 20, 1.6f, "Drop down to the survivors' camp (shortcut)");
            Trigger("t_roof_r2", P(14, 15, -4), P(28, 19, 8));
            Trigger("t_roof_r4", P(18, 15.5f, 18), P(30, 19, 32));
            Encounter("e_roof_drones", "trigger:t_roof_r2", new[] { Wave(E("drone", 18, 20, -2), E("drone", 26, 20.5f, 5), E("drone", 12, 19.5f, 10)) }, P(18, 15, 8), 26);
            Encounter("e_roof_stalkers", "trigger:t_roof_r4", new[] { Wave(E("stalker", 26, 16.05f, 28), E("stalker", 21, 16.05f, 30)) }, P(24, 16, 25), 12);
            Collectible("c_frag_10", 28.5f, 17.0f, 31);
            Collectible("c_frag_11", 42.5f, 20.0f, -9);
            Collectible("c_cache_04", -2.5f, 16.6f, 28.5f);
            ItemPickup("i_control_component", "q_control_component", 6, 17.15f, 25.6f, new[] { "quest:sq_broken_guardian:active" });
            ItemPickup("i_relay_cell", "q_relay_cell", 1.2f, 16.6f, 25.6f, new[] { "quest:sq_last_signal:active" });
            ItemPickup("i_anya_recording", "q_anya_recording", 24, 12.4f, 5.3f, new[] { "quest:sq_last_signal:active" });
            QuestPoint("i_relay_tower", P(38, 20.4f, 3.4f), "Inspect the relay transmitter", new[] { "stage:sq_last_signal:locate" }, 2.4f);
            Interactable("i_relay_socket", "inspect", P(35.5f, 20.2f, 3.2f), 2.2f, "Insert the relay power cell", () =>
            {
                SetRelay(true);
                SetFlag("relay_active");
                Sfx("door", V(38, 20, 2));
                EmitInteract("i_relay_socket");
            }, available: () => Check("stage:sq_last_signal:activate"));
            Interactable("i_hidden_hatch", "door", P(20, 15.6f, 6), 2.4f, "Open the hidden hatch", () =>
            {
                OpenHatch(true);
                SetFlag("anya_hatch_open");
                EmitInteract("i_hidden_hatch");
                _ = Traverse(new[] { P(20, 15.5f, 6), P(20, 11.7f, 6), P(20.6f, 11.7f, 5) }, "climb", 1.6f);
            }, available: () => hatchCollider != null, hidden: true);
            Interactable("i_hatch_ladder", "ladder", P(20.4f, 12.6f, 6), 1.6f, "Climb back up",
                () => _ = Traverse(new[] { P(20.3f, 11.7f, 6), P(20.3f, 15.6f, 6), P(20, 15.65f, 4.6f) }, "climb", 2.2f),
                available: () => hatchCollider == null);
            Interactable("i_ladder_r5", "ladder", P(28.9f, 16.4f, 0), 1.6f, "Climb to the relay roof",
                () => _ = Traverse(new[] { P(29.1f, 15.55f, 0), P(29.1f, 19.1f, 0), P(31, 19.05f, 0) }, "climb", 2.4f, Mathf.PI / 2));
            Interactable("i_ladder_r5_down", "ladder", P(30.6f, 19.8f, 0), 1.4f, "Climb down",
                () => _ = Traverse(new[] { P(30.6f, 19.05f, 0), P(29.1f, 19.05f, 0), P(29.1f, 15.55f, 0), P(27.5f, 15.55f, 0) }, "climb", 2.4f, -Mathf.PI / 2));
            SaveTerminal("i_save_roof", P(6, 15.3f, 2), 2);
        }

        void BuildMap()
        {
            MapBounds(-10, -14, 48, 36);
            MapShape("floor", 2, 2, 16, 16);
            MapShape("floor", 21, 2, 14, 12);
            MapShape("floor", 4, 23, 16, 14);
            MapShape("floor", 24, 25, 12, 14);
            MapShape("floor", 37, -2, 14, 16);
            MapShape("road", 12, 2, 4, 1.6f);
            MapShape("road", 24, 13, 0.6f, 10);
            MapShape("block", 3, 23, 5, 4);
            MapLabel("LADDER", 0, 0);
            MapLabel("SHED", 3, 23);
            MapLabel("RELAY", 38, -2);
            MapLabel("BEAM", 24, 13);
        }

        // ------------------------------------------------------------------ behaviour

        void SetRelay(bool on)
        {
            relayOn = on;
            if (relayMat != null)
            {
                relayMat.SetColor("_BaseColor", on ? Hex(0x5fd8ff) * 0.25f : Hex(0x101820));
                EnvMaterials.SetEmission(relayMat, Hex(0x5fd8ff), on ? 1.6f : 0);
            }
            beaconColor = FxMaterials.Hdr(Hex(on ? 0x5fd8ffu : 0xff3030u), 1.2f);
        }

        void OpenHatch(bool sound)
        {
            if (hatchCollider != null)
            {
                hatchCollider.gameObject.SetActive(false);
                Destroy(hatchCollider.gameObject);
                hatchCollider = null;
                RefreshNavMesh();
            }
            hatchTarget = 1;
            if (sound) Sfx("door", V(20, 15.45f, 6));
        }

        void ApplyHatch()
        {
            if (hatchLid == null) return;
            var k = Mathf.SmoothStep(0, 1, hatchOpen);
            hatchLid.transform.localRotation = Quaternion.AngleAxis(-110 * k, Vector3.right);
        }

        public override void OnEnter()
        {
            base.OnEnter();
            if (Flag("relay_active")) SetRelay(true);
            // The prototype replayed the door sound here; restoring the open hatch is silent.
            if (Flag("anya_hatch_open")) OpenHatch(false);
            Emitter(-2, 15.4f, 7, "steam", 2);
            Emitter(17, 16.9f, -1, "steam", 2);
        }

        public override void Tick(float dt)
        {
            base.Tick(dt);
            if (beaconMat != null)
            {
                var a = 0.5f + 0.5f * Mathf.Max(0, Mathf.Sin(ZoneTime * (relayOn ? 4 : 1.5f)));
                var c = beaconColor * a;
                c.a = a;
                beaconMat.SetColor("_BaseColor", c);
            }
            if (!Mathf.Approximately(hatchOpen, hatchTarget))
            {
                hatchOpen = Mathf.MoveTowards(hatchOpen, hatchTarget, dt / 0.6f);
                ApplyHatch();
            }
        }
    }
}
