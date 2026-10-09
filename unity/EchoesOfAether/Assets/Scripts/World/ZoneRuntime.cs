using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.AI;
using Unity.AI.Navigation;

namespace EOA
{
    /// <summary>
    /// Live state of the loaded zone (port of the prototype's World.ts): additive zone scene, NPCs, pickups,
    /// encounters and waves, triggers, exits, interaction candidate, Echo Sight reveals and attack tokens.
    /// Implements <see cref="IWorld"/> for actors.
    /// </summary>
    public sealed class ZoneRuntime : IWorld
    {
        sealed class LiveInteractable
        {
            public ZoneInteractable Def;
            public bool Consumed;
            public Func<bool> Available;
            public Func<string> Prompt;
            public Func<string> Locked;
            public Action OnUse;
            public Vector3 Position => Def.Position;
        }

        sealed class ActiveEncounter
        {
            public ZoneEncounter Def;
            public int Wave;
            public readonly List<Enemy> Enemies = new();
        }

        public string ZoneId { get; private set; }
        public ZoneDefinition Def { get; private set; }
        public ZoneScript Script { get; private set; }
        public Transform Root { get; private set; }
        public Scene Scene { get; private set; }
        public bool Loading { get; private set; }
        public readonly List<Npc> Npcs = new();
        public readonly List<Pickup> Pickups = new();
        readonly List<LiveInteractable> interactables = new();
        readonly Dictionary<string, ActiveEncounter> encounters = new();
        readonly HashSet<string> insideTriggers = new(), firedTriggers = new();
        readonly HashSet<UnityEngine.Object> tokens = new();
        float echoT, echoRange, exitCooldown;
        Vector3 echoCenter;
        public int MaxTokens = 2;
        public string Candidate { get; private set; }
        public string CandidatePrompt { get; private set; }
        public string CandidateLocked { get; private set; }
        public Vector3? CandidatePosition { get; private set; }
        ZoneMapData map;

        public bool EchoActive => echoT > 0;
        public float EchoRemaining => echoT;
        /// <summary>Living enemies (rebuilt at most once per frame into a reused list; iterate with an index).</summary>
        public IReadOnlyList<IDamageable> Enemies
        {
            get
            {
                if (enemiesFrame == Time.frameCount) return enemiesBuf;
                enemiesFrame = Time.frameCount;
                enemiesBuf.Clear();
                var all = Enemy.All;
                for (var i = 0; i < all.Count; i++) if (all[i] != null && all[i].Alive) enemiesBuf.Add(all[i]);
                return enemiesBuf;
            }
        }
        readonly List<IDamageable> enemiesBuf = new();
        int enemiesFrame = -1;
        public float KillY => Def != null ? Def.KillY : -50;

        // ------------------------------------------------------------------ loading

        public async Task Load(string zoneId, Action<float, string> progress)
        {
            Loading = true;
            LoadTrace.Begin();
            var report = progress;
            progress = (f, label) => { LoadTrace.Mark(label); report(f, label); };
            try
            {
                LoadTrace.Mark("Unload previous zone");
                Unload();
                ZoneId = zoneId;
                progress(0.05f, "Loading zone");
                var sceneName = "Zone_" + zoneId;
                if (Application.CanStreamedLevelBeLoaded(sceneName))
                {
                    var op = SceneManager.LoadSceneAsync(sceneName, LoadSceneMode.Additive);
                    while (!op.isDone)
                    {
                        progress(0.05f + op.progress * 0.6f, "Loading zone");
                        await Awaitable.NextFrameAsync();
                    }
                    Scene = SceneManager.GetSceneByName(sceneName);
                    SceneManager.SetActiveScene(Scene);
                    foreach (var go in Scene.GetRootGameObjects())
                    {
                        Def ??= go.GetComponentInChildren<ZoneDefinition>(true);
                        Script ??= go.GetComponentInChildren<ZoneScript>(true);
                    }
                    Root = Def != null ? Def.transform : Scene.GetRootGameObjects().FirstOrDefault()?.transform;
                }
                if (Def == null && ZoneRegistry.Has(zoneId))
                {
                    // Procedural environment generated in C# (the normal path; scenes are optional overrides).
                    var go = new GameObject("Zone_" + zoneId);
                    Def = go.AddComponent<ZoneDefinition>();
                    Def.ZoneId = zoneId;
                    var pz = ZoneRegistry.Create(zoneId, go);
                    Script = pz;
                    Root = go.transform;
                    Scene = go.scene;
                    pz.Bind(this);
                    await pz.Build(Def, async (f, label) =>
                    {
                        progress(0.05f + Mathf.Clamp01(f) * 0.55f, label);
                        await Awaitable.NextFrameAsync();
                    });
                    progress(0.62f, "Mapping paths");
                    await Awaitable.NextFrameAsync();
                    BuildNavMesh(go);
                }
                if (Def == null)
                {
                    Debug.LogWarning($"[world] scene {sceneName} missing or has no ZoneDefinition; using a fallback test zone");
                    BuildFallback(zoneId);
                }
                var gs = G.State;
                progress(0.7f, "Placing survivors");
                foreach (var n in Def.Npcs)
                {
                    var npc = Npc.Spawn(n, Root);
                    if (n.Id == "bolt") { npc.BoltActive = gs.Flag("bolt_repaired"); npc.ApplyBehaviour(); }
                    Npcs.Add(npc);
                    var place = n;
                    var npcRef = npc;
                    Register(new ZoneInteractable { Id = "npc_" + n.Id, Kind = "npc", Position = n.Position + Vector3.up * 1.2f, Radius = 2.4f, Report = false },
                        () => (n.Id == "bolt" || !place.EchoOnly || EchoActive) && gs.CheckAll(place.Conditions) && (place.Available == null || place.Available()),
                        () => $"Talk to {(GameData.Speakers.TryGetValue(place.Id, out var s) ? s.Name : place.Id)}",
                        () => G.Manager.TalkTo(npcRef));
                }
                progress(0.78f, "Placing collectibles");
                foreach (var c in Def.Collectibles)
                {
                    if (!GameData.Collectibles.TryGetValue(c.Id, out var cd)) { Debug.LogError($"[world] unknown collectible {c.Id}"); continue; }
                    if (gs.IsCollected(c.Id)) continue;
                    var kind = cd.Kind == "fragment" ? PickupKind.Fragment : cd.Kind == "recording" ? PickupKind.Recording : PickupKind.Cache;
                    AddPickup(c.Id, kind, c.Position, auto: cd.Kind != "cache", hidden: cd.Hidden && !gs.IsRevealed(c.Id));
                }
                foreach (var p in Def.ItemPickups)
                    if (!gs.IsCollected(p.Id)) AddPickup(p.Id, PickupKind.Quest, p.Position, item: p.Item, auto: false, cond: p.Conditions, prompt: p.Prompt);
                foreach (var i in Def.Interactables) RegisterDef(i);
                progress(0.84f, "Waking enemies");
                foreach (var e in Def.Encounters)
                {
                    if (gs.IsDefeated(e.Id) && !e.Respawn) continue;
                    if (e.Spawn == "auto" || (e.Spawn == "quest" && gs.Flag("enc_" + e.Id))) SpawnEncounter(e.Id);
                }
                map = BuildMap();
                Script?.Bind(this);
                Script?.OnLoaded();
                progress(0.9f, "Finalising");
            }
            finally { Loading = false; }
        }

        /// <summary>Bake a NavMesh for enemies from the zone's static colliders (world + invisible blockers).</summary>
        static void BuildNavMesh(GameObject root)
        {
            try
            {
                var surface = root.GetComponent<NavMeshSurface>() ?? root.AddComponent<NavMeshSurface>();
                surface.collectObjects = CollectObjects.Children;
                surface.useGeometry = NavMeshCollectGeometry.PhysicsColliders;
                surface.layerMask = (1 << CombatLayers.World) | (1 << CombatLayers.Default) | (1 << CombatLayers.IgnoreCamera);
                surface.BuildNavMesh();
            }
            catch (Exception e) { Debug.LogWarning("[world] NavMesh bake failed, enemies will steer without it: " + e.Message); }
        }

        /// <summary>
        /// Re-bake the zone NavMesh in the background after the level changed (door opened, barrier removed) so
        /// enemies can path through new openings. Cheap enough to call on discrete events, not every frame.
        /// </summary>
        public void RefreshNavMesh()
        {
            var surface = Root != null ? Root.GetComponent<NavMeshSurface>() : null;
            if (surface == null || surface.navMeshData == null) return;
            try { surface.UpdateNavMesh(surface.navMeshData); }
            catch (Exception e) { Debug.LogWarning("[world] NavMesh refresh failed: " + e.Message); }
        }

        /// <summary>Live interactable with code callbacks (procedural zones; replaces any with the same id).</summary>
        public void AddInteractable(ZoneInteractable def, Func<bool> available, Func<string> prompt, Action use, Func<string> locked = null)
        {
            if (def.OneShot && G.State.IsCollected(def.Id)) return;
            if (def.Hidden && G.State.IsRevealed(def.Id)) ApplyReveal(def, false);
            Register(def, available, prompt, () =>
            {
                if (def.OneShot) { G.State.MarkCollected(def.Id); SetConsumed(def.Id); }
                use?.Invoke();
            }, locked);
        }

        void BuildFallback(string zoneId)
        {
            var go = new GameObject("Zone_" + zoneId + "_Fallback");
            Def = go.AddComponent<ZoneDefinition>();
            Def.ZoneId = zoneId;
            Def.Spawns.Add(new ZoneSpawn { Name = "start", Position = new Vector3(0, 0.05f, 0) });
            var ground = GameObject.CreatePrimitive(PrimitiveType.Plane);
            ground.transform.SetParent(go.transform, false);
            ground.transform.localScale = new Vector3(12, 1, 12);
            ground.layer = CombatLayers.World;
            var sun = new GameObject("Sun").AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.transform.SetParent(go.transform, false);
            sun.transform.rotation = Quaternion.Euler(50, -30, 0);
            Root = go.transform;
            Scene = go.scene;
        }

        public void Unload()
        {
            foreach (var enc in encounters.Values) foreach (var e in enc.Enemies) if (e != null) e.Despawn();
            encounters.Clear();
            foreach (var e in Enemy.All.ToList()) if (e != null) e.Despawn();
            tokens.Clear();
            foreach (var n in Npcs) if (n != null) UnityEngine.Object.Destroy(n.gameObject);
            Npcs.Clear();
            foreach (var p in Pickups) if (p != null) UnityEngine.Object.Destroy(p.gameObject);
            Pickups.Clear();
            interactables.Clear();
            insideTriggers.Clear(); firedTriggers.Clear();
            VfxManager.Instance?.Clear();
            CombatSystem.Instance?.ClearProjectiles();
            if (Scene.IsValid() && Scene.isLoaded && Scene.name.StartsWith("Zone_")) SceneManager.UnloadSceneAsync(Scene);
            else if (Root != null) UnityEngine.Object.Destroy(Root.gameObject);
            Def = null; Script = null; Root = null; Scene = default;
            echoT = 0;
            Candidate = null;
            map = null;
        }

        // ------------------------------------------------------------------ interactables

        void Register(ZoneInteractable def, Func<bool> available, Func<string> prompt, Action use, Func<string> locked = null)
        {
            interactables.RemoveAll(x => x.Def.Id == def.Id);
            interactables.Add(new LiveInteractable { Def = def, Available = available, Prompt = prompt, OnUse = use, Locked = locked });
        }

        void RegisterDef(ZoneInteractable i)
        {
            var gs = G.State;
            if (i.OneShot && gs.IsCollected(i.Id)) return;
            if (i.Hidden && gs.IsRevealed(i.Id)) ApplyReveal(i, false);
            Register(i,
                () => gs.CheckAll(i.Conditions) && (Script == null || Script.IsAvailable(i.Id)),
                () => Script?.PromptFor(i.Id) ?? i.Prompt ?? "Inspect",
                () =>
                {
                    if (i.Kind == "save") { G.Manager.OpenSaveTerminal(); return; }
                    if (Script != null && Script.OnInteract(i.Id)) return;
                    if (i.OneShot) { gs.MarkCollected(i.Id); var li = interactables.Find(x => x.Def.Id == i.Id); if (li != null) li.Consumed = true; }
                    if (i.Report) Bus.Emit(new Interacted { Id = i.Id, Kind = i.Kind });
                },
                () => string.IsNullOrEmpty(i.LockedReason) ? null : i.LockedReason);
        }

        /// <summary>Quest point that reports Interacted while conditions hold (zone scripts can add their own).</summary>
        public void QuestPoint(string id, Vector3 pos, string prompt, string[] cond, float radius = 2.2f) =>
            RegisterDef(new ZoneInteractable { Id = id, Position = pos, Prompt = prompt, Conditions = cond ?? Array.Empty<string>(), Radius = radius });

        public void SetConsumed(string id, bool consumed = true)
        {
            var li = interactables.Find(x => x.Def.Id == id);
            if (li != null) li.Consumed = consumed;
        }

        // ------------------------------------------------------------------ pickups

        public Pickup AddPickup(string id, PickupKind kind, Vector3 pos, string item = null, string powerup = null, bool auto = true, bool hidden = false, bool persist = true, string[] cond = null, string prompt = null)
        {
            if (Root == null) return null;
            var p = Pickup.Create(Root, id, kind, pos, item, powerup, auto, hidden, persist, cond);
            Pickups.Add(p);
            if (!auto)
            {
                var label = prompt ?? (kind == PickupKind.Cache ? "Open hidden cache" : item != null ? $"Take {(GameData.Items.TryGetValue(item, out var d) ? d.Name : item)}" : "Pick up");
                Register(new ZoneInteractable { Id = id, Kind = kind == PickupKind.Cache ? "cache" : "pickup", Position = pos, Radius = 2, Hidden = hidden, Report = false },
                    () => !p.Collected && G.State.CheckAll(cond), () => label, () => Collect(p));
            }
            return p;
        }

        public bool HasPickup(string id) => Pickups.Any(p => p.Id == id && !p.Collected);

        public void Collect(Pickup p)
        {
            if (p.Collected) return;
            if (p.Persist) G.State.MarkCollected(p.Id);
            SetConsumed(p.Id);
            p.MarkCollected();
            VfxManager.Instance?.FlashSprite(p.Position, 1.6f, p.Color, 0.2f);
            VfxManager.Instance?.Embers(p.Position, 18, p.Color, 0.4f, 2.2f);
            VfxManager.Instance?.Shockwave(p.Position - Vector3.up * 0.5f, 1.6f, p.Color, 0.4f);
            G.Manager.OnPickup(p);
            Bus.Emit(new PickedUp { Id = p.Id });
        }

        // ------------------------------------------------------------------ encounters

        public void SpawnEncounter(string id)
        {
            if (Def == null) return;
            var def = Def.Encounters.Find(e => e.Id == id);
            if (def == null) { Debug.LogWarning($"[world] encounter {id} not in zone {ZoneId}"); return; }
            if (encounters.ContainsKey(id)) return;
            if (G.State.IsDefeated(id) && !def.Respawn) return;
            var enc = new ActiveEncounter { Def = def };
            encounters[id] = enc;
            SpawnWave(enc);
            Bus.Emit(new EncounterStarted { Id = id });
        }

        void SpawnWave(ActiveEncounter enc)
        {
            if (enc.Wave >= enc.Def.Waves.Count) return;
            foreach (var pl in enc.Def.Waves[enc.Wave].Enemies)
            {
                if (!EnemyFactory.IsKnown(pl.Type)) { Debug.LogError($"[world] no enemy type {pl.Type}"); continue; }
                var e = EnemyFactory.Create(pl.Type, pl.Position, pl.YawDeg, Root, enc.Def.Id, enc.Wave > 0 || enc.Def.Spawn == "quest");
                if (e == null) continue;
                if (enc.Def.ArenaRadius > 0) e.SetArena(enc.Def.ArenaCenter, enc.Def.ArenaRadius);
                enc.Enemies.Add(e);
                VfxManager.Instance?.FlashSprite(pl.Position + Vector3.up, 2, new Color(1, 0.35f, 0.23f), 0.2f);
            }
        }

        public void SpawnMinion(string type, Vector3 pos, string encounterId)
        {
            if (Root == null) return;
            var e = EnemyFactory.SpawnMinion(type, pos, encounterId, Root);
            if (e == null) return;
            if (encounterId != null && encounters.TryGetValue(encounterId, out var enc))
            {
                enc.Enemies.Add(e);
                if (enc.Def.ArenaRadius > 0) e.SetArena(enc.Def.ArenaCenter, enc.Def.ArenaRadius);
            }
        }

        public void DespawnEncounter(string id)
        {
            if (!encounters.TryGetValue(id, out var enc)) return;
            foreach (var e in enc.Enemies) if (e != null) e.Despawn();
            encounters.Remove(id);
        }

        public bool EncounterActive(string id) => encounters.ContainsKey(id);

        public void OnEnemyKilled(Component enemy)
        {
            var e = enemy as Enemy;
            if (e == null) return;
            tokens.Remove(e);
            var id = e.EncounterId;
            if (string.IsNullOrEmpty(id) || !encounters.TryGetValue(id, out var enc)) return;
            if (enc.Enemies.Any(x => x != null && x.Alive)) return;
            if (enc.Wave < enc.Def.Waves.Count - 1)
            {
                enc.Wave++;
                _ = NextWave(id, enc);
                return;
            }
            encounters.Remove(id);
            if (!enc.Def.Respawn) G.State.MarkDefeated(id);
            Script?.OnEncounterCleared(id);
            Bus.Emit(new EncounterCleared { Id = id });
        }

        async Task NextWave(string id, ActiveEncounter enc)
        {
            await Awaitable.WaitForSecondsAsync(1.5f);
            if (encounters.TryGetValue(id, out var cur) && cur == enc) SpawnWave(enc);
        }

        // ------------------------------------------------------------------ IWorld

        public bool RequestAttackToken(UnityEngine.Object enemy)
        {
            if (tokens.Contains(enemy)) return true;
            tokens.RemoveWhere(t => t == null || (t is Enemy en && !en.Alive));
            if (tokens.Count >= MaxTokens) return false;
            tokens.Add(enemy);
            return true;
        }

        public void ReleaseAttackToken(UnityEngine.Object enemy) => tokens.Remove(enemy);

        // The world answers line-of-sight itself (CombatSystem.LineOfSight delegates here; delegating back recursed forever).
        public bool LineOfSight(Vector3 from, Vector3 to) => !Physics.Linecast(from, to, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore);

        public float? GroundAt(Vector3 p, float maxDist = 20) =>
            Physics.Raycast(p + Vector3.up * 0.5f, Vector3.down, out var h, maxDist + 0.5f, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore) ? h.point.y : null;

        // ------------------------------------------------------------------ echo sight

        public void EchoReveal(Vector3 center, float range, float duration)
        {
            echoT = Mathf.Max(echoT, duration);
            echoRange = range;
            echoCenter = center;
            VfxManager.Instance?.EchoReveal(center, range);
        }

        void ApplyReveal(ZoneInteractable i, bool fx)
        {
            if (i.RevealObject != null) i.RevealObject.SetActive(true);
            if (i.HideOnReveal != null) i.HideOnReveal.SetActive(false);
            if (fx)
            {
                var violet = new Color(0.64f, 0.49f, 1f);
                VfxManager.Instance?.FlashSprite(i.Position, 2, violet, 0.4f);
                VfxManager.Instance?.Embers(i.Position, 20, violet, 1, 1.2f);
                G.Audio?.Play("reveal", i.Position);
                G.Presentation?.Toast("Echo revealed something hidden");
            }
        }

        void UpdateEcho(float dt, Vector3? playerPos)
        {
            if (echoT <= 0) return;
            echoT -= dt;
            var gs = G.State;
            var center = playerPos ?? echoCenter;
            foreach (var li in interactables)
            {
                var i = li.Def;
                if (!i.Hidden || gs.IsRevealed(i.Id)) continue;
                if (Vector3.Distance(i.Position, center) > echoRange) continue;
                gs.Reveal(i.Id);
                ApplyReveal(i, true);
                Script?.OnRevealed(i.Id);
            }
            foreach (var p in Pickups)
            {
                if (!p.Hidden || p.Collected || Vector3.Distance(p.Position, center) > echoRange) continue;
                p.Reveal();
                gs.Reveal(p.Id);
                var li = interactables.Find(x => x.Def.Id == p.Id);
                if (li != null) li.Def.Hidden = false;
                VfxManager.Instance?.FlashSprite(p.Position, 1.6f, new Color(0.64f, 0.49f, 1f), 0.4f);
                G.Audio?.Play("reveal", p.Position);
            }
        }

        // ------------------------------------------------------------------ per frame

        public void Tick(float dt, Vector3? playerPos, bool canInteract, bool revealBuff)
        {
            if (Def == null) return;
            if (revealBuff && echoT < 0.2f && playerPos.HasValue) EchoReveal(playerPos.Value, 24, 0.6f);
            UpdateEcho(dt, playerPos);
            Script?.Tick(dt);
            foreach (var n in Npcs) if (n != null) n.Tick(dt, playerPos, EchoActive);
            foreach (var p in Pickups)
            {
                if (p == null || p.Collected || !p.Auto || p.Hidden || !playerPos.HasValue || !canInteract) continue;
                if (Vector3.Distance(p.Position, playerPos.Value + Vector3.up * 0.9f) < 1.5f && G.State.CheckAll(p.Conditions)) Collect(p);
            }
            if (!playerPos.HasValue) { Candidate = null; CandidatePrompt = null; return; }
            var pp = playerPos.Value;
            // Triggers
            foreach (var t in Def.Triggers)
            {
                var b = new Bounds(t.Center, t.Size);
                var inside = b.Contains(pp + Vector3.up * 0.5f);
                var was = insideTriggers.Contains(t.Id);
                if (inside && !was && G.State.CheckAll(t.Conditions) && (t.Available == null || t.Available()))
                {
                    insideTriggers.Add(t.Id);
                    if (!t.Once || !firedTriggers.Contains(t.Id))
                    {
                        firedTriggers.Add(t.Id);
                        t.OnEnter?.Invoke();
                        Script?.OnTrigger(t.Id);
                        Bus.Emit(new TriggerEnter { Id = t.Id });
                        foreach (var e in Def.Encounters) if (e.Spawn == "trigger:" + t.Id) SpawnEncounter(e.Id);
                    }
                }
                else if (!inside && was)
                {
                    insideTriggers.Remove(t.Id);
                    Bus.Emit(new TriggerExit { Id = t.Id });
                }
            }
            // Exits
            exitCooldown = Mathf.Max(0, exitCooldown - dt);
            string bestId = null, bestPrompt = null, bestLocked = null;
            Vector3? bestPos = null;
            var bestD = float.PositiveInfinity;
            Action bestUse = null;
            ZoneExit bestExit = null;
            foreach (var x in Def.Exits)
            {
                var d = Vector3.Distance(x.Position, pp);
                if (d > x.Radius) continue;
                var ok = G.State.CheckAll(x.Requires) && (x.RequiresFn == null || x.RequiresFn());
                if (x.Auto && ok && exitCooldown <= 0 && canInteract)
                {
                    exitCooldown = 3;
                    _ = G.Manager.ChangeZone(x.Target, x.Entry);
                    return;
                }
                if (d < bestD)
                {
                    bestD = d; bestId = x.Id; bestPrompt = x.Prompt; bestPos = x.Position;
                    bestLocked = ok ? null : x.LockedText ?? "Locked";
                    bestExit = x; bestUse = null; // no per-frame closure: Interact() takes the exit
                }
            }
            foreach (var li in interactables)
            {
                if (li.Consumed) continue;
                var i = li.Def;
                if (i.Hidden && !G.State.IsRevealed(i.Id)) continue;
                var flat = new Vector2(i.Position.x - pp.x, i.Position.z - pp.z).magnitude;
                var d = flat + Mathf.Abs(i.Position.y - (pp.y + 1)) * 0.5f;
                if (d > i.Radius || d >= bestD) continue;
                var avail = li.Available == null || li.Available();
                var reason = !avail ? li.Locked?.Invoke() : null;
                if (!avail && reason == null) continue;
                bestD = d; bestId = i.Id; bestPrompt = li.Prompt?.Invoke() ?? i.Prompt; bestLocked = reason; bestPos = i.Position; bestUse = li.OnUse; bestExit = null;
            }
            Candidate = bestId; CandidatePrompt = bestPrompt; CandidateLocked = bestLocked; CandidatePosition = bestPos;
            candidateUse = bestUse;
            candidateExit = bestExit;
        }

        Action candidateUse;
        ZoneExit candidateExit;

        public bool Interact()
        {
            if (Candidate == null) return false;
            if (CandidateLocked != null) { G.Presentation?.Toast(CandidateLocked, ToastKind.Warn); return false; }
            if (candidateExit != null)
            {
                if (exitCooldown > 0) return true;
                exitCooldown = 3;
                _ = G.Manager.ChangeZone(candidateExit.Target, candidateExit.Entry);
                return true;
            }
            candidateUse?.Invoke();
            return true;
        }

        /// <summary>Use an interactable by id regardless of distance (tests / scripted).</summary>
        public bool InteractWith(string id)
        {
            var li = interactables.Find(x => x.Def.Id == id && !x.Consumed);
            if (li == null) return false;
            li.OnUse?.Invoke();
            return true;
        }

        public int AggroCount(Vector3 near, float radius = 35) => Enemy.CountAggro(near, radius);

        public Npc FindNpc(string id) => Npcs.Find(n => n != null && n.Id == id);

        /// <summary>World position of a quest marker id (interactable, trigger, exit, npc_x, collectible or named marker).</summary>
        public Vector3? ResolveMarker(string id)
        {
            if (Def == null || string.IsNullOrEmpty(id)) return null;
            // Called every frame for the HUD objective marker: plain loops, no closures or substrings.
            var s = Script?.ResolveMarker(id);
            if (s.HasValue) return s;
            foreach (var li in interactables) if (li.Def.Id == id && !li.Consumed) return li.Position;
            foreach (var t in Def.Triggers) if (t.Id == id) return t.Center;
            foreach (var e in Def.Exits) if (e.Id == id) return e.Position;
            if (id.StartsWith("npc_", StringComparison.Ordinal))
                foreach (var n in Npcs)
                    if (n != null && n.Id != null && n.Id.Length == id.Length - 4 && string.CompareOrdinal(id, 4, n.Id, 0, n.Id.Length) == 0) return n.Position + Vector3.up * 1.8f;
            foreach (var p in Pickups) if (p != null && p.Id == id && !p.Collected) return p.Position;
            return Def.Marker(id);
        }

        /// <summary>Exit leading to a zone (for routing the objective marker across zones).</summary>
        public ZoneExit ExitTo(string zone)
        {
            if (Def == null) return null;
            foreach (var x in Def.Exits) if (x.Target == zone) return x; // per-frame (objective marker): no closure
            return null;
        }

        public ZoneMapData Map => map;

        ZoneMapData BuildMap()
        {
            var m = new ZoneMapData { ZoneId = ZoneId, Min = Def.MapMin, Max = Def.MapMax };
            m.Rects.AddRange(Def.MapRects);
            m.Lines.AddRange(Def.MapLines);
            m.Labels.AddRange(Def.MapLabels);
            foreach (var x in Def.Exits)
            {
                var xx = x;
                m.Markers.Add(new MapMarker { Kind = MapMarkerKind.Exit, Position = x.Position, Label = x.Prompt, TargetZone = x.Target, Locked = () => !G.State.CheckAll(xx.Requires) || (xx.RequiresFn != null && !xx.RequiresFn()) });
            }
            foreach (var i in Def.Interactables) if (i.Kind == "save") m.Markers.Add(new MapMarker { Kind = MapMarkerKind.Save, Position = i.Position, Label = "Save terminal" });
            // Reused buffers: the minimap polls these at 20 Hz.
            var npcBuf = new List<Vector3>();
            var hiddenBuf = new List<Vector3>();
            m.Npcs = () => { npcBuf.Clear(); foreach (var n in Npcs) if (n != null && !n.Place.EchoOnly) npcBuf.Add(n.Position); return npcBuf; };
            m.HiddenPickups = () => { hiddenBuf.Clear(); foreach (var p in Pickups) if (p != null && !p.Collected && p.Hidden) hiddenBuf.Add(p.Position); return hiddenBuf; };
            return m;
        }
    }
}
