using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;

namespace EOA
{
    /// <summary>
    /// Car damage and explosions in the open city (one per zone load, under the district root).
    ///   • <see cref="Register"/> makes every parked kit car destructible (the street traffic pool registers its own) and
    ///     adds the car colliders' layer to <see cref="CombatLayers.NeutralTargetMask"/> so attacks reach them.
    ///   • Stages per damaged car (<see cref="VehicleHealth"/>): smoke from the hood at 50 %, fire at 20 % (burns down by
    ///     itself), a short fuse with a flickering warning light at 0 (the player is pulled out of a car on its fuse),
    ///     then the explosion.
    ///   • Explosion: fireball, shockwave ring, sparks, embers, smoke, a light flash, tumbling debris, a boom, camera
    ///     shake (scaled by the gameplay and accessibility shake settings) and rumble; radius damage to enemies, the
    ///     heroes (capped and scaled by difficulty: hurts, never one-shots) and other cars (chain reactions on a short
    ///     fuse); the car becomes a burnt wreck (kit wreck prefab, blackened) that keeps a collider and smoulders.
    ///   • Pedestrians flee burning cars and blasts (<see cref="Hazards"/>); street traffic stops for them.
    /// Pooled: a handful of fire lights and fire-crackle voices go to the nearest fires, debris chunks are a fixed
    /// ballistic pool, wrecks are capped and recycled. No per-frame allocations. Nothing happens during cinematics.
    /// </summary>
    public sealed class VehicleDamage : MonoBehaviour
    {
        public static VehicleDamage Instance { get; private set; }

        const int MaxLights = 4, MaxVoices = 3, MaxDebris = 40, MaxWrecks = 14, MaxBlasts = 4;
        public const float BlastRadius = 9f, ActorRadius = 7f;
        static readonly HashSet<string> Destructible = new() { "CyberCar_Sedan", "CyberCar_Coupe", "CyberCar_Taxi", "CyberVan", "CyberBike" };
        static readonly int BaseColorId = Shader.PropertyToID("_BaseColor"), EmissionId = Shader.PropertyToID("_EmissionColor");
        static readonly Color Fire = new(1f, 0.55f, 0.18f), Smoke = new(0.42f, 0.43f, 0.46f, 0.6f), DarkSmoke = new(0.1f, 0.1f, 0.11f, 0.85f);

        readonly List<VehicleHealth> all = new();
        readonly List<VehicleHealth> active = new();
        Light[] lights;
        VehicleHealth[] lightOwner;
        AudioSource[] voices;
        VehicleHealth[] voiceOwner;
        float assignT;

        struct Chunk { public Transform T; public Vector3 V, Spin; public float Life, Ground; }
        Chunk[] debris;
        int debrisNext;

        sealed class Wreck { public GameObject Go; public string Name; public float Half, HalfW, Smoulder; }
        readonly List<Wreck> wrecks = new();
        int wreckNext;

        readonly Vector3[] blastPos = new Vector3[MaxBlasts];
        readonly float[] blastT = new float[MaxBlasts];
        int blastNext;

        readonly List<CombatHit> hits = new();
        static readonly List<Renderer> rbuf = new();
        static MaterialPropertyBlock mpb;
        bool chain;

        /// <summary>Explosions so far (tests).</summary>
        public int Explosions { get; private set; }
        public int Registered => all.Count;
        public IReadOnlyList<VehicleHealth> All => all;

        // ------------------------------------------------------------------ setup

        /// <summary>The district has loaded: make its cars destructible (OpenCity.OnLoaded).</summary>
        public static VehicleDamage Register(Transform cityRoot)
        {
            CombatLayers.NeutralTargetMask |= 1 << CombatLayers.IgnoreCamera;
            if (cityRoot == null) return null;
            var go = new GameObject("VehicleDamage");
            go.transform.SetParent(cityRoot, false);
            var vd = go.AddComponent<VehicleDamage>();
            foreach (var lg in cityRoot.GetComponentsInChildren<LODGroup>(true))
            {
                var car = lg.gameObject;
                if (!Destructible.Contains(car.name) || car.GetComponentInParent<Traffic>() != null) continue;
                VehicleHealth.Attach(car, VehicleKit.Get(car.name), false);
            }
            foreach (var h in cityRoot.GetComponentsInChildren<VehicleHealth>(true)) vd.all.Add(h);
            Debug.Log($"[vehicles] {vd.all.Count} destructible cars");
            return vd;
        }

        void Awake()
        {
            Instance = this;
            mpb ??= new MaterialPropertyBlock();
            lights = new Light[MaxLights];
            lightOwner = new VehicleHealth[MaxLights];
            for (var i = 0; i < MaxLights; i++)
            {
                var lg = new GameObject("FireLight" + i);
                lg.transform.SetParent(transform, false);
                var l = lg.AddComponent<Light>();
                l.type = LightType.Point;
                l.color = Fire;
                l.range = 12f;
                l.intensity = 0f;
                l.shadows = LightShadows.None;
                l.enabled = false;
                lights[i] = l;
            }
            voices = new AudioSource[MaxVoices];
            voiceOwner = new VehicleHealth[MaxVoices];
            var clip = Resources.Load<AudioClip>("Audio/SFX/car_fire_loop");
            for (var i = 0; i < MaxVoices; i++)
            {
                var ag = new GameObject("FireVoice" + i);
                ag.transform.SetParent(transform, false);
                var s = ag.AddComponent<AudioSource>();
                s.clip = clip;
                s.loop = true;
                s.playOnAwake = false;
                s.spatialBlend = 1f;
                s.rolloffMode = AudioRolloffMode.Logarithmic;
                s.minDistance = 4f;
                s.maxDistance = 45f;
                s.dopplerLevel = 0f;
                voices[i] = s;
            }
            // Debris: small dark chunks, ballistic (no physics bodies), bouncing off the ground they started over.
            debris = new Chunk[MaxDebris];
            var mesh = FxMesh.Box(1f, 1f, 1f);
            var mat = EnvMaterials.Get("metal_dark");
            for (var i = 0; i < MaxDebris; i++)
            {
                var d = new GameObject("Debris" + i);
                d.transform.SetParent(transform, false);
                d.AddComponent<MeshFilter>().sharedMesh = mesh;
                var r = d.AddComponent<MeshRenderer>();
                r.sharedMaterial = mat;
                r.shadowCastingMode = ShadowCastingMode.Off;
                d.SetActive(false);
                debris[i].T = d.transform;
            }
        }

        void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }

        // ------------------------------------------------------------------ stages

        /// <summary>A car took damage: advance its stage.</summary>
        internal void Damaged(VehicleHealth v, Vector3 point, float applied)
        {
            if (v == null || v.State == VehicleHealth.Stage.Wrecked) return;
            var f = v.Health01;
            if (v.State == VehicleHealth.Stage.Intact && f <= 0.5f) v.State = VehicleHealth.Stage.Smoking;
            if (v.State <= VehicleHealth.Stage.Smoking && f <= 0.2f) Ignite(v);
            if (v.State <= VehicleHealth.Stage.Burning && v.Health <= 0f) StartFuse(v);
            if (v.State != VehicleHealth.Stage.Intact) Track(v);
            if (applied >= 12f && point != Vector3.zero) VfxManager.Instance?.SparksDir(point, Vector3.up, 6, new Color(1f, 0.7f, 0.35f), 5f);
        }

        void Track(VehicleHealth v)
        {
            if (v.Listed) return;
            v.Listed = true;
            v.SmokeT = 0f;
            v.FireT = 0f;
            active.Add(v);
        }

        /// <summary>Stop the car's effects (pooled slots freed); it keeps its stage.</summary>
        internal void Release(VehicleHealth v)
        {
            if (v == null) return;
            v.Listed = false; // pruned from `active` by Update
            for (var i = 0; i < MaxLights; i++) if (lightOwner[i] == v) { lightOwner[i] = null; if (lights[i] != null) lights[i].enabled = false; }
            for (var i = 0; i < MaxVoices; i++) if (voiceOwner[i] == v) { voiceOwner[i] = null; if (voices[i] != null) voices[i].Stop(); }
            v.LightSlot = v.AudioSlot = -1;
        }

        void Ignite(VehicleHealth v)
        {
            v.State = VehicleHealth.Stage.Burning;
            G.Audio?.Play("car_ignite", Hood(v), 0.9f);
            assignT = 0f;
            var pc = Driving.Car;
            if (pc != null && pc.gameObject == v.gameObject) G.Presentation?.Toast(GameData.T("drive.fire"), ToastKind.Warn);
        }

        void StartFuse(VehicleHealth v)
        {
            if (v.State == VehicleHealth.Stage.Fuse) return;
            var pc = Driving.Car;
            var driven = pc != null && pc.gameObject == v.gameObject;
            v.State = VehicleHealth.Stage.Fuse;
            // Chain reactions go off quickly; the player's car gives time to get clear (they are pulled out now).
            v.Fuse = chain ? Random.Range(0.35f, 1.1f) : driven ? 3.2f : Random.Range(2.0f, 2.6f);
            v.FlickT = 0f;
            G.Audio?.Play("car_fuse", Hood(v), 0.8f);
            if (driven) Driving.Eject();
            Track(v);
            assignT = 0f;
        }

        static Vector3 Hood(VehicleHealth v)
        {
            var s = v.Spec;
            return v.transform.TransformPoint(new Vector3(0, s.Size.y * (s.Van ? 0.5f : 0.62f), s.Length * (s.Bike ? 0.1f : 0.32f)));
        }

        // ------------------------------------------------------------------ per frame

        void Update()
        {
            var m = G.Manager;
            if (m == null || m.Mode != GameMode.Play) return;
            var dt = Time.deltaTime;
            if (dt <= 0f) return;
            var frozen = m.InCinematic; // effects keep going, nothing burns down or blows up
            var vfx = VfxManager.Instance;
            for (var i = active.Count - 1; i >= 0; i--)
            {
                var v = active[i];
                if (v == null || !v.Listed || !v.isActiveAndEnabled || v.State == VehicleHealth.Stage.Intact || v.State == VehicleHealth.Stage.Wrecked)
                {
                    if (v != null && v.Listed) Release(v);
                    active.RemoveAt(i);
                    continue;
                }
                var hood = Hood(v);
                var burning = v.State >= VehicleHealth.Stage.Burning;
                v.SmokeT -= dt;
                if (v.SmokeT <= 0f && vfx != null)
                {
                    v.SmokeT = burning ? 0.1f : 0.16f;
                    vfx.SmokePuff(hood + Vector3.up * 0.25f, 1, burning ? DarkSmoke : Smoke, burning ? 1.5f : 0.9f);
                }
                if (burning && vfx != null)
                {
                    // Flames over the engine bay, livelier and bigger on the fuse.
                    v.FireT -= dt;
                    var fuse = v.State == VehicleHealth.Stage.Fuse;
                    var n = 0;
                    while (v.FireT <= 0f && n++ < 4)
                    {
                        v.FireT += fuse ? 0.03f : 0.045f;
                        vfx.Flames(hood, v.Spec.Size.x * 0.6f, fuse ? 1.25f : 0.95f, 1, fuse ? 2.2f : 1.7f);
                        vfx.EmitterTick("fire", hood + v.transform.right * Random.Range(-0.5f, 0.5f) * v.Spec.Size.x * 0.5f, 0f);
                    }
                }
                if (frozen) continue;
                if (v.State == VehicleHealth.Stage.Burning)
                {
                    v.Drain(v.Max * 0.045f * dt);
                    if (v.Health <= 0f) StartFuse(v);
                }
                else if (v.State == VehicleHealth.Stage.Fuse)
                {
                    v.Fuse -= dt;
                    if (v.Fuse <= 0f) Explode(v);
                }
            }
            Slots(dt, frozen);
            Debris(dt);
            Smoulder(dt);
            for (var i = 0; i < MaxBlasts; i++) if (blastT[i] > 0f) blastT[i] -= dt;
        }

        /// <summary>Fire lights and crackle voices to the nearest fires; flicker (a fast warning strobe on a fuse).</summary>
        void Slots(float dt, bool frozen)
        {
            assignT -= dt;
            if (assignT <= 0f)
            {
                assignT = 0.3f;
                var cam = G.Manager.Cam != null && G.Manager.Cam.Cam != null ? G.Manager.Cam.Cam.transform.position : Vector3.zero;
                Assign(lightOwner, MaxLights, cam);
                Assign(voiceOwner, MaxVoices, cam);
            }
            var t = Time.time;
            var bus = Bus01();
            for (var i = 0; i < MaxLights; i++)
            {
                var v = lightOwner[i];
                var l = lights[i];
                if (v == null || !v.Listed) { if (l.enabled) l.enabled = false; lightOwner[i] = null; continue; }
                l.enabled = true;
                l.transform.position = Hood(v) + Vector3.up * 0.9f;
                var flick = 0.75f + 0.25f * Mathf.PerlinNoise(t * 9f, i * 3.1f);
                if (v.State == VehicleHealth.Stage.Fuse)
                {
                    // Warning: hard strobe, faster as the fuse runs out.
                    var rate = Mathf.Lerp(18f, 7f, Mathf.Clamp01(v.Fuse / 2.5f));
                    l.intensity = (Mathf.Repeat(t * rate, 1f) < 0.5f ? 14f : 2f) * flick;
                    l.color = new Color(1f, 0.32f, 0.12f);
                }
                else
                {
                    l.intensity = 10f * flick;
                    l.color = Fire;
                }
            }
            for (var i = 0; i < MaxVoices; i++)
            {
                var v = voiceOwner[i];
                var s = voices[i];
                if (v == null || !v.Listed || s.clip == null || G.Manager.Paused) { if (s.isPlaying) s.Stop(); if (v == null || !v.Listed) voiceOwner[i] = null; continue; }
                s.transform.position = Hood(v);
                s.volume = bus * (v.State == VehicleHealth.Stage.Fuse ? 1f : 0.75f);
                s.pitch = v.State == VehicleHealth.Stage.Fuse ? 1.15f : 1f;
                if (!s.isPlaying) s.Play();
            }
        }

        void Assign(VehicleHealth[] owner, int count, Vector3 cam)
        {
            // Keep owners that still burn; fill free slots with the nearest unassigned fires.
            for (var i = 0; i < count; i++)
                if (owner[i] != null && (!owner[i].Listed || owner[i].State < VehicleHealth.Stage.Burning)) owner[i] = null;
            for (var k = 0; k < count; k++)
            {
                var free = -1;
                for (var i = 0; i < count; i++) if (owner[i] == null) { free = i; break; }
                if (free < 0) return;
                VehicleHealth best = null;
                var bestD = float.MaxValue;
                for (var j = 0; j < active.Count; j++)
                {
                    var v = active[j];
                    if (v == null || !v.Listed || v.State < VehicleHealth.Stage.Burning) continue;
                    var taken = false;
                    for (var i = 0; i < count && !taken; i++) taken = owner[i] == v;
                    if (taken) continue;
                    var d = (v.transform.position - cam).sqrMagnitude;
                    if (d < bestD) { bestD = d; best = v; }
                }
                if (best == null) return;
                owner[free] = best;
            }
        }

        static float Bus01()
        {
            var a = G.Settings?.Data?.Audio;
            if (a == null) return 0.5f;
            return Mathf.Clamp01(a.Master) * Mathf.Clamp01(a.Master) * Mathf.Clamp01(a.Sfx) * Mathf.Clamp01(a.Sfx);
        }

        // ------------------------------------------------------------------ explosion

        /// <summary>Blow the car up now (fuse ran out; tests).</summary>
        public void Explode(VehicleHealth v)
        {
            if (v == null || v.State == VehicleHealth.Stage.Wrecked) return;
            var pc = Driving.Car;
            if (pc != null && pc.gameObject == v.gameObject) Driving.Eject();
            v.State = VehicleHealth.Stage.Wrecked;
            Release(v);
            Explosions++;
            var t = v.transform;
            var ground = t.position;
            var center = t.TransformPoint(v.Spec.BoundsCenter);
            var vfx = VfxManager.Instance;
            if (vfx != null)
            {
                vfx.Explosion(center, 2.3f, Fire);
                vfx.Explosion(center + Vector3.up * 1.2f, 1.3f, new Color(1f, 0.35f, 0.08f));
                vfx.Flames(center + Vector3.up * 0.4f, 2.6f, 3.2f, 34, 4.5f); // the fireball
                vfx.Flames(center, 3.5f, 1.6f, 20, 2.5f);
                vfx.Shockwave(ground + Vector3.up * 0.15f, 9f, new Color(1f, 0.6f, 0.3f), 0.6f);
                vfx.Light(center + Vector3.up, new Color(1f, 0.62f, 0.3f), 9f, 26f, 0.45f);
                vfx.SmokePuff(center + Vector3.up * 0.8f, 10, DarkSmoke, 2.4f);
                vfx.Embers(center, 36, Fire, 1.6f, 4.5f);
            }
            for (var i = 0; i < 8; i++) Launch(center, ground.y);
            G.Audio?.Play("car_explode", center, 1f, Random.Range(0.9f, 1.05f));
            var m = G.Manager;
            var cam = m != null && m.Cam != null && m.Cam.Cam != null ? m.Cam.Cam.transform.position : center;
            var dc = Vector3.Distance(cam, center);
            if (dc < 55f)
            {
                CombatSystem.Shake(Mathf.Lerp(0.75f, 0.08f, dc / 55f)); // the rig scales trauma by the shake settings
                var k = Mathf.Clamp01(1f - dc / 40f);
                if (k > 0f) G.Input?.Rumble(0.5f * k + 0.2f, 0.8f * k, 0.35f, G.Settings.Data.Controls.Vibration);
            }
            blastPos[blastNext] = center;
            blastT[blastNext] = 9f;
            blastNext = (blastNext + 1) % MaxBlasts;

            // Actors: enemies hard, heroes fairly (capped, difficulty scaled; shields absorb first).
            hits.Clear();
            CombatSystem.Ensure().Radial(Team.Neutral, ground, ActorRadius, hits, 4f);
            var diff = G.Settings != null ? G.Settings.Difficulty.EnemyDamage : 1f;
            for (var i = 0; i < hits.Count; i++)
            {
                var h = hits[i];
                var k = Mathf.Clamp01(1f - h.Distance / ActorRadius);
                var hero = h.Target is Hero;
                var dir = h.Target.Position - ground; dir.y = 0;
                dir = dir.sqrMagnitude > 1e-4f ? dir.normalized : Vector3.forward;
                var hit = new HitInfo
                {
                    Damage = hero ? (12f + 30f * k) * diff : 40f + 110f * k,
                    Poise = k > 0.4f ? 45f : 20f,
                    Knock = dir * (6f + 7f * k),
                    Kind = HitKind.Environment,
                    Point = h.Point,
                };
                CombatSystem.Apply(h.Target, hit);
            }
            // Other cars: chain reactions; the player's moving car is shoved.
            chain = true;
            try
            {
                for (var i = 0; i < all.Count; i++)
                {
                    var u = all[i];
                    if (u == null || u == v || !u.Alive) continue;
                    var d = Vector3.Distance(u.transform.position, ground) - u.Radius * 0.5f;
                    if (d >= BlastRadius) continue;
                    // Bumper to bumper: it goes up too; a few metres further: it catches fire or smokes.
                    u.Damage(u.Max * 2.2f * Mathf.Pow(1f - Mathf.Max(0f, d) / BlastRadius, 0.8f), center);
                }
            }
            finally { chain = false; }
            var cars = Driving.Cars;
            for (var i = 0; i < cars.Count; i++)
            {
                var c = cars[i];
                if (c == null || c.Body == null || c.Body.isKinematic || c.gameObject == v.gameObject) continue;
                if ((c.transform.position - center).sqrMagnitude < 14f * 14f) c.Body.AddExplosionForce(c.Body.mass * 9f, center, 14f, 1.2f, ForceMode.Impulse);
            }

            SpawnWreck(v);
            var own = v.GetComponent<PlayerCar>();
            if (own != null) Driving.Forget(own);
            v.gameObject.SetActive(false); // the traffic pool recycles its cars; parked / driven ones stay gone
            Debug.Log($"[vehicles] {v.name} exploded at {ground}; {hits.Count} actors in range");
        }

        void Launch(Vector3 from, float groundY)
        {
            ref var c = ref debris[debrisNext];
            debrisNext = (debrisNext + 1) % MaxDebris;
            var dir = Random.insideUnitSphere;
            dir.y = Mathf.Abs(dir.y) + 0.6f;
            c.V = dir.normalized * Random.Range(6f, 12f);
            c.Spin = Random.insideUnitSphere * 720f;
            c.Life = Random.Range(3.5f, 6f);
            c.Ground = groundY + 0.06f;
            c.T.position = from + Random.insideUnitSphere * 0.5f;
            c.T.localScale = new Vector3(Random.Range(0.12f, 0.45f), Random.Range(0.04f, 0.12f), Random.Range(0.15f, 0.55f));
            c.T.gameObject.SetActive(true);
        }

        void Debris(float dt)
        {
            for (var i = 0; i < MaxDebris; i++)
            {
                ref var c = ref debris[i];
                if (c.Life <= 0f) continue;
                c.Life -= dt;
                if (c.Life <= 0f) { c.T.gameObject.SetActive(false); continue; }
                c.V.y -= 9.81f * dt;
                var p = c.T.position + c.V * dt;
                if (p.y < c.Ground)
                {
                    p.y = c.Ground;
                    c.V = new Vector3(c.V.x * 0.55f, -c.V.y * 0.3f, c.V.z * 0.55f);
                    c.Spin *= 0.5f;
                    if (Mathf.Abs(c.V.y) < 0.6f) c.V.y = 0f;
                }
                c.T.position = p;
                if (c.V.sqrMagnitude > 0.05f) c.T.Rotate(c.Spin * dt, Space.Self);
            }
        }

        // ------------------------------------------------------------------ wrecks

        void SpawnWreck(VehicleHealth v)
        {
            var spec = v.Spec;
            var name = spec.Bike ? "CyberBike" : spec.Van ? "CyberVan_Burnt" : "CyberCar_Sedan_Wrecked";
            if (!CityKitAssets.Has(name)) name = spec.Name; // no kit wreck: the same body, burnt
            var t = v.transform;
            var f = t.forward; f.y = 0;
            var rot = Quaternion.LookRotation(f.sqrMagnitude > 1e-4f ? f.normalized : Vector3.forward);
            if (spec.Bike) rot *= Quaternion.Euler(0, 0, 78f); // on its side
            var pos = new Vector3(t.position.x, t.position.y, t.position.z);
            if (Physics.Raycast(pos + Vector3.up * 2f, Vector3.down, out var hit, 6f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) pos.y = hit.point.y;
            if (spec.Bike) pos += Vector3.up * 0.3f;
            Wreck w = null;
            if (wrecks.Count >= MaxWrecks)
            {
                w = wrecks[wreckNext];
                wreckNext = (wreckNext + 1) % MaxWrecks;
                if (w.Name != name) { if (w.Go != null) Destroy(w.Go); w.Go = null; }
            }
            else { w = new Wreck(); wrecks.Add(w); }
            if (w.Go == null)
            {
                w.Go = EnvProps.Instantiate(name, transform, true);
                w.Go.name = "Wreck_" + name;
                w.Name = name;
                foreach (var c in w.Go.GetComponentsInChildren<Collider>(true)) if (!c.isTrigger) c.gameObject.layer = CombatLayers.World;
            }
            w.Go.SetActive(true);
            w.Go.transform.SetPositionAndRotation(pos, rot);
            w.Half = spec.Length * 0.5f;
            w.HalfW = spec.Size.x * 0.5f;
            w.Smoulder = 16f;
            Burnt(w.Go, name != "CyberVan_Burnt");
            Physics.SyncTransforms();
        }

        /// <summary>Charred look through property blocks (no material copies): dark base, lamps and neon dead.</summary>
        static void Burnt(GameObject go, bool darken)
        {
            go.GetComponentsInChildren(true, rbuf);
            var dark = new Color(0.07f, 0.065f, 0.06f, 1f);
            foreach (var r in rbuf)
            {
                var mats = r.sharedMaterials;
                for (var i = 0; i < mats.Length; i++)
                {
                    mpb.Clear();
                    if (darken) mpb.SetColor(BaseColorId, dark);
                    mpb.SetColor(EmissionId, Color.black);
                    r.SetPropertyBlock(mpb, i);
                }
            }
            rbuf.Clear();
        }

        void Smoulder(float dt)
        {
            var vfx = VfxManager.Instance;
            for (var i = 0; i < wrecks.Count; i++)
            {
                var w = wrecks[i];
                if (w.Go == null || w.Smoulder <= 0f) continue;
                var before = w.Smoulder;
                w.Smoulder -= dt;
                // A puff every quarter second, a few flames for the first seconds.
                if (vfx != null && Mathf.FloorToInt(before * 4f) != Mathf.FloorToInt(w.Smoulder * 4f))
                {
                    var p = w.Go.transform.position + Vector3.up * 1.0f;
                    vfx.SmokePuff(p, 1, DarkSmoke, 1.6f);
                    if (w.Smoulder > 10f) vfx.EmitterTick("fire", p + w.Go.transform.forward * Random.Range(-w.Half, w.Half) * 0.6f, 0f);
                }
            }
        }

        /// <summary>Wrecks in the street (traffic treats them as obstacles): position, forward, half length / width.</summary>
        public int WreckCount => wrecks.Count;

        public bool WreckAt(int i, out Vector3 pos, out Vector3 fwd, out float half, out float halfW)
        {
            var w = wrecks[i];
            pos = fwd = default; half = halfW = 0f;
            if (w.Go == null || !w.Go.activeSelf) return false;
            var t = w.Go.transform;
            pos = t.position; fwd = t.forward; half = w.Half; halfW = w.HalfW;
            return true;
        }

        /// <summary>
        /// Fires and recent blasts pedestrians run from: written into `buf` from `start`; returns how many were added.
        /// </summary>
        public int Hazards(Vector3[] buf, int start)
        {
            var n = 0;
            for (var i = 0; i < MaxBlasts && start + n < buf.Length; i++) if (blastT[i] > 0f) buf[start + n++] = blastPos[i];
            for (var i = 0; i < active.Count && start + n < buf.Length; i++)
            {
                var v = active[i];
                if (v != null && v.Listed && v.State >= VehicleHealth.Stage.Burning) buf[start + n++] = v.transform.position;
            }
            return n;
        }
    }
}
