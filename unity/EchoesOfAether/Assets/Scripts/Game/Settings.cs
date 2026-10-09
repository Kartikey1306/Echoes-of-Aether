using System;
using System.IO;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace EOA
{
    public sealed class GameplaySettings { public string Difficulty = "normal"; public float CameraSensitivity = 1, AimSensitivity = 0.6f, CameraShake = 1; public bool InvertY, AutoLock = true; }
    public sealed class GraphicsSettings
    {
        public string Preset = "high";      // low | medium | high | ultra | custom
        public string Resolution = "balanced"; // performance | balanced | quality | native (render scale)
        public bool Fullscreen;
        public string FrameLimit = "vsync"; // vsync | 30 | 60 | unlimited
        public string Shadows = "high";     // off | low | medium | high
        public string Effects = "high", Textures = "high", ViewDistance = "high"; // low | medium | high
        public string Antialiasing = "taa"; // off | fxaa | smaa | taa | msaa
        /// <summary>True until the player changes a graphics option: lets <see cref="PerformanceGuard"/> lower the preset.</summary>
        public bool AutoQuality = true;
    }
    public sealed class AudioSettings { public float Master = 0.85f, Music = 0.6f, Sfx = 0.8f, Voice = 0.9f, Ambience = 0.7f, Ui = 0.6f; /// <summary>Voice-over on by default (can be turned off on the new game screen or in Settings).</summary>
        public bool VoiceOver = true; }
    public sealed class ControlSettings { public string BindingOverrides = ""; public float PadLookSpeed = 1; public bool Vibration = true; }
    public sealed class AccessibilitySettings { public bool Subtitles = true, SpeakerNames = true, HoldToSkip = true; public string SubtitleSize = "medium"; public float SubtitleBackground = 0.55f, FlashIntensity = 1, CameraShake = 1, UiScale = 1; }
    public sealed class LanguageSettings { public string Locale = "en"; }

    public sealed class SettingsData
    {
        public int Version = Settings.Version;
        public GameplaySettings Gameplay = new();
        public GraphicsSettings Graphics = new();
        public AudioSettings Audio = new();
        public ControlSettings Controls = new();
        public AccessibilitySettings Accessibility = new();
        public LanguageSettings Language = new();
    }

    public readonly struct DifficultyMods
    {
        public readonly float EnemyDamage, EnemyHealth, PlayerRegen, Aggression;
        public DifficultyMods(float d, float h, float r, float a) { EnemyDamage = d; EnemyHealth = h; PlayerRegen = r; Aggression = a; }
    }

    /// <summary>Persistent player settings with validation/repair of untrusted data.</summary>
    public sealed class Settings
    {
        public const int Version = 2;
        public SettingsData Data { get; private set; }
        readonly string path;

        public Settings(string dir = null)
        {
            path = Path.Combine(dir ?? Application.persistentDataPath, "settings.json");
            Data = Load();
        }

        /// <summary>
        /// Fresh settings. WebGL starts on the Medium preset (no SSAO, low shadows, fewer city props). Desktop players
        /// start fullscreen at the desktop resolution (a 1920x1080 window would overflow a 1366x768 laptop) on a preset
        /// picked from the hardware, so the first launch runs on any Windows PC.
        /// </summary>
        public static SettingsData Defaults()
        {
            var d = new SettingsData();
            if (Application.platform == RuntimePlatform.WebGLPlayer) PresetValues(d.Graphics, "medium");
            else
            {
                if (!Application.isEditor) d.Graphics.Fullscreen = true;
                PresetValues(d.Graphics, HardwarePreset());
            }
            return d;
        }

        static string hardwarePreset;

        /// <summary>
        /// Starting preset for this machine: integrated GPUs (Intel UHD/Iris, AMD APUs), small or unknown VRAM, low RAM
        /// or old shader models start on Low; mid-range cards on Medium; dedicated 4 GB+ cards on High. The editor
        /// always reports High so automated tests stay deterministic.
        /// </summary>
        public static string HardwarePreset()
        {
            if (hardwarePreset != null) return hardwarePreset;
            if (Application.isEditor) return hardwarePreset = "high";
            var gpu = (SystemInfo.graphicsDeviceName ?? "").ToLowerInvariant();
            var vram = SystemInfo.graphicsMemorySize;   // MB
            var ram = SystemInfo.systemMemorySize;      // MB
            var apple = gpu.Contains("apple");          // unified memory: VRAM figures don't apply
            var integrated = !apple && (gpu.Contains("intel") && !gpu.Contains("arc")
                || gpu.Contains("radeon(tm) graphics") || gpu.Contains("radeon graphics")
                || gpu.Contains("vega") && !gpu.Contains("rx vega")
                || gpu.Contains("microsoft basic") || gpu.Contains("llvmpipe"));
            hardwarePreset = SystemInfo.graphicsShaderLevel < 45 || ram < 6000 || integrated || !apple && vram < 2000 ? "low"
                : !apple && vram < 4000 || SystemInfo.processorCount < 4 ? "medium"
                : "high";
            Debug.Log($"[settings] hardware: {SystemInfo.graphicsDeviceName} ({vram} MB VRAM, {ram} MB RAM, {SystemInfo.processorCount} cores, SM {SystemInfo.graphicsShaderLevel}) → {hardwarePreset} preset");
            return hardwarePreset;
        }

        /// <summary>Write a preset's values into graphics settings (no save, no event).</summary>
        public static bool PresetValues(GraphicsSettings g, string p)
        {
            switch (p)
            {
                case "low": g.Resolution = "performance"; g.Shadows = "off"; g.Effects = "low"; g.Textures = "low"; g.ViewDistance = "low"; g.Antialiasing = "fxaa"; break;
                case "medium": g.Resolution = "balanced"; g.Shadows = "low"; g.Effects = "medium"; g.Textures = "medium"; g.ViewDistance = "medium"; g.Antialiasing = "fxaa"; break;
                // TAA on high / ultra (clean hair cards and thin geometry; the rain is drawn after the resolve). WebGL
                // falls back to SMAA in GraphicsConfig.
                case "high": g.Resolution = "quality"; g.Shadows = "high"; g.Effects = "high"; g.Textures = "high"; g.ViewDistance = "high"; g.Antialiasing = "taa"; break;
                case "ultra": g.Resolution = "native"; g.Shadows = "high"; g.Effects = "high"; g.Textures = "high"; g.ViewDistance = "high"; g.Antialiasing = "taa"; break;
                default: return false;
            }
            g.Preset = p;
            return true;
        }

        static float Num(float v, float lo, float hi, float d) => float.IsNaN(v) || float.IsInfinity(v) ? d : Mathf.Clamp(v, lo, hi);
        static string Pick(string v, string[] opts, string d) => Array.IndexOf(opts, v) >= 0 ? v : d;

        /// <summary>Validate and repair settings, filling missing or invalid fields with defaults.</summary>
        public static SettingsData Sanitize(SettingsData s)
        {
            var d = Defaults();
            if (s == null) return d;
            // v2: voice-over recordings now exist; settings saved while it was off-by-default (no audio) switch it on once.
            if (s.Version < 2 && s.Audio != null) s.Audio.VoiceOver = true;
            s.Version = Version;
            s.Gameplay ??= d.Gameplay; s.Graphics ??= d.Graphics; s.Audio ??= d.Audio; s.Controls ??= d.Controls; s.Accessibility ??= d.Accessibility; s.Language ??= d.Language;
            var g = s.Gameplay;
            g.Difficulty = Pick(g.Difficulty, new[] { "story", "normal", "hard" }, "normal");
            g.CameraSensitivity = Num(g.CameraSensitivity, 0.1f, 3, 1);
            g.AimSensitivity = Num(g.AimSensitivity, 0.1f, 3, 0.6f);
            g.CameraShake = Num(g.CameraShake, 0, 1.5f, 1);
            var gr = s.Graphics;
            gr.Preset = Pick(gr.Preset, new[] { "low", "medium", "high", "ultra", "custom" }, "high");
            gr.Resolution = Pick(gr.Resolution, new[] { "performance", "balanced", "quality", "native" }, "balanced");
            gr.FrameLimit = Pick(gr.FrameLimit, new[] { "vsync", "30", "60", "unlimited" }, "vsync");
            gr.Shadows = Pick(gr.Shadows, new[] { "off", "low", "medium", "high" }, "high");
            var q3 = new[] { "low", "medium", "high" };
            gr.Effects = Pick(gr.Effects, q3, "high"); gr.Textures = Pick(gr.Textures, q3, "high"); gr.ViewDistance = Pick(gr.ViewDistance, q3, "high");
            gr.Antialiasing = Pick(gr.Antialiasing, new[] { "off", "fxaa", "smaa", "taa", "msaa" }, "taa");
            var a = s.Audio;
            a.Master = Num(a.Master, 0, 1, 0.85f); a.Music = Num(a.Music, 0, 1, 0.6f); a.Sfx = Num(a.Sfx, 0, 1, 0.8f);
            a.Voice = Num(a.Voice, 0, 1, 0.9f); a.Ambience = Num(a.Ambience, 0, 1, 0.7f); a.Ui = Num(a.Ui, 0, 1, 0.6f);
            var c = s.Controls;
            c.BindingOverrides ??= ""; c.PadLookSpeed = Num(c.PadLookSpeed, 0.2f, 3, 1);
            var ac = s.Accessibility;
            ac.SubtitleSize = Pick(ac.SubtitleSize, new[] { "small", "medium", "large", "xl" }, "medium");
            ac.SubtitleBackground = Num(ac.SubtitleBackground, 0, 1, 0.55f);
            ac.FlashIntensity = Num(ac.FlashIntensity, 0, 1, 1);
            ac.CameraShake = Num(ac.CameraShake, 0, 1, 1);
            ac.UiScale = Num(ac.UiScale, 0.75f, 1.5f, 1);
            s.Language.Locale = string.IsNullOrEmpty(s.Language.Locale) ? "en" : s.Language.Locale;
            return s;
        }

        /// <summary>Parse untrusted JSON leniently: bad fields fall back to defaults instead of failing.</summary>
        public static SettingsData Parse(string json)
        {
            try
            {
                var token = JToken.Parse(json);
                if (token is not JObject obj) return Defaults();
                var ser = JsonSerializer.Create(new JsonSerializerSettings
                {
                    ContractResolver = GameData.Json.ContractResolver,
                    Error = (_, e) => e.ErrorContext.Handled = true, // ignore individually invalid values
                });
                return Sanitize(obj.ToObject<SettingsData>(ser));
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[settings] stored settings unreadable, using defaults: {e.Message}");
                return Defaults();
            }
        }

        SettingsData Load()
        {
            try { return File.Exists(path) ? Parse(File.ReadAllText(path)) : Defaults(); }
            catch (Exception e) { Debug.LogWarning($"[settings] {e.Message}"); return Defaults(); }
        }

        public void Save()
        {
            try { SafeFile.WriteAtomic(path, JsonConvert.SerializeObject(Data, Formatting.Indented, GameData.Json)); }
            catch (Exception e) { Debug.LogWarning($"[settings] failed to persist settings: {e.Message}"); }
        }

        /// <summary>Apply a change to one section, re-validate, persist and notify.</summary>
        public void Update(string section, Action<SettingsData> change)
        {
            change(Data);
            if (section == "graphics") Data.Graphics.AutoQuality = false;
            Data = Sanitize(Data);
            Save();
            Bus.Emit(new SettingsChanged { Section = section });
        }

        public static readonly string[] Presets = { "low", "medium", "high", "ultra" };

        public void ApplyPreset(string p)
        {
            if (!PresetValues(Data.Graphics, p)) return;
            Data.Graphics.AutoQuality = false;
            Save();
            Bus.Emit(new SettingsChanged { Section = "graphics" });
        }

        /// <summary>
        /// Lower the preset one step (Ultra → High → Medium → Low) on the player's behalf, keeping AutoQuality on.
        /// Returns the new preset, or null when already at Low or the player has chosen their own settings.
        /// </summary>
        public string StepDownPreset()
        {
            var g = Data.Graphics;
            if (!g.AutoQuality) return null;
            var i = Array.IndexOf(Presets, g.Preset);
            if (i <= 0) return null;
            var next = Presets[i - 1];
            PresetValues(g, next);
            Save();
            Bus.Emit(new SettingsChanged { Section = "graphics" });
            return next;
        }

        public void ResetSection(string section)
        {
            var d = Defaults();
            switch (section)
            {
                case "gameplay": Data.Gameplay = d.Gameplay; break;
                case "graphics": Data.Graphics = d.Graphics; break;
                case "audio": Data.Audio = d.Audio; break;
                case "controls": Data.Controls = d.Controls; break;
                case "accessibility": Data.Accessibility = d.Accessibility; break;
                case "language": Data.Language = d.Language; break;
            }
            Save();
            Bus.Emit(new SettingsChanged { Section = section });
        }

        /// <summary>Effective camera-shake scale (gameplay setting x accessibility cap).</summary>
        public float ShakeScale => Data.Gameplay.CameraShake * Data.Accessibility.CameraShake;

        public DifficultyMods Difficulty => Data.Gameplay.Difficulty switch
        {
            "story" => new DifficultyMods(0.5f, 0.75f, 1.5f, 0.75f),
            "hard" => new DifficultyMods(1.45f, 1.3f, 0.8f, 1.3f),
            _ => new DifficultyMods(1, 1, 1, 1),
        };
    }
}
