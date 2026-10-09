using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Underground Aether Vault (port of VaultZone.ts; z increases deeper).
    /// Lift landing z[-4,4] → great hall x[-10,10] z[4,40] (vents at z=16, z=28; hidden wall west at z=24)
    /// → lock chamber x[-14,14] z[40,60] (three resonators, glyphs) → attunement z[60,74]
    /// → Guardian gallery x[-8,8] z[74,104] → blast door z=104 → core lift z[104,118]. Secret room x[-22,-10] z[18,30].
    /// Layout numbers, collision and every gameplay id match the prototype; the look uses the Blender vault kit
    /// (wall panels, resonator pillars, lock door leaves, blast door + frame + countdown lights, pods, pedestals).
    /// </summary>
    public sealed class VaultZone : ProceduralZone
    {
        public override string ZoneId => "vault";

        static readonly int[] GlyphTarget = { 3, 1, 4 };
        const float DoorTime = 38;

        sealed class Resonator
        {
            public Vector3 Pos;          // prototype space
            public int Value = 1;
            public readonly Material[] Segments = new Material[4];
            public string[] Prompts;     // cached "Tune resonator i (now v)" strings, index = value
        }

        sealed class Vent
        {
            public float Z, Offset, HitCd;
            public Renderer Renderer;
            public Material Mat;
        }

        readonly Resonator[] resonators = new Resonator[3];
        readonly Vent[] vents = new Vent[2];
        Transform dyn;

        // Resonance lock door (two leaves sliding apart along prototype x).
        readonly Transform[] lockLeaves = new Transform[2];
        readonly float[] leafX = { 1.5f, -1.5f };
        GameObject lockBlocker;
        bool lockOpen;

        // Blast door (lifts 9.5 m) with eight countdown lights.
        Transform blastDoor;
        float blastY, blastT;
        bool blastOpen;
        /// <summary>True once the blast door has opened (automation / cinematics).</summary>
        public bool BlastOpen => blastOpen;
        GameObject blastBlocker;
        Renderer[][] blastLightRenderers = new Renderer[8][];
        Material[][][][] blastLightSets = new Material[8][][][];
        readonly int[] blastLightState = { -1, -1, -1, -1, -1, -1, -1, -1 };

        // Hidden wall into Maren's secret room.
        GameObject hiddenWall, hiddenBlocker;
        bool hiddenOpen, hiddenGlowing;

        Transform attuneCore, relic;
        Color ventColor;
        Light[] glowLights;
        float[] glowBase;

        protected override async Task BuildZone()
        {
            ZoneSettings(-14, true, "tension", "vault_hum");
            SetAtmosphere(new AtmosphereSettings
            {
                // Ancient aether vault: neutral stone-grey ambient with a teal sky term and warm (gold) bounce from below;
                // the aether teal and the old gold lamps are the accents.
                SkyTop = 0x0a1014, SkyHorizon = 0x141c1e, SkyBottom = 0x070605, Glow = 0x5fd0c0, GlowStrength = 0.35f,
                FogColor = 0x080b0c, FogDensity = 0.02f,
                HemiSky = 0x7a8a8c, HemiGround = 0x221c14, HemiIntensity = 1.35f, EnvIntensity = 0.7f,
                SunPos = new Vector3(-10, 40, 30), SunTarget = Vector3.zero, SunColor = 0xb8c4c0, SunIntensity = 0.6f, SunShadows = true,
                Exposure = 1.24f, Contrast = 1.14f, Saturation = 1.07f, Lift = new Vector3(0.002f, 0.002f, 0.001f), Gain = new Vector3(1.01f, 1.0f, 0.985f),
                BloomThreshold = 0.82f,
                // cinematic grade: aether-teal shadows, old-gold highlights
                LightChroma = 0.68f, SplitShadows = 0x5a8a84, SplitHighlights = 0xa48a5a,
                GradeShadows = new Vector3(0.94f, 1.02f, 1.03f), GradeHighlights = new Vector3(1.06f, 1.01f, 0.9f), ShadowLift = 0.015f,
                Temperature = 4f, Vignette = 0.38f, LensStreaks = 0.5f,
            });
            B.LightBudget = 14;
            dyn = new GameObject("Dynamic").transform;
            dyn.SetParent(transform, false);
            var lights = new System.Collections.Generic.List<Light>();
            await Progress(0.1f, "Vault shell");

            // ---------------------------------------------------------------- Lift landing
            VaultKit.Room(B, -5, -4, 5, 4, 6, "grate", "metal_dark", "metal_dark", "emit_violet", "s");
            B.Box(0, 0.05f, -1, 5, 0.1f, 5, "metal_yellow", collide: false);
            B.Prop("Terminal_Kiosk", 3.8f, 0, 2.5f, -Mathf.PI / 2);
            B.Sign(0, 4.5f, -3.75f, 5, 0.8f, 0, new[] { "LEVEL V-3 · CONTAINMENT" }, fg: 0xc8a8ff, bg: 0x100a1a, glow: 1.2f, border: 0x6a4aa8);
            lights.Add(B.PointLight(0, 4.5f, 0, 0xa47dff, 50, 12, 1.6f));
            Panels("Vault_Wall_Panel_4m", 'n', -4, -2, 2);
            Panels("Vault_Wall_Panel_4m", 'e', 5, -2, 2);
            Panels("Vault_Wall_Panel_4m", 'w', -5, -2, 2);

            // ---------------------------------------------------------------- Great hall
            VaultKit.Room(B, -10, 4, 10, 40, 9, "grate", "metal_dark", "metal_dark", "emit_violet", "ns", new[] { new VaultKit.Door('w', 24, 2.6f, 3.2f) });
            // Back-fill the north wall around the landing opening and the south wall around the lock chamber opening.
            B.Box(-7.7f, 4.5f, 3.8f, 4.6f, 9, 0.4f, "metal_dark");
            B.Box(7.7f, 4.5f, 3.8f, 4.6f, 9, 0.4f, "metal_dark");
            B.Box(0, 7.5f, 3.8f, 10, 3, 0.4f, "metal_dark");
            Panels("Vault_Wall_Panel_4m", 'n', 4, -7.7f, 7.7f);
            // Conduit panels line both walls (their pipes replace the prototype's 1.2 m / 2.8 m runs); the 4.4 m run stays.
            Panels("Vault_Wall_Panel_4m", 'w', -10, 8.7f, 12.7f, 16.7f, 20.7f, 27.3f, 31.3f, 35.3f);
            Panels("Vault_Wall_Panel_4m_Cyan", 'e', 10, 8.7f, 12.7f, 16.7f, 20.7f, 27.3f, 31.3f, 35.3f);
            // East twin of the hidden wall so the singing wall does not stand out until Echo Sight finds it.
            var twin = B.Prop("Vault_Wall_Panel_4m_Cyan", 9.99f, 0, 24, -Mathf.PI / 2, collide: false);
            twin.transform.localScale = new Vector3(0.65f, 0.8f, 1);
            foreach (var x in new[] { -9.4f, 9.4f })
            {
                B.Cyl(x, 4.4f, 22, 0.18f, 0.18f, 36, "metal", 10, open: true, collide: false, rotX: Mathf.PI / 2);
                for (var z = 6f; z < 40; z += 8) B.Prop("Pipe_Flange", x, 4.4f, z, Mathf.PI / 2, collide: false);
                B.Box(x * 0.98f, 6.4f, 22, 0.08f, 0.12f, 36, x < 0 ? "emit_violet" : "emit_cyan", collide: false, shadow: false);
            }
            // Service pipes under the grating.
            foreach (var x in new[] { -6f, -2.5f, 5f }) B.Cyl(x, -0.28f, 22, 0.12f, 0.12f, 36, "metal", 8, open: true, collide: false, shadow: false, rotX: Mathf.PI / 2);
            // Containment alcoves with sealed chambers.
            foreach (var z in new[] { 10f, 20f, 34f })
            {
                B.Prop("CryoPod", -7.5f, 0, z, Mathf.PI / 2);
                B.Prop(z != 20 ? "CryoPod" : "CryoPod_Empty", 7.5f, 0, z, -Mathf.PI / 2);
            }
            // Hazard vents: grating strip over a violet slot, energy curtain animated in Tick.
            var ventMesh = VaultKit.GlowBox(19.6f, 2.4f, 1.4f);
            ventColor = FxMaterials.Hdr(Hex(0xa47dff), 1.6f);
            var vz = new[] { 16f, 28f };
            var voff = new[] { 0f, 1.6f };
            for (var i = 0; i < 2; i++)
            {
                B.Box(0, 0.02f, vz[i], 20, 0.04f, 1.6f, "grate", collide: false, shadow: false);
                B.Box(0, -0.38f, vz[i], 19.6f, 0.02f, 1.4f, "emit_violet", collide: false, shadow: false);
                var mat = VaultKit.Additive(0xa47dff, 1.6f);
                var go = VaultKit.MeshGo("Vent" + i, ventMesh, mat, dyn, V(0, 1.2f, vz[i]), Quaternion.identity);
                vents[i] = new Vent { Z = vz[i], Offset = voff[i], Renderer = go.GetComponent<Renderer>(), Mat = mat };
                vents[i].Renderer.enabled = false;
            }
            lights.Add(B.PointLight(0, 7, 12, 0x5fe0d0, 90, 22, 1.5f));
            lights.Add(B.PointLight(0, 7, 30, 0xffc27a, 90, 22, 1.5f)); // old gold lamp (teal / gold vault palette)
            // The hidden wall (west, z=24): a panel sized to the 2.6 x 3.2 opening, glowing violet once revealed.
            hiddenWall = VaultKit.PropUnder(B, dyn, "Vault_Wall_Panel_4m", -9.99f, 0, 24, Mathf.PI / 2);
            hiddenWall.transform.localScale = new Vector3(0.65f, 0.8f, 1);
            hiddenBlocker = VaultKit.DoorBlocker(B, -10.2f, 1.6f, 24, 0.42f, 3.2f, 2.6f);
            await Progress(0.3f, "Containment hall");

            // ---------------------------------------------------------------- Secret room (Hidden Vault)
            VaultKit.Room(B, -22, 18, -10, 30, 4.5f, "wood", "plaster", "plaster", "emit_violet", "e");
            B.Prop("Vault_Pedestal_Relic", -16, 0, 24, 0, collide: false);
            VaultKit.CylCollider(B, -16, 0.5f, 24, 1.0f, 1.0f, 16);
            B.Cyl(-16, 1.02f, 24, 0.7f, 0.7f, 0.04f, "emit_violet", 24, collide: false);
            var relicMat = EnvMaterials.Aether(Hex(0x5fd8ff), 1.2f, Hex(0xa47dff));
            relic = VaultKit.PropUnder(B, dyn, "Vault_Crystal", -16, 1.7f, 24).transform;
            VaultKit.SwapMaterial(relic.gameObject, "aether", relicMat, true);
            VaultKit.SetShadows(relic.gameObject, false);
            B.GlowSprite(-16, 1.7f, 24, 1.4f, 0xc8a8ff, 0.8f);
            for (var i = 0; i < 4; i++) B.Box(-21.6f, 0.6f + i * 0.5f, 24, 0.3f, 0.05f, 4, "wood", collide: false);
            lights.Add(B.PointLight(-16, 3.6f, 24, 0xc8a8ff, 60, 12, 1.6f));

            // ---------------------------------------------------------------- Lock chamber
            VaultKit.Room(B, -14, 40, 14, 60, 10, "grate", "metal_dark", "metal_dark", "emit_violet", "n", new[] { new VaultKit.Door('s', 0, 6, 5) });
            B.Box(-12, 5, 39.8f, 4, 10, 0.4f, "metal_dark");
            B.Box(12, 5, 39.8f, 4, 10, 0.4f, "metal_dark");
            B.Box(0, 9.5f, 39.8f, 20, 1, 0.4f, "metal_dark");
            Panels("Vault_Wall_Panel_4m", 'n', 40, -12, 12);
            Panels("Vault_Wall_Panel_4m", 'w', -14, 42, 50, 54, 58);   // z=46 left bare for the glyph plate
            Panels("Vault_Wall_Panel_4m", 'e', 14, 42, 50, 54, 58);
            Panels("Vault_Wall_Panel_4m", 's', 60, -9, -5, 5, 9);
            var rp = new[] { new Vector3(-8, 0, 50), new Vector3(0, 0, 54), new Vector3(8, 0, 50) };
            for (var i = 0; i < 3; i++) resonators[i] = MakeResonator(rp[i], i);
            // Glyph plates on the walls (hidden, revealed by Echo Sight).
            var glyphPos = new[] { new Vector3(-13.75f, 4, 46), new Vector3(0, 6, 59.75f), new Vector3(13.75f, 4, 46) };
            for (var i = 0; i < 3; i++) MakeGlyph(glyphPos[i], i);
            // The resonance lock door: two Blender leaves (violet seam toward the centre).
            lockLeaves[0] = VaultKit.PropUnder(B, dyn, "Vault_LockDoor_Half", leafX[0], 0, 60.2f, 0).transform;
            lockLeaves[1] = VaultKit.PropUnder(B, dyn, "Vault_LockDoor_Half", leafX[1], 0, 60.2f, Mathf.PI).transform;
            lockBlocker = VaultKit.DoorBlocker(B, 0, 2.5f, 60.2f, 6, 5, 0.5f);
            // High ledge with a fragment; wide steel stairs (Blender) with their ramp collider.
            // Grated catwalk: grating deck in a steel rim on two legs; collider = the prototype's 3 x 0.4 x 7 slab.
            B.SolidCollider(12, 3, 56, 3, 0.4f, 7);
            B.Box(12, 3.19f, 56, 2.8f, 0.02f, 6.8f, "grate", collide: false, shadow: false);
            B.Box(10.55f, 3.05f, 56, 0.1f, 0.3f, 7, "metal_dark", collide: false);
            B.Box(13.45f, 3.05f, 56, 0.1f, 0.3f, 7, "metal_dark", collide: false);
            B.Box(12, 3.05f, 52.55f, 3, 0.3f, 0.1f, "metal_dark", collide: false);
            B.Box(12, 3.05f, 59.45f, 3, 0.3f, 0.1f, "metal_dark", collide: false);
            foreach (var lx in new[] { 10.7f, 13.3f }) B.Box(lx, 1.45f, 59.3f, 0.2f, 2.9f, 0.2f, "metal_dark", collide: false);
            B.Prop("Stairs_Metal_3m", 12.2f, 0, 48.1f, 0, collide: false);
            B.AddBoxCollider(V(12.2f, 1.4f, 50.26f), new Vector3(2.6f, 0.2f, 5.26f), Quaternion.Euler(-34.78f, 0, 0), CombatLayers.World);
            for (var i = 0; i < 3; i++) B.Prop("Railing_2m", 10.6f, 3.2f, 54 + i * 2, Mathf.PI / 2, collide: false);
            B.Prop("Railing_Post", 10.6f, 3.2f, 53, 0, collide: false);
            lights.Add(B.PointLight(0, 8, 50, 0x7fe6d6, 110, 24, 1.5f));
            await Progress(0.45f, "Resonance lock");

            // ---------------------------------------------------------------- Attunement chamber
            VaultKit.Room(B, -8, 60, 8, 74, 8, "grate", "metal_dark", "metal_dark", "emit_violet", "ns");
            Panels("Vault_Wall_Panel_4m_Cyan", 'w', -8, 63, 67, 71);
            Panels("Vault_Wall_Panel_4m_Cyan", 'e', 8, 63, 67, 71);
            B.Prop("Vault_Pedestal_Attunement", 0, 0, 67, 0, collide: false);
            VaultKit.CylCollider(B, 0, 0.6f, 67, 2, 1.2f, 24);
            attuneCore = VaultKit.MeshGo("AttuneCore", FxMesh.Sphere(0.9f, 28, 18), EnvMaterials.Aether(Hex(0x5fd8ff), 1.1f), dyn, V(0, 2.6f, 67), Quaternion.identity).transform;
            B.GlowSprite(0, 2.6f, 67, 4.5f, 0x5fd8ff, 0.7f);
            foreach (var x in new[] { -6f, 6f }) B.Cyl(x, 4, 67, 0.4f, 0.5f, 8, "metal", 10);
            lights.Add(B.PointLight(0, 3, 67, 0x5fd8ff, 100, 16, 1.6f));

            // ---------------------------------------------------------------- Guardian gallery
            VaultKit.Room(B, -8, 74, 8, 104, 11, "grate", "metal_dark", "metal_dark", "emit_violet", "ns");
            Panels("Vault_Wall_Panel_4m", 'w', -8, 76, 80, 84, 88, 92, 96, 100);
            Panels("Vault_Wall_Panel_4m", 'e', 8, 76, 80, 84, 88, 92, 96, 100);
            foreach (var x in new[] { -3f, 3f }) B.Cyl(x, -0.28f, 89, 0.12f, 0.12f, 58, "metal", 8, open: true, collide: false, shadow: false, rotX: Mathf.PI / 2);
            foreach (var z in new[] { 80f, 88f, 96f })
                foreach (var x in new[] { -5f, 5f }) B.Prop("Pillar_Vault_4m", x, 0, z);
            // Containment pit glow where the Guardian rises (visible through the grating).
            B.Box(0, -0.38f, 78, 6, 0.02f, 6, "emit_red", collide: false, shadow: false);
            VaultKit.Debris(B, -4, 92, 2, 6, 701, true);
            // Blast door: frame (static) + lifting door with the eight countdown lights at the asset's sockets.
            B.Prop("Vault_BlastDoor_Frame", 0, 0, 104.2f, Mathf.PI);
            blastDoor = VaultKit.PropUnder(B, dyn, "Vault_BlastDoor", 0, 0, 104.2f, Mathf.PI).transform;
            var dim = VaultKit.Glow(0x401010, 1);
            var red = VaultKit.Glow(0xff3a2e, 2);
            var green = VaultKit.Glow(0x52ff9a, 2);
            for (var i = 0; i < 8; i++)
            {
                var l = EnvProps.Instantiate("Vault_BlastDoor_Light", blastDoor, false);
                // Door is turned 180 deg: local -4.2 + 1.2i lands at prototype x = -4.2 + 1.2i (the prototype light order).
                l.transform.localPosition = new Vector3(-4.2f + i * 1.2f, 8.5f, 0.69f);
                l.transform.localRotation = Quaternion.identity;
                var (rs, sets) = VaultKit.MaterialStates(l, "emit_red", new[] { dim, red, green });
                blastLightRenderers[i] = rs;
                blastLightSets[i] = sets;
            }
            blastBlocker = VaultKit.DoorBlocker(B, 0, 5, 104.2f, 16, 10, 0.8f);
            lights.Add(B.PointLight(0, 9, 90, 0xff8a6a, 160, 30, 1.4f));
            lights.Add(B.PointLight(0, 8, 78, 0xffd49a, 120, 24, 1.5f));
            // Core lift room.
            VaultKit.Room(B, -8, 104, 8, 118, 7, "grate", "metal_dark", "metal_dark", "emit_violet", "n");
            Panels("Vault_Wall_Panel_4m_Cyan", 'w', -8, 108, 112, 116);
            Panels("Vault_Wall_Panel_4m_Cyan", 'e', 8, 108, 112, 116);
            Panels("Vault_Wall_Panel_4m_Cyan", 's', 118, -6, -2, 2, 6);
            B.Box(0, 0.05f, 109, 6, 0.04f, 0.12f, "emit_cyan", collide: false, shadow: false);
            B.Box(0, 0.05f, 115, 6, 0.04f, 0.12f, "emit_cyan", collide: false, shadow: false);
            B.Box(-3, 0.05f, 112, 0.12f, 0.04f, 6, "emit_cyan", collide: false, shadow: false);
            B.Box(3, 0.05f, 112, 0.12f, 0.04f, 6, "emit_cyan", collide: false, shadow: false);
            B.Prop("Terminal_Kiosk", 5, 0, 109, -Mathf.PI / 2);
            B.Sign(0, 5, 117.75f, 6, 0.9f, Mathf.PI, new[] { "CORE ACCESS" }, fg: 0x7fe0ff, bg: 0x08141a, glow: 1.4f);
            await Progress(0.6f, "Guardian gallery");

            glowLights = lights.ToArray();
            glowBase = new float[glowLights.Length];
            for (var i = 0; i < glowLights.Length; i++) glowBase[i] = glowLights[i] != null ? glowLights[i].intensity : 0;

            Layout();
            MapBounds(-24, -6, 16, 120);
            MapShape("floor", 0, 0, 10, 8);
            MapShape("floor", 0, 22, 20, 36);
            MapShape("floor", -16, 24, 12, 12);
            MapShape("floor", 0, 50, 28, 20);
            MapShape("floor", 0, 67, 16, 14);
            MapShape("floor", 0, 89, 16, 30);
            MapShape("floor", 0, 111, 16, 14);
            MapLabel("HALL", 0, 22);
            MapLabel("LOCK", 0, 50);
            MapLabel("ATTUNEMENT", 0, 67);
            MapLabel("GALLERY", 0, 89);
            MapLabel("CORE LIFT", 0, 111);
            await Progress(0.75f, "Vault ready");
        }

        /// <summary>
        /// Heavy wall panels (wall-base pivot on the wall's interior face) at the given centres along one side.
        /// side: n (faces +z), s (faces -z), w (faces +x), e (faces -x); `fixedCoord` is the interior face.
        /// Visual only: the prototype's wall boxes keep the collision.
        /// </summary>
        void Panels(string asset, char side, float fixedCoord, params float[] centres)
        {
            foreach (var c in centres)
            {
                switch (side)
                {
                    case 'n': B.Prop(asset, c, 0, fixedCoord + 0.01f, 0, collide: false); break;
                    case 's': B.Prop(asset, c, 0, fixedCoord - 0.01f, Mathf.PI, collide: false); break;
                    case 'w': B.Prop(asset, fixedCoord + 0.01f, 0, c, Mathf.PI / 2, collide: false); break;
                    default: B.Prop(asset, fixedCoord - 0.01f, 0, c, -Mathf.PI / 2, collide: false); break;
                }
            }
        }

        Resonator MakeResonator(Vector3 p, int i)
        {
            var r = new Resonator { Pos = p };
            B.Prop("Vault_ResonatorPillar", p.x, 0, p.z);
            var housing = B.Prop("Vault_ResonatorRing", p.x, 2.2f, p.z, 0, collide: false);
            if (VaultKit.IsPlaceholder(housing)) Destroy(housing);
            else VaultKit.SwapMaterial(housing, "emit_violet", EnvMaterials.Get("metal_dark"));
            for (var k = 0; k < 4; k++)
            {
                var mesh = VaultKit.ArcTorusFlat(0.75f, 0.068f, k * (Mathf.PI / 2) + 0.075f, Mathf.PI / 2 - 0.15f);
                r.Segments[k] = VaultKit.Glow(0x202030, 1);
                VaultKit.MeshGo("ResonatorSeg" + k, mesh, r.Segments[k], dyn, V(p.x, 2.2f, p.z), Quaternion.identity);
            }
            var top = VaultKit.PropUnder(B, dyn, "Vault_Crystal", p.x, 3.1f, p.z);
            VaultKit.SwapMaterial(top, "aether", EnvMaterials.Aether(Hex(0xa47dff), 1.3f, Hex(0xc8a8ff)), true);
            VaultKit.SetShadows(top, false);
            B.GlowSprite(p.x, 3.1f, p.z, 1.1f, 0xa47dff, 0.9f);
            r.Prompts = new string[5];
            for (var v = 1; v <= 4; v++) r.Prompts[v] = $"Tune resonator {i + 1} (now {v})";
            return r;
        }

        void MakeGlyph(Vector3 p, int i)
        {
            // Group on the wall face; the Blender plaque (back-centre pivot) and the order/value marks reveal together.
            float yaw;
            Vector3 wall;
            if (Mathf.Abs(p.x) > 10) { yaw = p.x < 0 ? Mathf.PI / 2 : -Mathf.PI / 2; wall = new Vector3(Mathf.Sign(p.x) * 13.99f, p.y, p.z); }
            else { yaw = Mathf.PI; wall = new Vector3(p.x, p.y, 59.99f); }
            var group = new GameObject("Glyph" + (i + 1));
            group.transform.SetParent(dyn, false);
            group.transform.localPosition = V(wall);
            group.transform.localRotation = YawQ(yaw);
            var plate = EnvProps.Instantiate("Vault_GlyphPlate", group.transform, false);
            plate.transform.localPosition = Vector3.zero;
            plate.transform.localRotation = Quaternion.identity;
            var n = GlyphTarget[i];
            VaultKit.MeshGo("Marks", VaultKit.GlyphMarks(i, n, 0.09f), VaultKit.Glow(0xc8a8ff, 2.2f), group.transform, Vector3.zero, Quaternion.identity);
            var hint = $"Glyph {i + 1}: tune resonator {i + 1} to {n}.";
            Interactable($"g_glyph_{i + 1}", "lore", p, 4, $"Resonance glyph {i + 1}", () => Toast(hint),
                available: () => true, hidden: true, revealObject: group);
        }

        void Layout()
        {
            Spawn("start", 0, 0.05f, 1.5f, 0);
            Spawn("from_facility", 0, 0.05f, 1.5f, 0);
            Spawn("from_core", 0, 0.05f, 110, Mathf.PI);
            Exit("x_vault_facility", "facility", "from_vault", 0, 0.05f, -1.5f, 2, "Ride the lift back up to the facility");
            Exit("i_core_lift", "core", "from_vault", 0, 0.05f, 112, 2.8f, "Ride the lift down to the Aether Core",
                lockedText: "The lift is sealed behind the blast door.", requiresFn: () => Flag("vault_escaped"));
            Trigger("t_vault_lock", P(-14, -1, 40), P(14, 6, 46));
            Trigger("t_vault_guardian", P(-8, -1, 84), P(8, 6, 90), available: () => Check("stage:m4_vault:guardian"));
            Trigger("t_vault_blastdoor", P(-8, -1, 106), P(8, 6, 116));
            Encounter("e_vault_hall", "quest", new[] { Wave(E("stalker", -5, 0.05f, 30), E("stalker", 5, 0.05f, 33), E("drone", 0, 5, 26)) }, P(0, 0, 24), 22);
            Encounter("e_vault_deep", "quest", new[]
            {
                Wave(E("sentinel", -8, 0.05f, 56), E("stalker", 8, 0.05f, 56)),
                Wave(E("stalker", 0, 0.05f, 44), E("sentinel", 6, 0.05f, 46)),
            }, P(0, 0, 55), 22);
            Encounter("e_vault_guardian", "quest", new[] { Wave(E("guardian_vault", 0, 0.05f, 78, 0)) }, P(0, 0, 89), 30);
            Collectible("c_frag_12", 12, 4.1f, 58);
            Collectible("c_rec_06", -6.5f, 1.1f, 70);
            Collectible("c_cache_05", -20.5f, 0.6f, 20);
            for (var i = 0; i < 3; i++)
            {
                var k = i;
                var r = resonators[i];
                Interactable($"i_resonator_{i + 1}", "puzzle", new Vector3(r.Pos.x, 1.6f, r.Pos.z), 2.2f, () => r.Prompts[Mathf.Clamp(r.Value, 1, 4)],
                    () => Tune(k), available: () => !lockOpen);
            }
            Interactable("i_vault_lock", "inspect", P(0, 1.6f, 58.5f), 2.2f, "Inspect the resonance lock",
                () => Toast("Three resonators must hum in tune. Echo Sight should reveal how."), available: () => !lockOpen);
            QuestPoint("i_attunement", P(0, 1.6f, 65), "Attune to the Core", new[] { "stage:m4_vault:upgrade" }, 2.6f);
            Interactable("i_hidden_door", "door", P(-10.2f, 1.6f, 24), 3, "Enter the singing wall", () =>
            {
                OpenHidden(true);
                EmitInteract("i_hidden_door");
            }, available: () => !hiddenOpen, hidden: true, onRevealAction: HiddenRevealedLook);
            Interactable("i_hidden_pedestal", "inspect", P(-16, 1.4f, 24), 2.4f, "Take what Maren left behind", () => EmitInteract("i_hidden_pedestal"),
                available: () => Check("stage:sq_hidden_vault:claim"),
                lockedReason: () => Check("quest:sq_hidden_vault:done") ? null : "An echo hums here, waiting for someone who was asked to come.");
            SaveTerminal("i_save_vault", P(3.8f, 1.3f, 2.5f), 2);
            Marker("guardian_rise", 0, 0, 78);
            Marker("relic", -16, 1.7f, 24);
        }

        // ------------------------------------------------------------------ puzzle and doors

        void Tune(int i)
        {
            var r = resonators[i];
            r.Value = (r.Value % 4) + 1;
            Sfx("echo", V(r.Pos));
            PaintResonators();
            for (var k = 0; k < 3; k++) if (resonators[k].Value != GlyphTarget[k]) return;
            OpenLock(false);
            SetFlag("vault_lock_open");
            Sfx("door", V(0, 0, 60.2f));
            Toast("The resonance lock disengages.");
        }

        void PaintResonators()
        {
            for (var i = 0; i < 3; i++)
            {
                var r = resonators[i];
                var ok = r.Value == GlyphTarget[i];
                for (var k = 0; k < 4; k++)
                {
                    var lit = k < r.Value;
                    var c = lit ? FxMaterials.Hdr(Hex(ok ? 0x52ff9au : 0xa47dffu), 2.4f) : FxMaterials.Hdr(Hex(0x202030), 1);
                    r.Segments[k].SetColor("_BaseColor", c);
                    if (r.Segments[k].HasProperty("_Color")) r.Segments[k].SetColor("_Color", c);
                }
            }
        }

        void OpenLock(bool instant)
        {
            lockOpen = true;
            if (lockBlocker != null) lockBlocker.SetActive(false);
            if (!instant) return;
            for (var k = 0; k < 2; k++)
            {
                leafX[k] = Mathf.Sign(leafX[k]) * 4.5f;
                lockLeaves[k].localPosition = V(leafX[k], 0, 60.2f);
            }
            for (var i = 0; i < 3; i++) resonators[i].Value = GlyphTarget[i];
        }

        void OpenHidden(bool sound)
        {
            if (hiddenOpen) return;
            hiddenOpen = true;
            if (hiddenBlocker != null) hiddenBlocker.SetActive(false);
            if (hiddenWall != null) hiddenWall.SetActive(false);
            if (sound) Sfx("door", V(-10.2f, 1.6f, 24));
        }

        void HiddenRevealedLook()
        {
            if (hiddenGlowing || hiddenWall == null) return;
            hiddenGlowing = true;
            VaultKit.SwapMaterial(hiddenWall, "", EnvMaterials.Get("emit_violet"));
        }

        // ------------------------------------------------------------------ lifecycle

        public override void OnLoaded()
        {
            base.OnLoaded();
            if (Flag("vault_lock_open")) OpenLock(true);
            if (lockBlocker != null) lockBlocker.SetActive(!lockOpen);
            if (Check("quest:sq_hidden_vault:done") || Check("stage:sq_hidden_vault:claim")) OpenHidden(false);
            if (hiddenBlocker != null) hiddenBlocker.SetActive(!hiddenOpen);
            if (Revealed("i_hidden_door")) HiddenRevealedLook();
            PaintResonators();
            if (Flag("vault_escaped"))
            {
                blastOpen = true;
                blastY = 9.5f;
                blastDoor.localPosition = V(0, blastY, 104.2f);
                SetBlastLights(8, true);
            }
            else SetBlastLights(0, false);
            if (blastBlocker != null) blastBlocker.SetActive(!blastOpen);
        }

        public override void OnEnter()
        {
            base.OnEnter();
            Emitter(0, 0.5f, 67, "aether", 10, 2);
            Emitter(0, 0.3f, 22, "aether", 4, 9);
        }

        void SetBlastLights(int lit, bool cycling)
        {
            for (var i = 0; i < 8; i++)
            {
                var state = !cycling ? 0 : i < lit ? 2 : 1;
                if (blastLightState[i] == state) continue;
                blastLightState[i] = state;
                var rs = blastLightRenderers[i];
                if (rs == null) continue;
                for (var k = 0; k < rs.Length; k++) if (rs[k] != null) rs[k].sharedMaterials = blastLightSets[i][k][state];
            }
        }

        public override void Tick(float dt)
        {
            base.Tick(dt);
            var t = ZoneTime;
            if (attuneCore != null)
            {
                attuneCore.localRotation *= Quaternion.AngleAxis(-dt * 0.6f * Mathf.Rad2Deg, Vector3.up);
                attuneCore.localScale = Vector3.one * (1 + Mathf.Sin(t * 2) * 0.06f);
            }
            if (relic != null) relic.localRotation *= Quaternion.AngleAxis(-dt * 0.5f * Mathf.Rad2Deg, Vector3.up);

            // Lock door leaves slide open.
            if (lockOpen)
            {
                for (var k = 0; k < 2; k++)
                {
                    var target = Mathf.Sign(leafX[k]) * 4.5f;
                    if (Mathf.Abs(target - leafX[k]) < 0.001f) continue;
                    leafX[k] += (target - leafX[k]) * Mathf.Min(1, dt * 0.8f);
                    lockLeaves[k].localPosition = V(leafX[k], 0, 60.2f);
                }
            }

            // Vents: telegraph glow, then a damaging pulse.
            var pp = PlayerProto;
            var hasPlayer = Player != null;
            for (var i = 0; i < vents.Length; i++)
            {
                var v = vents[i];
                var c = (t + v.Offset) % 4.2f;
                var active = c > 2.4f && c < 3.6f;
                var warn = c > 1.6f && c <= 2.4f;
                var opacity = active ? 0.55f + Mathf.Sin(t * 40) * 0.1f : warn ? 0.12f + Mathf.Sin(t * 20) * 0.08f : 0;
                v.Renderer.enabled = opacity > 0.001f;
                if (v.Renderer.enabled)
                {
                    var col = ventColor;
                    col.a = opacity;
                    v.Mat.SetColor("_BaseColor", col);
                }
                v.HitCd -= dt;
                if (active && hasPlayer && v.HitCd <= 0)
                {
                    var py = pp.y + 0.4f;
                    if (pp.x >= -10 && pp.x <= 10 && py >= -1 && py <= 2.5f && pp.z >= v.Z - 0.8f && pp.z <= v.Z + 0.8f)
                    {
                        v.HitCd = 0.9f;
                        DamagePlayer(14, "vent", V(pp.x, 0, v.Z));
                        Vfx?.SparksDir(PlayerPos + Vector3.up * 0.6f, Vector3.up, 12, Hex(0xc8a8ff), 5);
                    }
                }
                if (active && Random.value < 0.3f) Vfx?.Embers(V((Random.value - 0.5f) * 18, 0.2f, v.Z), 1, Hex(0xa47dff), 0.4f, 3);
            }

            // Blast door cycle during the Guardian encounter.
            if (!blastOpen && Flag("blastdoor_cycling"))
            {
                blastT += dt;
                var k = Mathf.Min(1, blastT / DoorTime);
                SetBlastLights(Mathf.FloorToInt(k * 8), true);
                if (k >= 1)
                {
                    blastOpen = true;
                    if (blastBlocker != null) blastBlocker.SetActive(false);
                    Sfx("door", V(0, 0, 104.2f));
                    Toast("The blast door is open. Get through!");
                }
            }
            if (blastOpen && blastY < 9.5f)
            {
                blastY = Mathf.Min(9.5f, blastY + dt * 3);
                blastDoor.localPosition = V(0, blastY, 104.2f);
            }

            // Lights breathe slightly (prototype: intensity *= 1 + sin(1.5t + i) * 0.002 per frame).
            for (var i = 0; i < glowLights.Length; i++)
            {
                var l = glowLights[i];
                if (l != null) l.intensity = glowBase[i] * (1 + 0.08f * (Mathf.Cos(i) - Mathf.Cos(t * 1.5f + i)));
            }
        }
    }
}
