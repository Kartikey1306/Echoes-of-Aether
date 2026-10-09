using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Runtime audio. Plays the clips pre-rendered from the prototype's procedural engine
    /// (tools/audio/render.mjs -> Resources/Audio/{SFX,Music,Ambience,Thunder} + manifest.json) through pooled
    /// AudioSources. Buses (master/music/sfx/voice/ui/ambience) are plain volume multipliers, there is no
    /// AudioMixer asset. Volumes follow the prototype's curve (gain = v^2) and every clip carries the manifest
    /// "gain" that restores the prototype's relative balance. The AudioListener stays on the main camera
    /// (owned by GameManager/camera rig). WebGL safe: no threads, no coroutines needed.
    /// </summary>
    [DisallowMultipleComponent]
    public sealed class AudioManager : MonoBehaviour, IAudio, IAudioDebugInfo
    {
        // ------------------------------------------------------------------ tuning
        const string ResRoot = "Audio/";
        const int Pool3DSize = 20;
        const int Pool2DSize = 8;
        const int LoopSources = 3;              // per loop channel (music / ambience): survives rapid re-targeting
        const float MinDistance = 2f;           // full volume inside this radius
        const float MaxDistance = 40f;          // logarithmic rolloff stops attenuating here
        const float CullDistance = 45f;         // positional sounds further than this are not started
        const float PitchJitter = 0.04f;        // +-4% on non-UI SFX
        const int WarmupPerFrame = 4;           // SFX sets loaded per frame after creation

        /// <summary>Exponent of the bus volume curve (prototype: gain = v*v).</summary>
        public float VolumeExponent = 2f;

        /// <summary>Mirrors UI_SOUNDS in the prototype (routed to the ui bus); the manifest "bus" field wins when present.</summary>
        static readonly HashSet<string> UiSounds = new()
        {
            "ui_hover", "ui_click", "ui_back", "quest_accept", "quest_complete", "save", "load", "error_ui",
            "checkpoint", "item", "lore", "toast",
        };

        enum Route { Sfx, Ui, Music, Ambience, Voice }

        sealed class Entry
        {
            public Route Route;
            public string[] Paths;
            public float[] Gains;
        }

        sealed class ClipSet
        {
            public Route Route;
            public AudioClip[] Clips;
            public float[] Gains;
            int last = -1;

            /// <summary>Random take, never the same take twice in a row.</summary>
            public int Pick()
            {
                int n = Clips.Length;
                if (n <= 1) return 0;
                int i;
                if (last < 0) i = Random.Range(0, n);
                else
                {
                    i = Random.Range(0, n - 1);
                    if (i >= last) i++;
                }
                last = i;
                return i;
            }
        }

        sealed class Voice
        {
            public AudioSource Src;
            public string Id;
            public Route Route;
            public float Base;      // clip gain * caller volume
            public float Started;   // unscaled time
        }

        /// <summary>Crossfading looped bed (music or ambience) over a few sources.</summary>
        sealed class LoopChannel
        {
            public readonly AudioSource[] Src = new AudioSource[LoopSources];
            readonly string[] key = new string[LoopSources];
            readonly float[] gain = new float[LoopSources];
            readonly float[] level = new float[LoopSources];
            readonly float[] target = new float[LoopSources];
            readonly float[] rate = new float[LoopSources];
            public string Current = "";

            public void Set(string id, AudioClip clip, float clipGain, float fade)
            {
                float r = 1f / Mathf.Max(0.01f, fade);
                int idx = -1;
                if (clip != null)
                {
                    for (int i = 0; i < LoopSources; i++)
                        if (key[i] == id && Src[i].clip == clip) idx = i; // still playing/fading: pick it back up
                    if (idx < 0)
                    {
                        idx = 0; // reuse the quietest source
                        for (int i = 1; i < LoopSources; i++) if (level[i] < level[idx]) idx = i;
                        var s = Src[idx];
                        s.Stop();
                        s.clip = clip;
                        key[idx] = id;
                        level[idx] = 0f;
                        s.volume = 0f;
                        if (clip.loadState == AudioDataLoadState.Unloaded) clip.LoadAudioData();
                        s.Play(); // deferred by Unity until the data is loaded when loadInBackground is set
                    }
                    else if (!Src[idx].isPlaying) Src[idx].Play();
                    gain[idx] = clipGain;
                }
                for (int i = 0; i < LoopSources; i++)
                {
                    target[i] = i == idx ? 1f : 0f;
                    rate[i] = r;
                }
            }

            public void Tick(float dt, float busVolume)
            {
                for (int i = 0; i < LoopSources; i++)
                {
                    level[i] = Mathf.MoveTowards(level[i], target[i], rate[i] * dt);
                    var s = Src[i];
                    if (level[i] <= 0f && target[i] <= 0f)
                    {
                        if (s.isPlaying) s.Stop();
                        s.volume = 0f;
                        continue;
                    }
                    // Equal-power crossfade between different (uncorrelated) beds.
                    s.volume = Mathf.Clamp01(gain[i] * Mathf.Sin(level[i] * Mathf.PI * 0.5f) * busVolume);
                }
            }

            public int Playing
            {
                get
                {
                    int n = 0;
                    for (int i = 0; i < LoopSources; i++) if (Src[i].isPlaying) n++;
                    return n;
                }
            }
        }

        struct PendingThunder
        {
            public float At;
            public float Intensity;
        }

        // ------------------------------------------------------------------ state
        readonly Dictionary<string, Dictionary<string, Entry>> manifest = new()
        {
            ["sfx"] = new Dictionary<string, Entry>(),
            ["music"] = new Dictionary<string, Entry>(),
            ["ambience"] = new Dictionary<string, Entry>(),
            ["thunder"] = new Dictionary<string, Entry>(),
        };
        bool manifestLoaded;
        readonly Dictionary<string, ClipSet> sfxSets = new();
        readonly Dictionary<string, ClipSet> loopSets = new();
        ClipSet thunderSet;
        bool thunderLoaded;
        readonly HashSet<string> warned = new();
        readonly Dictionary<string, float> lastPlay = new();
        readonly Queue<string> warmup = new();
        readonly List<PendingThunder> thunders = new();

        Voice[] pool3D;
        Voice[] pool2D;
        readonly LoopChannel music = new();
        readonly LoopChannel ambience = new();

        float master = 0.85f, musicVol = 0.6f, sfxVol = 0.8f, voiceVol = 0.9f, uiVol = 0.6f, ambienceVol = 0.7f;
        float duck, duckTarget, duckRate = 1f;
        Vector3 listenerPos;
        System.Action unsubSettings;

        /// <summary>Current music mood (IAudioDebugInfo, debug overlay).</summary>
        public string Mood => string.IsNullOrEmpty(music.Current) ? "silence" : music.Current;
        /// <summary>Current ambience bed (IAudioDebugInfo, debug overlay).</summary>
        public string Ambience => string.IsNullOrEmpty(ambience.Current) ? "none" : ambience.Current;
        /// <summary>SFX started since creation (debug overlay).</summary>
        public int Played { get; private set; }
        /// <summary>Currently sounding sources (debug overlay).</summary>
        public int ActiveVoices
        {
            get
            {
                int n = music.Playing + ambience.Playing;
                foreach (var v in pool3D) if (v.Src.isPlaying) n++;
                foreach (var v in pool2D) if (v.Src.isPlaying) n++;
                return n;
            }
        }

        // ------------------------------------------------------------------ lifecycle
        /// <summary>Build the audio GameObject (pools, loop sources) under <paramref name="parent"/>.</summary>
        public static AudioManager Create(Transform parent)
        {
            var go = new GameObject("Audio");
            if (parent != null) go.transform.SetParent(parent, false);
            else DontDestroyOnLoad(go);
            return go.AddComponent<AudioManager>();
        }

        void Awake()
        {
            pool3D = new Voice[Pool3DSize];
            for (int i = 0; i < Pool3DSize; i++) pool3D[i] = new Voice { Src = NewSource($"Sfx3D_{i:00}", true, 128), Started = -1f };
            pool2D = new Voice[Pool2DSize];
            for (int i = 0; i < Pool2DSize; i++) pool2D[i] = new Voice { Src = NewSource($"Sfx2D_{i:00}", false, 96), Started = -1f };
            for (int i = 0; i < LoopSources; i++)
            {
                music.Src[i] = NewSource($"Music_{i}", false, 0);
                music.Src[i].loop = true;
                ambience.Src[i] = NewSource($"Ambience_{i}", false, 16);
                ambience.Src[i].loop = true;
            }
            LoadManifest();
            foreach (var id in manifest["sfx"].Keys) warmup.Enqueue(id);
            if (G.Settings != null) SetVolumes(G.Settings.Data.Audio);
        }

        void OnEnable() => unsubSettings = Bus.On<SettingsChanged>(OnSettingsChanged);

        void OnDisable()
        {
            unsubSettings?.Invoke();
            unsubSettings = null;
        }

        void Start()
        {
            if (G.Settings != null) SetVolumes(G.Settings.Data.Audio);
        }

        void OnDestroy()
        {
            if (ReferenceEquals(G.Audio, this)) G.Audio = null;
        }

        void OnSettingsChanged(SettingsChanged e)
        {
            // Idempotent: re-apply whatever section changed (GameManager may also call SetVolumes).
            if (G.Settings != null) SetVolumes(G.Settings.Data.Audio);
        }

        AudioSource NewSource(string name, bool spatial, int priority)
        {
            var go = new GameObject(name);
            go.transform.SetParent(transform, false);
            var s = go.AddComponent<AudioSource>();
            s.playOnAwake = false;
            s.loop = false;
            s.priority = priority;
            s.dopplerLevel = 0f;
            s.spatialBlend = spatial ? 1f : 0f;
            if (spatial)
            {
                s.rolloffMode = AudioRolloffMode.Logarithmic;
                s.minDistance = MinDistance;
                s.maxDistance = MaxDistance;
                s.spread = 0f;
            }
            return s;
        }

        void Update()
        {
            float dt = Time.unscaledDeltaTime; // fades keep running while paused (timeScale 0)
            float now = Time.unscaledTime;
            var cam = Camera.main;
            if (cam != null) listenerPos = cam.transform.position;

            duck = Mathf.MoveTowards(duck, duckTarget, duckRate * dt);
            music.Tick(dt, BusGain(Route.Music) * MusicDuck);
            ambience.Tick(dt, BusGain(Route.Ambience) * AmbienceDuck);

            for (int i = thunders.Count - 1; i >= 0; i--)
            {
                if (now < thunders[i].At) continue;
                float intensity = thunders[i].Intensity;
                thunders.RemoveAt(i);
                PlayThunderNow(intensity);
            }

            for (int i = 0; i < WarmupPerFrame && warmup.Count > 0; i++) GetSfx(warmup.Dequeue());

            RefreshVoices(pool3D);
            RefreshVoices(pool2D);
        }

        // ------------------------------------------------------------------ IAudio
        public void Play(string id, Vector3? position = null, float volume = 1, float pitch = 1)
        {
            if (string.IsNullOrEmpty(id)) return;
            var set = GetSfx(id);
            if (set == null) return;
            PlaySet(set, id, set.Route, position, volume, pitch, set.Route != Route.Ui);
        }

        public void PlayUi(string id)
        {
            if (string.IsNullOrEmpty(id)) return;
            var set = GetSfx(id);
            if (set == null) return;
            PlaySet(set, id, Route.Ui, null, 1f, 1f, false);
        }

        public void SetMusic(string mood, float fade = 2f)
        {
            if (string.IsNullOrEmpty(mood) || mood == "none") mood = "silence";
            if (mood == music.Current) return;
            music.Current = mood;
            var set = mood == "silence" ? null : GetLoop("music", mood);
            music.Set(mood, set?.Clips[0], set != null ? set.Gains[0] : 0f, fade);
        }

        public void SetAmbience(string id, float fade = 2f)
        {
            if (string.IsNullOrEmpty(id)) id = "none";
            if (id == ambience.Current) return;
            ambience.Current = id;
            var set = id == "none" ? null : GetLoop("ambience", id);
            ambience.Set(id, set?.Clips[0], set != null ? set.Gains[0] : 0f, fade);
        }

        /// <summary>
        /// Duck music and ambience by <paramref name="amount"/> (0 = none, 1 = silent music) over
        /// <paramref name="seconds"/>; call again with 0 to release. Prototype dialogue duck = Duck(0.55, 0.25)
        /// (music x0.45, ambience x0.6).
        /// </summary>
        public void Duck(float amount, float seconds)
        {
            duckTarget = Mathf.Clamp01(float.IsNaN(amount) ? 0f : amount);
            if (!(seconds > 0f))
            {
                duck = duckTarget;
                duckRate = 1f;
            }
            else duckRate = Mathf.Max(0.0001f, Mathf.Abs(duckTarget - duck) / seconds);
        }

        /// <summary>Distant thunder clap. Arrives after a distance delay (stronger = closer = sooner).</summary>
        public void Thunder(float intensity)
        {
            if (!(intensity > 0f)) return;
            float i01 = Mathf.Clamp01(intensity);
            float delay = Mathf.Lerp(2.8f, 0.6f, i01) * Random.Range(0.8f, 1.2f);
            thunders.Add(new PendingThunder { At = Time.unscaledTime + delay, Intensity = Mathf.Min(intensity, 1.5f) });
        }

        public void SetVolumes(AudioSettings s)
        {
            if (s == null) return;
            master = s.Master;
            musicVol = s.Music;
            sfxVol = s.Sfx;
            voiceVol = s.Voice;
            uiVol = s.Ui;
            ambienceVol = s.Ambience;
            RefreshVoices(pool3D);
            RefreshVoices(pool2D);
        }

        // ------------------------------------------------------------------ playback
        float Curve(float v) => Mathf.Pow(Mathf.Clamp01(float.IsNaN(v) ? 0f : v), VolumeExponent);

        float BusGain(Route r)
        {
            float b = r switch
            {
                Route.Music => musicVol,
                Route.Ambience => ambienceVol,
                Route.Ui => uiVol,
                Route.Voice => voiceVol,
                _ => sfxVol,
            };
            return Curve(master) * Curve(b);
        }

        float MusicDuck => 1f - duck;
        float AmbienceDuck => 1f - 0.75f * duck;

        float VoiceVolume(Voice v)
        {
            float g = v.Base * BusGain(v.Route);
            if (v.Route == Route.Ambience) g *= AmbienceDuck;
            return Mathf.Clamp01(g);
        }

        void RefreshVoices(Voice[] pool)
        {
            if (pool == null) return;
            foreach (var v in pool) if (v.Src.isPlaying) v.Src.volume = VoiceVolume(v);
        }

        static float MinGap(string id) => id == "footstep" ? 0.06f : id.StartsWith("ui_", System.StringComparison.Ordinal) ? 0.03f : 0.025f;
        static int MaxConcurrent(string id) => id == "footstep" || id == "hit" ? 6 : 4;

        int CountActive(string id)
        {
            int n = 0;
            foreach (var v in pool3D) if (v.Id == id && v.Src.isPlaying) n++;
            foreach (var v in pool2D) if (v.Id == id && v.Src.isPlaying) n++;
            return n;
        }

        static Voice Acquire(Voice[] pool)
        {
            Voice oldest = pool[0];
            foreach (var v in pool)
            {
                if (!v.Src.isPlaying) return v;
                if (v.Started < oldest.Started) oldest = v;
            }
            oldest.Src.Stop(); // steal the oldest voice
            return oldest;
        }

        void PlaySet(ClipSet set, string id, Route route, Vector3? position, float volume, float pitch, bool jitter)
        {
            if (!(volume > 0f)) return;
            float now = Time.unscaledTime;
            if (lastPlay.TryGetValue(id, out var last) && now - last < MinGap(id)) return;
            if (CountActive(id) >= MaxConcurrent(id)) return;
            if (position.HasValue && (position.Value - listenerPos).sqrMagnitude > CullDistance * CullDistance) return;
            lastPlay[id] = now;

            int k = set.Pick();
            var v = Acquire(position.HasValue ? pool3D : pool2D);
            var s = v.Src;
            if (position.HasValue) s.transform.position = position.Value;
            float p = pitch > 0f ? Mathf.Clamp(pitch, 0.25f, 3f) : 1f;
            if (jitter) p *= 1f + Random.Range(-PitchJitter, PitchJitter);
            s.clip = set.Clips[k];
            s.pitch = p;
            s.ignoreListenerPause = route == Route.Ui;
            v.Id = id;
            v.Route = route;
            v.Base = set.Gains[k] * volume;
            v.Started = now;
            s.volume = VoiceVolume(v);
            s.Play();
            Played++;
        }

        void PlayThunderNow(float intensity)
        {
            if (!thunderLoaded)
            {
                thunderLoaded = true;
                thunderSet = LoadSet("thunder", "thunder", Route.Ambience);
                if (thunderSet == null) WarnOnce("thunder", "[audio] no thunder clips in Resources/Audio/Thunder");
            }
            if (thunderSet == null) return;
            int k = thunderSet.Pick();
            var v = Acquire(pool2D);
            var s = v.Src;
            s.clip = thunderSet.Clips[k];
            s.pitch = Random.Range(0.9f, 1.05f);
            s.ignoreListenerPause = false;
            v.Id = "thunder";
            v.Route = Route.Ambience;
            v.Base = thunderSet.Gains[k] * intensity;
            v.Started = Time.unscaledTime;
            s.volume = VoiceVolume(v);
            s.Play();
        }

        // ------------------------------------------------------------------ clip loading
        ClipSet GetSfx(string id)
        {
            if (sfxSets.TryGetValue(id, out var set)) return set;
            set = LoadSet("sfx", id, UiSounds.Contains(id) ? Route.Ui : Route.Sfx);
            sfxSets[id] = set; // a missing id is cached as null and warned about once
            if (set == null) WarnOnce("sfx:" + id, $"[audio] unknown or missing sfx '{id}' (Resources/Audio/SFX)");
            return set;
        }

        ClipSet GetLoop(string kind, string id)
        {
            string cacheKey = kind + ":" + id;
            if (loopSets.TryGetValue(cacheKey, out var set)) return set;
            set = LoadSet(kind, id, kind == "music" ? Route.Music : Route.Ambience);
            loopSets[cacheKey] = set;
            if (set == null) WarnOnce(cacheKey, $"[audio] unknown or missing {kind} '{id}'");
            return set;
        }

        /// <summary>Load every take of a clip group via the manifest, or by naming convention without one.</summary>
        ClipSet LoadSet(string kind, string id, Route fallbackRoute)
        {
            var clips = new List<AudioClip>();
            var gains = new List<float>();
            var route = fallbackRoute;
            if (manifest.TryGetValue(kind, out var table) && table.TryGetValue(id, out var e))
            {
                route = e.Route;
                for (int i = 0; i < e.Paths.Length; i++)
                {
                    var c = string.IsNullOrEmpty(e.Paths[i]) ? null : Resources.Load<AudioClip>(ResRoot + e.Paths[i]);
                    if (c == null)
                    {
                        WarnOnce("file:" + e.Paths[i], $"[audio] manifest lists missing clip Resources/{ResRoot}{e.Paths[i]}");
                        continue;
                    }
                    clips.Add(c);
                    gains.Add(e.Gains[i]);
                }
            }
            else
            {
                foreach (var path in ConventionPaths(kind, id))
                {
                    var c = Resources.Load<AudioClip>(ResRoot + path);
                    if (c == null) continue;
                    clips.Add(c);
                    gains.Add(1f);
                }
            }
            if (clips.Count == 0) return null;
            return new ClipSet { Route = route, Clips = clips.ToArray(), Gains = gains.ToArray() };
        }

        static IEnumerable<string> ConventionPaths(string kind, string id)
        {
            switch (kind)
            {
                case "sfx":
                    yield return "SFX/" + id;
                    for (int v = 1; v <= 4; v++) yield return $"SFX/{id}_v{v}";
                    break;
                case "music":
                    yield return "Music/" + id;
                    break;
                case "ambience":
                    yield return "Ambience/" + id;
                    break;
                case "thunder":
                    for (int v = 1; v <= 4; v++) yield return $"Thunder/thunder_{v}";
                    break;
            }
        }

        void LoadManifest()
        {
            if (manifestLoaded) return;
            manifestLoaded = true;
            var asset = Resources.Load<TextAsset>(ResRoot + "manifest");
            if (asset == null)
            {
                Debug.LogWarning("[audio] Resources/Audio/manifest.json missing: clips load by name with gain 1 (mix balance lost). Run tools/audio/render.mjs.");
                return;
            }
            try
            {
                var root = JObject.Parse(asset.text);
                if (root["clips"] is not JArray list) return;
                foreach (var c in list)
                {
                    string id = (string)c["id"];
                    string kind = (string)c["kind"];
                    if (string.IsNullOrEmpty(id) || kind == null || !manifest.TryGetValue(kind, out var table)) continue;
                    if (c["files"] is not JArray files || files.Count == 0) continue;
                    var e = new Entry
                    {
                        Route = RouteOf((string)c["bus"], kind),
                        Paths = new string[files.Count],
                        Gains = new float[files.Count],
                    };
                    for (int i = 0; i < files.Count; i++)
                    {
                        e.Paths[i] = (string)files[i]["path"];
                        var g = files[i]["gain"];
                        e.Gains[i] = g != null && (g.Type == JTokenType.Float || g.Type == JTokenType.Integer) ? Mathf.Clamp01((float)g) : 1f;
                    }
                    table[id] = e;
                }
            }
            catch (System.Exception ex)
            {
                Debug.LogWarning($"[audio] manifest.json unreadable ({ex.Message}); clips load by name with gain 1.");
            }
        }

        static Route RouteOf(string bus, string kind) => bus switch
        {
            "ui" => Route.Ui,
            "music" => Route.Music,
            "ambience" => Route.Ambience,
            "voice" => Route.Voice,
            "sfx" => Route.Sfx,
            _ => kind == "music" ? Route.Music : kind == "ambience" || kind == "thunder" ? Route.Ambience : Route.Sfx,
        };

        void WarnOnce(string key, string message)
        {
            if (warned.Add(key)) Debug.LogWarning(message);
        }
    }
}
