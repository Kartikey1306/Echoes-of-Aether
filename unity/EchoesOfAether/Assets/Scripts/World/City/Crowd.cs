using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;
using Random = UnityEngine.Random;

namespace EOA
{
    /// <summary>
    /// Pedestrians of the open city: a pool of character prefabs (survivor NPC models with random clothing and hair
    /// tints) walking the sidewalk graph around the player. They cross at zebra crossings on the pedestrian phase of
    /// the signals, step aside for the player and quest NPCs, linger now and then, and flee from fights (react, run
    /// away, then crouch until the fighting stops). Kinematic along the graph: no colliders, no NavMesh agents.
    /// Spawning and despawning happen out of view; the per-frame update allocates nothing.
    /// </summary>
    public sealed class Crowd : MonoBehaviour
    {
        enum State { Walk, Wait, Linger, React, Flee, Cower }

        sealed class Ped
        {
            public GameObject Go;
            public Transform T;
            public Animator Anim;
            public Material[] Cloth, Hair, Boots, Accent;
            public Color[] ClothBase, HairBase, BootsBase, AccentBase;
            public SkinnedMeshRenderer Beard;
            public bool Active, HasActions, CarScare;
            public int Edge, Pending;
            public bool Fwd;
            public float S, Lane, LaneCur, Walk, Speed, Timer, Yaw, Calm, StopAt, Dodge;
            public State St;
            public Vector3 Pos, Threat;
        }

        static readonly int SpeedId = Animator.StringToHash("Speed"), MulId = Animator.StringToHash("MoveSpeedMul"),
            GroundedId = Animator.StringToHash("Grounded"), CombatId = Animator.StringToHash("Combat");
        static readonly int EmptyId = Animator.StringToHash("Empty"), ReactId = Animator.StringToHash("npc_react"),
            CowerId = Animator.StringToHash("kneel_work");
        static readonly int[] IdleIds = { Animator.StringToHash("npc_look"), Animator.StringToHash("npc_crossed"), Animator.StringToHash("npc_hips") };
        static readonly int BaseColor = Shader.PropertyToID("_BaseColor");

        /// <summary>Prefabs tried for pedestrians (echo characters are skipped).</summary>
        public static readonly string[] Models = { "Oren", "Mira", "Tomas", "Nia", "Maren" };

        public const float SpawnMin = 28f, SpawnMax = 85f, DespawnR = 105f, FleeR = 38f, SafeR = 62f;
        const float WalkAnim = 1.9f, RunSpeed = 4.4f, LaneMax = 0.9f;

        PedGraph graph;
        RoadGraph roads;
        readonly List<Ped> peds = new();
        int target;
        int[] near;
        int nearCount;
        float nearTimer, spawnTimer, npcTimer;
        bool filled;
        readonly Vector3[] threats = new Vector3[12];
        int threatCount;
        readonly Vector3[] npcs = new Vector3[12];
        int npcCount;

        public int Pool => peds.Count;
        public int Target => target;
        public int ActiveCount { get; private set; }
        /// <summary>Pedestrians that jumped out of the way of the player's car (telemetry).</summary>
        public static int Dodges { get; private set; }

        // The player's car this frame (pedestrians dodge it; it has no effect on them otherwise).
        bool carOn;
        Vector3 carPos, carVel;
        float carHalfW, carHalfL;

        /// <summary>Copy active pedestrian positions into buf (traffic uses them to stop); returns the count.</summary>
        public int ActivePositions(Vector3[] buf)
        {
            var n = 0;
            for (var i = 0; i < peds.Count && n < buf.Length; i++) if (peds[i].Active) buf[n++] = peds[i].Pos;
            return n;
        }

        /// <summary>Pedestrian budget from the effects quality (smaller on WebGL: CPU skinning).</summary>
        public static int Budget()
        {
            var fx = G.Settings?.Data?.Graphics?.Effects ?? "high";
            var n = fx == "low" ? 10 : fx == "medium" ? 18 : 28;
            if (Application.platform == RuntimePlatform.WebGLPlayer) n = Mathf.Min(n, 14);
            return n;
        }

        // ------------------------------------------------------------------ creation

        public static async Task<Crowd> Create(Transform parent, PedGraph g, RoadGraph r, int count, Func<float, string, Task> progress, List<Vector4> obstacles = null)
        {
            var go = new GameObject("Crowd");
            go.transform.SetParent(parent, false);
            var crowd = go.AddComponent<Crowd>();
            crowd.graph = g;
            crowd.roads = r;
            crowd.near = new int[g.Edges];
            crowd.BindObstacles(obstacles);
            var prefabs = new List<GameObject>();
            foreach (var name in Models)
            {
                var p = Resources.Load<GameObject>("Characters/" + name);
                if (p == null) continue;
                var cm = p.GetComponent<CharacterModel>();
                if (cm != null && cm.Echo) continue; // echoes of the past never walk the living streets
                prefabs.Add(p);
            }
            if (prefabs.Count == 0)
            {
                Debug.LogWarning("[city] no pedestrian character prefabs (Resources/Characters); crowd disabled");
                return crowd;
            }
            var palettes = Palettes();
            for (var i = 0; i < count; i++)
            {
                crowd.peds.Add(crowd.MakePed(prefabs[i % prefabs.Count], go.transform, palettes));
                if (progress != null && i % 6 == 5) await progress(0.95f + 0.02f * i / count, "Crowds");
            }
            crowd.target = count;
            return crowd;
        }

        static Color[][] Palettes()
        {
            static Color[] P(params string[] hex)
            {
                var a = new Color[hex.Length];
                for (var i = 0; i < hex.Length; i++) a[i] = ColorUtility.TryParseHtmlString(hex[i], out var c) ? c : Color.gray;
                return a;
            }
            return new[]
            {
                P("#3a3a42", "#1c1c20", "#26334f", "#5e1c2a", "#4a5236", "#14585c", "#4a2f6a", "#d8d6cc", "#9a7a24", "#ff3c9a", "#20c8e0", "#6a6e78"),
                P("#0f0d0c", "#1d1714", "#4a2e1c", "#8e5a33", "#d1aa6c", "#e8dcc8", "#9a9a9a", "#7a2420", "#ff2bd6", "#00e5ff", "#9b5cff", "#2b3550"),
                P("#141414", "#2a2420", "#3a2f28", "#1e2230"),
                P("#ff2bd6", "#00e5ff", "#ffe14d", "#9b5cff", "#3a3a42", "#7a2420", "#c8c8c8"),
            };
        }

        Ped MakePed(GameObject prefab, Transform parent, Color[][] pal)
        {
            var go = Instantiate(prefab, parent, false);
            go.name = "Ped_" + prefab.name;
            var p = new Ped { Go = go, T = go.transform };
            var cm = go.GetComponent<CharacterModel>();
            p.Anim = cm != null && cm.Animator != null ? cm.Animator : go.GetComponentInChildren<Animator>();
            if (p.Anim != null)
            {
                p.Anim.cullingMode = AnimatorCullingMode.CullUpdateTransforms;
                p.Anim.applyRootMotion = false;
                p.HasActions = p.Anim.layerCount > 1 && p.Anim.HasState(1, EmptyId) && p.Anim.HasState(1, ReactId) && p.Anim.HasState(1, CowerId);
            }
            var cloth = new List<Material>(); var hair = new List<Material>(); var boots = new List<Material>(); var accent = new List<Material>();
            var renderers = cm != null && cm.Renderers.Length > 0 ? cm.Renderers : go.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            foreach (var r in renderers)
            {
                if (r == null) continue;
                if (r.name == "Teeth" || r.name == "Tongue") { r.enabled = false; continue; }
                if (r.name.StartsWith("Facial_")) { p.Beard = r; continue; }
                r.updateWhenOffscreen = false;
                foreach (var m in r.sharedMaterials)
                {
                    if (m == null || !m.HasProperty(BaseColor)) continue;
                    var n = m.name;
                    if (n.StartsWith("Cloth_")) cloth.Add(m);
                    else if (n.StartsWith("Hair_")) hair.Add(m);
                    else if (n.StartsWith("Boots")) boots.Add(m);
                    else if (n.StartsWith("Gear") || n.StartsWith("Strap") || n.StartsWith("Scarf")) accent.Add(m);
                }
            }
            p.Cloth = cloth.ToArray(); p.Hair = hair.ToArray(); p.Boots = boots.ToArray(); p.Accent = accent.ToArray();
            p.ClothBase = Bases(p.Cloth); p.HairBase = Bases(p.Hair); p.BootsBase = Bases(p.Boots); p.AccentBase = Bases(p.Accent);
            // Blinking and expressions are not needed at crowd distance.
            if (cm != null) cm.enabled = false;
            palette = pal;
            go.SetActive(false);
            return p;
        }

        Color[][] palette;
        Vector4[] obstacles = Array.Empty<Vector4>();
        int[][] edgeObstacles;

        /// <summary>Static sidewalk obstacles (shelters, kiosks) indexed by the sidewalk edges they stand beside.</summary>
        void BindObstacles(List<Vector4> list)
        {
            edgeObstacles = new int[graph.Edges][];
            if (list != null) obstacles = list.ToArray();
            var tmp = new List<int>(4);
            for (var e = 0; e < graph.Edges; e++)
            {
                tmp.Clear();
                if (graph.Kind[e] == PedGraph.Sidewalk)
                {
                    var a = graph.Pos[graph.A[e]];
                    for (var i = 0; i < obstacles.Length; i++)
                    {
                        var o = (Vector3)obstacles[i];
                        var rel = o - a; rel.y = 0;
                        var along = Vector3.Dot(rel, graph.Dir[e]);
                        var lat = Vector3.Dot(rel, graph.Side[e]);
                        if (along > -2f && along < graph.Len[e] + 2f && Mathf.Abs(lat) < obstacles[i].w + 1.8f) tmp.Add(i);
                    }
                }
                edgeObstacles[e] = tmp.Count > 0 ? tmp.ToArray() : Array.Empty<int>();
            }
        }

        static Color[] Bases(Material[] mats)
        {
            var a = new Color[mats.Length];
            for (var i = 0; i < mats.Length; i++) a[i] = mats[i].GetColor(BaseColor);
            return a;
        }

        void Tint(Ped p)
        {
            if (palette == null) return;
            var cloth = palette[0][Random.Range(0, palette[0].Length)];
            var cloth2 = palette[0][Random.Range(0, palette[0].Length)];
            var hair = palette[1][Random.Range(0, palette[1].Length)];
            var boots = palette[2][Random.Range(0, palette[2].Length)];
            var accent = palette[3][Random.Range(0, palette[3].Length)];
            for (var i = 0; i < p.Cloth.Length; i++) p.Cloth[i].SetColor(BaseColor, p.ClothBase[i] * Bright(i % 2 == 0 ? cloth : cloth2, 1.35f));
            for (var i = 0; i < p.Hair.Length; i++) p.Hair[i].SetColor(BaseColor, hair);
            for (var i = 0; i < p.Boots.Length; i++) p.Boots[i].SetColor(BaseColor, p.BootsBase[i] * Bright(boots, 1.6f));
            for (var i = 0; i < p.Accent.Length; i++) p.Accent[i].SetColor(BaseColor, p.AccentBase[i] * Bright(accent, 1.2f));
            if (p.Beard != null) p.Beard.gameObject.SetActive(Random.value < 0.4f);
            var s = Random.Range(0.94f, 1.06f);
            p.T.localScale = new Vector3(s, s, s);
            p.Walk = Random.Range(1.15f, 1.6f);
            p.StopAt = Random.Range(0.4f, 2.0f);
        }

        static Color Bright(Color c, float k)
        {
            var o = c * k;
            o.r = Mathf.Min(o.r, 1); o.g = Mathf.Min(o.g, 1); o.b = Mathf.Min(o.b, 1); o.a = 1;
            return o;
        }

        // ------------------------------------------------------------------ helpers

        static Vector3? PlayerPos()
        {
            var m = G.Manager;
            var p = m != null ? m.Player : null;
            return p != null ? p.Position : null;
        }

        static Camera Cam()
        {
            var rig = G.Manager != null ? G.Manager.Cam : null;
            return rig != null && rig.Cam != null ? rig.Cam : Camera.main;
        }

        static bool InView(Camera cam, Vector3 p)
        {
            if (cam == null) return false;
            var v = cam.WorldToViewportPoint(p + Vector3.up);
            return v.z > 0 && v.x > -0.15f && v.x < 1.15f && v.y > -0.2f && v.y < 1.2f;
        }

        int From(Ped p) => p.Fwd ? graph.A[p.Edge] : graph.B[p.Edge];
        int To(Ped p) => p.Fwd ? graph.B[p.Edge] : graph.A[p.Edge];
        Vector3 Dir(Ped p) => p.Fwd ? graph.Dir[p.Edge] : -graph.Dir[p.Edge];

        float Height(Ped p)
        {
            if (graph.Kind[p.Edge] != PedGraph.Crossing) return CityLayout.Curb;
            var d = Mathf.Min(p.S, graph.Len[p.Edge] - p.S);
            return d <= 2f ? CityLayout.Curb : d >= 2.5f ? 0f : CityLayout.Curb * (2.5f - d) / 0.5f;
        }

        void Act(Ped p, int hash, float fade)
        {
            if (p.HasActions && p.Anim != null && p.Anim.isActiveAndEnabled) p.Anim.CrossFadeInFixedTime(hash, fade, 1, 0f);
        }

        // ------------------------------------------------------------------ spawning

        void RefreshNear(Vector3 player)
        {
            nearCount = 0;
            for (var e = 0; e < graph.Edges; e++)
            {
                if (graph.Kind[e] != PedGraph.Sidewalk) continue;
                var a = graph.Pos[graph.A[e]]; var b = graph.Pos[graph.B[e]];
                // Distance from the player to the segment (XZ).
                var ab = b - a; ab.y = 0;
                var ap = player - a; ap.y = 0;
                var t = Mathf.Clamp01(Vector3.Dot(ap, ab) / Mathf.Max(0.01f, ab.sqrMagnitude));
                var c = a + ab * t; c.y = player.y;
                if ((c - player).sqrMagnitude < SpawnMax * SpawnMax) near[nearCount++] = e;
            }
        }

        bool TrySpawn(Ped p, Vector3 player, Camera cam, bool initial)
        {
            if (nearCount == 0) return false;
            for (var tries = 0; tries < 10; tries++)
            {
                var e = near[Random.Range(0, nearCount)];
                var s = Random.value * graph.Len[e];
                var pos = graph.Pos[graph.A[e]] + graph.Dir[e] * s;
                var d = Vector3.Distance(new Vector3(pos.x, player.y, pos.z), player);
                if (d < (initial ? 12f : SpawnMin) || d > SpawnMax) continue;
                if (!initial && InView(cam, pos) && d < 70f) continue;
                p.Edge = e;
                p.Fwd = Random.value < 0.5f;
                p.S = p.Fwd ? s : graph.Len[e] - s;
                p.Lane = Random.Range(-LaneMax, LaneMax);
                p.LaneCur = p.Lane;
                p.Pending = -1;
                p.St = State.Walk;
                p.Speed = 0;
                p.Timer = 0;
                p.Calm = 0;
                p.Dodge = 0;
                p.CarScare = false;
                Tint(p);
                p.Active = true;
                p.Go.SetActive(true);
                var dir = Dir(p);
                p.Yaw = Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg;
                Place(p, 0);
                if (p.Anim != null)
                {
                    p.Anim.SetBool(GroundedId, true);
                    p.Anim.SetBool(CombatId, false);
                    p.Anim.SetFloat(MulId, 1f);
                    p.Anim.SetFloat(SpeedId, WalkAnim);
                }
                return true;
            }
            return false;
        }

        void Despawn(Ped p)
        {
            p.Active = false;
            p.Go.SetActive(false);
        }

        // ------------------------------------------------------------------ update

        void Update()
        {
            var m = G.Manager;
            if (graph == null || peds.Count == 0 || m == null || m.Mode != GameMode.Play || m.Paused) return;
            var pp = PlayerPos();
            if (!pp.HasValue) return;
            var player = pp.Value;
            var dt = Mathf.Min(Time.deltaTime, 0.1f);
            var cam = Cam();
            var t = Time.time;

            nearTimer -= dt;
            if (nearTimer <= 0) { nearTimer = 1f; RefreshNear(player); }
            npcTimer -= dt;
            if (npcTimer <= 0) { npcTimer = 1f; CacheNpcs(); }
            Threats(player, m.InCombat);
            var pc = Driving.Car;
            carOn = pc != null && pc.Body != null && !pc.Body.isKinematic;
            if (carOn)
            {
                carPos = pc.transform.position;
                carVel = pc.Body.linearVelocity;
                carHalfW = pc.Spec.Size.x * 0.5f;
                carHalfL = pc.Spec.Length * 0.5f;
            }

            // Despawn far pedestrians, spawn missing ones (a few per tick, out of view after the first fill).
            spawnTimer -= dt;
            var active = 0;
            for (var i = 0; i < peds.Count; i++)
            {
                var p = peds[i];
                if (!p.Active) continue;
                var dx = p.Pos.x - player.x; var dz = p.Pos.z - player.z;
                if (dx * dx + dz * dz > DespawnR * DespawnR) { Despawn(p); continue; }
                active++;
            }
            if (spawnTimer <= 0)
            {
                spawnTimer = filled ? 0.25f : 0f;
                var budget = filled ? 2 : target;
                for (var i = 0; i < peds.Count && active < target && budget > 0; i++)
                {
                    if (peds[i].Active) continue;
                    if (TrySpawn(peds[i], player, cam, !filled)) { active++; budget--; }
                    else break;
                }
                filled = true;
            }
            ActiveCount = active;

            for (var i = 0; i < peds.Count; i++)
            {
                var p = peds[i];
                if (p.Active) Step(p, player, dt, t);
            }
        }

        void CacheNpcs()
        {
            npcCount = 0;
            var rt = G.Manager != null ? G.Manager.World : null;
            if (rt == null) return;
            var list = rt.Npcs;
            for (var i = 0; i < list.Count && npcCount < npcs.Length; i++)
                if (list[i] != null) npcs[npcCount++] = list[i].Position;
        }

        void Threats(Vector3 player, bool inCombat)
        {
            threatCount = 0;
            var all = Enemy.All;
            for (var i = 0; i < all.Count && threatCount < threats.Length - 1; i++)
            {
                var e = all[i];
                if (e != null && e.Alive && e.Aggro) threats[threatCount++] = e.Position;
            }
            if (inCombat) threats[threatCount++] = player;
            // Burning cars and fresh explosions.
            var vd = VehicleDamage.Instance;
            if (vd != null) threatCount += vd.Hazards(threats, threatCount);
        }

        float NearestThreat(Vector3 p, out Vector3 at)
        {
            var best = float.MaxValue;
            at = p;
            for (var i = 0; i < threatCount; i++)
            {
                var dx = threats[i].x - p.x; var dz = threats[i].z - p.z;
                var d = dx * dx + dz * dz;
                if (d < best) { best = d; at = threats[i]; }
            }
            return threatCount > 0 ? Mathf.Sqrt(best) : float.MaxValue;
        }

        /// <summary>
        /// The player's car heading their way (closest approach within ~1.6 s, or already alongside): pedestrians jump
        /// to the side of the sidewalk away from its path with a startled reaction, then walk on. Nobody is ever hurt.
        /// </summary>
        void CarDanger(Ped p)
        {
            var rel = p.Pos - carPos; rel.y = 0;
            var d2 = rel.sqrMagnitude;
            if (d2 > 40f * 40f) return;
            var v = carVel; v.y = 0;
            var sp2 = v.sqrMagnitude;
            var tca = sp2 > 0.25f ? Mathf.Clamp(Vector3.Dot(rel, v) / sp2, 0f, 1.6f) : 0f;
            var miss = rel - v * tca; miss.y = 0;
            var close = d2 < (carHalfL + 1.2f) * (carHalfL + 1.2f);
            if (miss.magnitude > carHalfW + 1.4f || (sp2 < 4f && !close) || (sp2 < 0.25f)) return;
            var dir = Dir(p);
            var side = Vector3.Cross(Vector3.up, dir);
            var away = miss.sqrMagnitude > 0.04f ? miss : (Vector3.Dot(rel, side) >= 0 ? side : -side);
            var sgn = Vector3.Dot(away, side) >= 0 ? 1f : -1f;
            p.Lane = sgn * 2.0f;
            if (p.Dodge <= 0f) Dodges++;
            p.Dodge = 0.9f;
            if (p.St == State.Walk || p.St == State.Wait || p.St == State.Linger)
            {
                p.Threat = carPos;
                p.St = State.React;
                p.CarScare = true;
                p.Timer = 0.7f;
                p.Pending = -1;
                Act(p, ReactId, 0.08f);
            }
        }

        void Step(Ped p, Vector3 player, float dt, float t)
        {
            if (carOn) CarDanger(p);
            if (p.Dodge > 0f) p.Dodge -= dt;
            var threatD = NearestThreat(p.Pos, out var threat);
            switch (p.St)
            {
                case State.Walk:
                case State.Wait:
                case State.Linger:
                    if (threatD < FleeR)
                    {
                        p.Threat = threat;
                        p.St = State.React;
                        p.Timer = 0.7f;
                        p.Pending = -1;
                        Act(p, ReactId, 0.1f);
                        // Turn around if walking toward the fight.
                        if (Vector3.Dot(Dir(p), threat - p.Pos) > 0) { p.Fwd = !p.Fwd; p.S = graph.Len[p.Edge] - p.S; }
                    }
                    break;
                case State.Flee:
                    if (threatD < SafeR) p.Threat = threat;
                    else { p.St = State.Cower; p.Timer = 0; p.Calm = 0; Act(p, CowerId, 0.35f); }
                    break;
                case State.Cower:
                    if (threatD < FleeR * 0.7f) { p.Threat = threat; p.St = State.Flee; Act(p, EmptyId, 0.2f); }
                    else if (threatD > SafeR + 8) { p.Calm += dt; if (p.Calm > 3f) { p.St = State.Walk; Act(p, EmptyId, 0.5f); } }
                    else p.Calm = 0;
                    break;
            }

            var want = 0f;
            switch (p.St)
            {
                case State.Walk: want = p.Walk * (graph.Kind[p.Edge] == PedGraph.Crossing ? 1.2f : 1f); break;
                case State.Flee: want = RunSpeed; break;
                case State.React:
                    p.Timer -= dt;
                    if (p.Timer <= 0)
                    {
                        // A car that missed them: back to walking (a fight: run).
                        if (p.CarScare && threatD > FleeR) { p.St = State.Walk; Act(p, EmptyId, 0.3f); }
                        else p.St = State.Flee;
                        p.CarScare = false;
                    }
                    break;
                case State.Wait:
                    // Green for pedestrians: walk the last metre to the kerb and straight onto the crossing.
                    if (p.Pending < 0 || roads.PedStart(graph.SignalNode[p.Pending], graph.SignalAxis[p.Pending], t)) p.St = State.Walk;
                    break;
                case State.Linger:
                    p.Timer -= dt;
                    if (p.Timer <= 0) { p.St = State.Walk; Act(p, EmptyId, 0.4f); }
                    break;
            }

            // Step aside for the player and quest NPCs; stop if someone is right in front.
            var dir = Dir(p);
            var side = Vector3.Cross(Vector3.up, dir);
            if (p.St == State.Walk)
            {
                Avoid(p, player, dir, side, ref want, 1.3f);
                for (var i = 0; i < npcCount; i++) Avoid(p, npcs[i], dir, side, ref want, 1.6f);
                var obs = edgeObstacles != null ? edgeObstacles[p.Edge] : null;
                if (obs != null) for (var i = 0; i < obs.Length; i++) Avoid(p, obstacles[obs[i]], dir, side, ref want, obstacles[obs[i]].w + 0.35f, false);
            }
            p.Speed = Mathf.MoveTowards(p.Speed, want, (want > p.Speed ? 3f : 6f) * dt);
            p.LaneCur = Mathf.MoveTowards(p.LaneCur, p.Lane, (p.Dodge > 0f ? 5.5f : 1.2f) * dt);
            p.S += p.Speed * dt;

            // Plan the next edge shortly before the node; a red crossing is waited for short of the kerb (spread out).
            var len = graph.Len[p.Edge];
            if (p.Pending < 0 && p.S >= len - p.StopAt && (p.St == State.Walk || p.St == State.Flee))
            {
                p.Pending = Choose(p, To(p));
                if (p.St == State.Walk && p.Pending >= 0 && graph.Kind[p.Pending] == PedGraph.Crossing &&
                    !roads.PedStart(graph.SignalNode[p.Pending], graph.SignalAxis[p.Pending], t))
                {
                    p.St = State.Wait;
                    p.Speed = 0;
                }
            }
            if (p.S >= len)
            {
                var node = To(p);
                var next = p.Pending >= 0 ? p.Pending : Choose(p, node);
                if (next < 0) { p.S = len; }
                else if (p.St == State.Walk && graph.Kind[next] == PedGraph.Sidewalk && Random.value < 0.04f)
                {
                    p.S = len;
                    p.St = State.Linger;
                    p.Timer = Random.Range(4f, 9f);
                    p.Speed = 0;
                    Act(p, IdleIds[Random.Range(0, IdleIds.Length)], 0.4f);
                }
                else Enter(p, next, node, p.S - len);
            }
            Place(p, dt);
        }

        void Avoid(Ped p, Vector3 other, Vector3 dir, Vector3 side, ref float want, float radius, bool slow = true)
        {
            var rel = other - p.Pos; rel.y = 0;
            var along = Vector3.Dot(rel, dir);
            if (along < -0.5f || along > 3.2f) return;
            var lat = Vector3.Dot(rel, side);
            var mine = p.LaneCur * Taper(p);
            var gap = lat - mine;
            if (Mathf.Abs(gap) > radius) return;
            // Shift the walking lane away from them and slow down; stop when they are right in front.
            p.Lane = Mathf.Clamp(gap > 0 ? lat - radius : lat + radius, -1.7f, 1.7f);
            if (!slow) return;
            if (along > 0 && along < 1.1f && Mathf.Abs(gap) < 0.55f) want = 0;
            else want *= 0.6f;
        }

        void Enter(Ped p, int edge, int fromNode, float carry = 0)
        {
            p.Fwd = graph.A[edge] == fromNode;
            p.Edge = edge;
            p.S = Mathf.Max(0, carry);
            p.Pending = -1;
            if (p.St == State.Wait) p.St = State.Walk;
            if (p.St == State.Walk && Random.value < 0.3f) p.Lane = Random.Range(-LaneMax, LaneMax);
        }

        /// <summary>Next edge at a node: random (no U-turn) when calm, away from the threat when fleeing.</summary>
        int Choose(Ped p, int node)
        {
            var adj = graph.Adj[node];
            if (adj.Length == 0) return -1;
            if (p.St == State.Flee || p.St == State.React)
            {
                var best = -1; var bestD = float.MinValue;
                for (var i = 0; i < adj.Length; i++)
                {
                    var o = graph.Pos[graph.Other(adj[i], node)];
                    var d = (o - p.Threat).sqrMagnitude + (adj[i] == p.Edge ? -400f : 0);
                    if (d > bestD) { bestD = d; best = adj[i]; }
                }
                return best;
            }
            var count = 0;
            for (var i = 0; i < adj.Length; i++) if (adj[i] != p.Edge) count++;
            if (count == 0) return adj[0];
            // Prefer staying on the sidewalk a little more than crossing.
            for (var attempt = 0; attempt < 3; attempt++)
            {
                var k = Random.Range(0, count);
                for (var i = 0; i < adj.Length; i++)
                {
                    if (adj[i] == p.Edge) continue;
                    if (k-- != 0) continue;
                    if (graph.Kind[adj[i]] == PedGraph.Crossing && attempt < 2 && Random.value < 0.35f) break;
                    return adj[i];
                }
            }
            for (var i = 0; i < adj.Length; i++) if (adj[i] != p.Edge) return adj[i];
            return adj[0];
        }

        float Taper(Ped p)
        {
            var d = Mathf.Min(p.S, graph.Len[p.Edge] - p.S);
            return Mathf.Clamp01(d / 2.5f);
        }

        void Place(Ped p, float dt)
        {
            var dir = Dir(p);
            var side = Vector3.Cross(Vector3.up, dir);
            var from = graph.Pos[From(p)];
            var pos = from + dir * p.S + side * (p.LaneCur * (p.Dodge > 0f ? Mathf.Max(Taper(p), 0.6f) : Taper(p)));
            pos.y = Height(p);
            var moved = pos - p.Pos; moved.y = 0;
            p.Pos = pos;
            Vector3 face;
            if (p.St == State.Cower || p.St == State.React) face = p.Threat - pos;
            else if (moved.sqrMagnitude > 1e-6f && dt > 0) face = moved;
            else face = dir;
            face.y = 0;
            if (p.St == State.Cower) face = -face; // crouch facing away from the fight
            if (face.sqrMagnitude > 1e-6f)
            {
                var yaw = Mathf.Atan2(face.x, face.z) * Mathf.Rad2Deg;
                p.Yaw = dt > 0 ? Mathf.LerpAngle(p.Yaw, yaw, 1 - Mathf.Exp(-8f * dt)) : yaw;
            }
            p.T.SetPositionAndRotation(pos, Quaternion.Euler(0, p.Yaw, 0));
            var a = p.Anim;
            if (a == null || !a.isActiveAndEnabled || dt <= 0) return;
            float animSpeed, mul;
            if (p.Speed < 0.05f) { animSpeed = 0; mul = 1; }
            else if (p.Speed <= WalkAnim) { animSpeed = WalkAnim; mul = Mathf.Clamp(p.Speed / WalkAnim, 0.45f, 1.2f); }
            else { animSpeed = p.Speed; mul = 1; }
            a.SetFloat(SpeedId, animSpeed, 0.15f, dt);
            a.SetFloat(MulId, mul);
        }
    }
}
