using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// The Aether Core (port of CoreZone.ts): a circular chamber (radius ~27) with the Core suspended above the centre.
    /// The lift arrives at the south edge (z≈31); the heart pedestal sits at the centre beneath the Core. During the boss
    /// stage telegraphed discharges strike near the player. <see cref="Released"/> (set by cin_ending) makes the Core flare.
    /// Built from the Blender core kit: arena floor, machinery wall ring, heart pedestal, tether anchors, the four broken
    /// orbit rings (animated like the prototype's torus rings) and cover blocks; the Core and tethers use the Aether shader.
    /// </summary>
    public sealed class CoreZone : ProceduralZone
    {
        public override string ZoneId => "core";

        /// <summary>The echoes have been released (ending): the Core spins faster and burns brighter.</summary>
        public bool Released;

        public Vector3 CoreProto => new(0, 15, 0);

        sealed class Debris
        {
            public Transform T;
            public Vector3 Axis;
            public float Speed, Orbit, R, Y, A;
        }

        sealed class Strike
        {
            public bool Active, Fired;
            public float T;
            public Vector3 Pos;          // Unity space
            public Transform Ring;
            public Renderer Renderer;
            public Material Mat;
        }

        static readonly Quaternion RingFlatToXY = Quaternion.Euler(90, 0, 0);

        Transform dyn, core, coreInner;
        Material coreMat;
        readonly Transform[] rings = new Transform[4];
        readonly float[] ringRx = new float[4], ringRy = new float[4];
        readonly Debris[] debris = new Debris[26];
        readonly Strike[] strikes = new Strike[3];
        Light coreLight;
        float coreLightScale;
        float strikeT = 4;
        Color strikeColor;

        protected override async Task BuildZone()
        {
            ZoneSettings(-20, true, "boss", "core_drone");
            SetAtmosphere(new AtmosphereSettings
            {
                // Open void above the chamber: near-black sky (prototype background 0x02040a); the cyan glow stands in for
                // the baked environment's overhead cyan light in the ambient term.
                SkyTop = 0x03060e, SkyHorizon = 0x0a1426, SkyBottom = 0x020306, Glow = 0x5fd8ff, GlowStrength = 0.4f,
                // Neutral steel-grey base so the core's cyan light and the violet accents read as light, not as a wash.
                FogColor = 0x080a12, FogDensity = 0.008f,
                HemiSky = 0x66707e, HemiGround = 0x100e14, HemiIntensity = 1.15f, EnvIntensity = 0.9f,
                SunPos = new Vector3(5, 50, 10), SunTarget = Vector3.zero, SunColor = 0xcad6e2, SunIntensity = 1.0f, SunShadows = true,
                Exposure = 1.02f, Contrast = 1.14f, Saturation = 1.06f, Lift = new Vector3(0.002f, 0f, 0.004f), Gain = new Vector3(1f, 1f, 1.01f),
                BloomThreshold = 0.95f,
                // cinematic grade: deep blue shadows under the cyan core light, highlights left clean
                SplitShadows = 0x5a7896, SplitHighlights = 0x928a94, GradeShadows = new Vector3(0.96f, 0.99f, 1.06f), GradeHighlights = new Vector3(1.03f, 1f, 1f),
                ShadowLift = 0.01f, Temperature = -4f, Vignette = 0.36f, LensStreaks = 0.8f,
            });
            B.LightBudget = 10;
            dyn = new GameObject("Dynamic").transform;
            dyn.SetParent(transform, false);
            await Progress(0.1f, "Core chamber");

            // ---------------------------------------------------------------- Arena floor: central disc + broken outer ring
            B.Prop("Core_ArenaFloor", 0, 0, 0, 0, collide: false);
            VaultKit.CylCollider(B, 0, -0.5f, 0, 27.5f, 1.0f, 64);
            // Outer machinery wall (Blender blocks face the arena centre; heights 12/16/20 like the prototype).
            for (var i = 0; i < 36; i++)
            {
                var a = i / 36f * Mathf.PI * 2;
                const float r = 33;
                if (Mathf.Abs(Mathf.Sin(a / 2)) < 0.06f) continue; // gap at the lift (south)
                var h = 12 + (i % 3) * 4;
                B.Prop(h == 12 ? "Core_Machinery_12m" : h == 16 ? "Core_Machinery_16m" : "Core_Machinery_20m", Mathf.Sin(a) * r, 0, Mathf.Cos(a) * r, a + Mathf.PI);
            }
            // Invisible fence at the arena edge (falls are allowed at the broken gaps only).
            for (var i = 0; i < 32; i++)
            {
                var a = i / 32f * Mathf.PI * 2;
                if (Mathf.Abs(Mathf.Cos(a) - 1) < 0.02f) continue;
                B.Wall(Mathf.Sin(a) * 27.6f, 2, Mathf.Cos(a) * 27.6f, 5.6f, 4, 0.5f, a + Mathf.PI / 2);
            }
            // Lift landing (south).
            for (var gx = -1; gx <= 1; gx += 2)
                for (var gz = -1; gz <= 1; gz += 2) B.Prop("Floor_Grate_4m", gx * 2, 0, 31 + gz * 2, 0, collide: false);
            B.SolidCollider(0, -0.25f, 31, 8, 0.5f, 8);
            B.Box(0, 0.02f, 28, 6, 0.04f, 0.12f, "emit_cyan", collide: false, shadow: false);
            B.Box(0, 0.02f, 34, 6, 0.04f, 0.12f, "emit_cyan", collide: false, shadow: false);
            B.Box(-3, 0.02f, 31, 0.12f, 0.04f, 6, "emit_cyan", collide: false, shadow: false);
            B.Box(3, 0.02f, 31, 0.12f, 0.04f, 6, "emit_cyan", collide: false, shadow: false);
            B.Wall(0, 2, 35.2f, 8, 4, 0.4f);
            B.Wall(-4.2f, 2, 31, 0.4f, 4, 8);
            B.Wall(4.2f, 2, 31, 0.4f, 4, 8);
            // Guard rails along the landing edges (the invisible walls above keep the prototype's collision).
            foreach (var x in new[] { -3.95f, 3.95f })
            {
                for (var z = 28f; z <= 34; z += 2) B.Prop("Railing_2m", x, 0, z, Mathf.PI / 2, collide: false);
                B.Prop("Railing_Post", x, 0, 27, 0, collide: false);
            }
            for (var x = -3f; x <= 3; x += 2) B.Prop("Railing_2m", x, 0, 34.95f, 0, collide: false);
            B.Prop("Railing_Post", -4, 0, 34.95f, 0, collide: false);

            // Damaged platforms and cover (same mulberry32 sequence as the prototype, so positions and sizes match).
            var rr = new VaultRng(404);
            for (var i = 0; i < 8; i++)
            {
                var a = i / 8f * Mathf.PI * 2 + 0.2f;
                var d = 14 + rr.Next() * 8;
                var sx = 2 + rr.Next() * 2;
                var sy = 1.2f + rr.Next();
                var rz = rr.Range(-0.1f, 0.1f);
                CoverBlock(Mathf.Sin(a) * d, Mathf.Cos(a) * d, sx, sy, 1.4f, a, rz);
            }
            VaultKit.Debris(B, -12, -10, 2.4f, 8, 405, true);
            VaultKit.Debris(B, 14, 6, 2.4f, 8, 406, true);
            await Progress(0.3f, "Arena");

            // ---------------------------------------------------------------- Heart pedestal and the Core
            B.Prop("Core_Pedestal", 0, 0, 0, 0, collide: false);
            VaultKit.CylCollider(B, 0, 0.6f, 0, 3.8f, 1.2f, 32);
            B.Cyl(0, 1.22f, 0, 2.6f, 2.6f, 0.04f, "emit_cyan", 48, collide: false);
            // Dedicated, dimmer Aether instance for the giant core so it doesn't flood the bloom.
            coreMat = EnvMaterials.Aether(Hex(0x5fd8ff), 0.75f, Hex(0xa47dff));
            core = VaultKit.MeshGo("Core", FxMesh.Sphere(6, 48, 32), coreMat, dyn, V(CoreProto), Quaternion.identity).transform;
            coreInner = VaultKit.MeshGo("CoreInner", FxMesh.Sphere(3.6f, 32, 20), VaultKit.Glow(0x8fdcff, 1.15f), dyn, V(CoreProto), Quaternion.identity).transform;
            var ringNames = new[] { "Core_Ring_A", "Core_Ring_B", "Core_Ring_C", "Core_Ring_D" };
            for (var i = 0; i < 4; i++)
            {
                rings[i] = VaultKit.PropUnder(B, dyn, ringNames[i], 0, 15, 0).transform;
                ringRx[i] = i * 0.7f;
                ringRy[i] = i * 1.3f;
                rings[i].localRotation = Rot(ringRx[i], ringRy[i], 0) * RingFlatToXY;
            }
            // Energy tethers from the floor anchors to the Core.
            var tetherMat = EnvMaterials.Aether(Hex(0x5fd8ff), 1f, Hex(0xa47dff));
            for (var i = 0; i < 6; i++)
            {
                var a = i / 6f * Mathf.PI * 2;
                float bx = Mathf.Sin(a) * 20, bz = Mathf.Cos(a) * 20;
                B.Prop("Core_TetherAnchor", bx, 0, bz, a + Mathf.PI, collide: false);
                VaultKit.CylCollider(B, bx, 0.8f, bz, 1.2f, 1.6f, 10);
                var baseU = V(bx, 1.7f, bz);
                var topU = V(CoreProto + new Vector3(Mathf.Sin(a) * 4, -2, Mathf.Cos(a) * 4));
                var dir = topU - baseU;
                var mesh = FxMesh.Cylinder(0.12f, 0.3f, dir.magnitude, 8, false);
                VaultKit.MeshGo("Tether" + i, mesh, tetherMat, dyn, (baseU + topU) / 2, Quaternion.FromToRotation(Vector3.up, dir.normalized));
                B.GlowSprite(bx, 1.75f, bz, 1.8f, 0x5fd8ff, 0.8f);
            }
            coreLight = B.PointLight(0, 12, 0, 0x7fe0ff, 320, 60, 1.5f);
            coreLightScale = coreLight != null ? coreLight.intensity / 320f : 0;
            B.PointLight(0, 4, 24, 0xa98aff, 40, 16, 1.6f); // violet accent at the approach
            // Floating debris: rusted scrap and dark chunks orbiting the Core.
            for (var i = 0; i < 26; i++)
            {
                var gx = rr.Range(0.6f, 2.4f);
                var gy = rr.Range(0.4f, 1.4f);
                var gz = rr.Range(0.6f, 2f);
                var rust = rr.Chance(0.3f);
                var axis = new Vector3(rr.Range(-1, 1), rr.Range(-1, 1), rr.Range(-1, 1));
                var dbr = new Debris
                {
                    Axis = axis.sqrMagnitude > 1e-6f ? new Vector3(-axis.x, axis.y, axis.z).normalized : Vector3.up,
                    Speed = rr.Range(0.1f, 0.5f),
                    Orbit = rr.Range(0.02f, 0.06f) * rr.Sign(),
                    R = rr.Range(10, 26),
                    Y = rr.Range(6, 24),
                    A = rr.Range(0, Mathf.PI * 2),
                };
                // Pivot object at the chunk's centre so it tumbles in place (the props pivot at their base).
                var asset = rust ? "Scrap_Metal" : "Rubble_Chunk_L";
                var info = EnvProps.Get(asset);
                var size = info != null ? info.Size : Vector3.one;
                var scale = new Vector3(gx / Mathf.Max(0.1f, size.x), gy / Mathf.Max(0.1f, size.y), gz / Mathf.Max(0.1f, size.z));
                var pivot = new GameObject("Debris" + i).transform;
                pivot.SetParent(dyn, false);
                var go = VaultKit.PropUnder(B, pivot, asset, 0, 0, 0);
                go.transform.localScale = scale;
                go.transform.localPosition = -Vector3.Scale(info != null ? info.BoundsCenter : new Vector3(0, size.y / 2, 0), scale);
                dbr.T = pivot;
                debris[i] = dbr;
                PlaceDebris(dbr, 0);
            }
            // Pooled discharge telegraph rings (boss phase hazard).
            var ringMesh = VaultKit.FlatRing(2.2f, 2.5f, 32);
            strikeColor = FxMaterials.Hdr(Hex(0xa47dff), 2);
            for (var i = 0; i < strikes.Length; i++)
            {
                var mat = VaultKit.Additive(0xa47dff, 2);
                var go = VaultKit.MeshGo("Discharge" + i, ringMesh, mat, dyn, Vector3.zero, Quaternion.identity);
                go.SetActive(false);
                strikes[i] = new Strike { Ring = go.transform, Renderer = go.GetComponent<Renderer>(), Mat = mat };
            }
            await Progress(0.5f, "The Core");

            Layout();
            MapBounds(-34, -34, 34, 36);
            MapShape("floor", 0, 0, 52, 52);
            MapShape("water", 0, 0, 7, 7);
            MapShape("floor", 0, 31, 8, 8);
            MapLabel("HEART", 0, 0);
            MapLabel("LIFT", 0, 31);
        }

        /// <summary>
        /// Prototype cover box (centre y 0.6, size sx × sy × sz, yaw a, roll rz) as a Blender cover block scaled to the
        /// same size; the collider is the prototype's exact box.
        /// </summary>
        void CoverBlock(float x, float z, float sx, float sy, float sz, float yaw, float rz)
        {
            var large = sx >= 3;
            var asset = large ? "Core_CoverBlock_Large" : "Core_CoverBlock";
            float L = large ? 4 : 3, H = large ? 2.2f : 1.6f, D = 1.4f;
            var q = Rot(0, yaw, rz);
            var c = V(x, 0.6f, z);
            B.AddBoxCollider(c, new Vector3(sx, sy, sz), q, CombatLayers.World);
            var go = B.Prop(asset, x, 0.6f, z, yaw, collide: false);
            go.transform.localRotation = q;
            go.transform.localPosition = c + q * new Vector3(0, -sy / 2, 0);
            go.transform.localScale = new Vector3(sx / L, sy / H, sz / D);
        }

        void Layout()
        {
            Spawn("start", 0, 0.05f, 30, Mathf.PI);
            Spawn("from_vault", 0, 0.05f, 30, Mathf.PI);
            Exit("x_core_vault", "vault", "from_core", 0, 0.05f, 33.5f, 1.6f, "Ride the lift back up",
                lockedText: "The lift won't move while the Core is under attack.",
                requiresFn: () => !Check("stage:m5_core:boss") && !Check("stage:m5_core:waves"));
            Encounter("e_core_waves", "quest", new[]
            {
                Wave(E("drone", -10, 6, -6), E("drone", 10, 6, -6), E("stalker", -8, 0.05f, 4), E("stalker", 8, 0.05f, 4)),
                Wave(E("sentinel", -12, 0.05f, -12), E("sentinel", 12, 0.05f, -12), E("stalker", 0, 0.05f, -18), E("drone", 0, 7, 0)),
            }, P(0, 0, 0), 26);
            Encounter("e_core_guardian", "quest", new[] { Wave(E("guardian", 0, 0.05f, -14, 0)) }, P(0, 0, 0), 26);
            QuestPoint("i_core_terminal", P(0, 1.4f, 22), "Approach the Core", new[] { "stage:m5_core:listen" }, 5);
            QuestPoint("i_core_heart", P(0, 1.6f, 3.2f), "Release the echoes", new[] { "stage:m5_core:release" }, 3.6f);
            Marker("heart", 0, 1.25f, 0);
            Marker("core", 0, 15, 0);
        }

        public override void OnEnter()
        {
            base.OnEnter();
            Emitter(0, 1.3f, 0, "aether", 14, 2.5f);
            Emitter(0, 0.3f, 0, "aether", 10, 22);
        }

        void PlaceDebris(Debris d, float t)
        {
            d.T.localPosition = V(Mathf.Sin(d.A) * d.R, d.Y + Mathf.Sin(t * 0.4f + d.R) * 0.6f, Mathf.Cos(d.A) * d.R);
        }

        /// <summary>Telegraphed energy discharge near the player (boss fight hazard).</summary>
        void StartStrike()
        {
            Strike s = null;
            foreach (var x in strikes) if (!x.Active) { s = x; break; }
            if (s == null) return;
            var p = PlayerPos;
            var pos = new Vector3(p.x + (Random.value - 0.5f) * 6, 0.05f, p.z + (Random.value - 0.5f) * 6);
            if (pos.magnitude > 25) pos = pos.normalized * 24;
            s.Active = true;
            s.Fired = false;
            s.T = 0;
            s.Pos = pos;
            s.Ring.localPosition = new Vector3(pos.x, 0.08f, pos.z);
            s.Ring.localScale = Vector3.one;
            s.Ring.gameObject.SetActive(true);
            Sfx("enemy_telegraph", pos);
        }

        public override void Tick(float dt)
        {
            base.Tick(dt);
            var t = ZoneTime;
            var intensity = Released ? 2.2f : 1;
            core.localRotation *= Quaternion.AngleAxis(-dt * 0.08f * intensity * Mathf.Rad2Deg, Vector3.up);
            core.localScale = Vector3.one * (1 + Mathf.Sin(t * 1.4f) * 0.03f * intensity);
            coreInner.localRotation *= Quaternion.AngleAxis(dt * 0.2f * Mathf.Rad2Deg, Vector3.up);
            for (var i = 0; i < 4; i++)
            {
                ringRx[i] += dt * (0.05f + i * 0.02f) * intensity;
                ringRy[i] += dt * (0.03f + i * 0.015f) * (i % 2 == 1 ? -1 : 1) * intensity;
                rings[i].localRotation = Rot(ringRx[i], ringRy[i], 0) * RingFlatToXY;
            }
            for (var i = 0; i < debris.Length; i++)
            {
                var d = debris[i];
                d.A += d.Orbit * dt;
                PlaceDebris(d, t);
                d.T.localRotation *= Quaternion.AngleAxis(-d.Speed * dt * Mathf.Rad2Deg, d.Axis);
            }
            if (coreLight != null) coreLight.intensity = coreLightScale * (300 + Mathf.Sin(t * 1.4f) * 40) * (Released ? 1.8f : 1);
            EnvMaterials.SetAetherIntensity(coreMat, Released ? 1.6f : 0.75f);

            // Discharges during the boss fight.
            if (VaultKit.StageIs("m5_core", "boss") && Player != null)
            {
                strikeT -= dt;
                if (strikeT <= 0)
                {
                    strikeT = 3.5f + Random.value * 2.5f;
                    StartStrike();
                }
            }
            for (var i = 0; i < strikes.Length; i++)
            {
                var s = strikes[i];
                if (!s.Active) continue;
                s.T += dt;
                s.Ring.localScale = Vector3.one * (1 - Mathf.Min(0.6f, s.T * 0.4f));
                var col = strikeColor;
                col.a = 0.5f + Mathf.Sin(s.T * 20) * 0.3f;
                s.Mat.SetColor("_BaseColor", col);
                if (!s.Fired && s.T > 1.3f)
                {
                    s.Fired = true;
                    var vfx = Vfx;
                    if (vfx != null)
                    {
                        vfx.FlashSprite(s.Pos + Vector3.up * 1.45f, 4, Hex(0xc8a8ff), 0.2f);
                        vfx.SparksDir(s.Pos + Vector3.up * 0.25f, Vector3.up, 30, Hex(0xc8a8ff), 9);
                        vfx.LightProto(s.Pos + Vector3.up * 1.95f, Hex(0xa47dff), 60, 0.3f);
                    }
                    Sfx("slam", s.Pos);
                    Shake(0.2f);
                    var p = PlayerPos;
                    if (Player != null && Vector3.Distance(p, s.Pos) < 2.6f && p.y < 1.2f) DamagePlayer(18, "discharge", s.Pos);
                }
                if (s.T > 1.6f)
                {
                    s.Active = false;
                    s.Ring.gameObject.SetActive(false);
                }
            }
        }
    }
}
