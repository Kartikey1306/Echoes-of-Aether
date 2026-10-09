using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace EOA
{
    /// <summary>Crash-safe file writes: temp file, verify, then replace.</summary>
    public static class SafeFile
    {
#if UNITY_WEBGL && !UNITY_EDITOR
        [DllImport("__Internal")] static extern void EOA_SyncFS();
#endif
        public static void WriteAtomic(string path, string text)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, text, Encoding.UTF8);
            if (File.ReadAllText(tmp, Encoding.UTF8) != text) throw new IOException("temp file verification failed");
            try
            {
                if (File.Exists(path)) File.Replace(tmp, path, null);
                else File.Move(tmp, path);
            }
            catch (Exception e) when (e is PlatformNotSupportedException || e is NotSupportedException)
            {
                // Some virtual file systems (WebGL IDBFS) lack replace; copy over the verified temp instead.
                File.Copy(tmp, path, true);
                File.Delete(tmp);
            }
            Flush();
        }

        public static void Delete(string path)
        {
            if (File.Exists(path)) File.Delete(path);
            Flush();
        }

        /// <summary>WebGL keeps persistentDataPath in IndexedDB; push writes through immediately.</summary>
        public static void Flush()
        {
#if UNITY_WEBGL && !UNITY_EDITOR
            try { EOA_SyncFS(); } catch { }
#endif
        }
    }

    public enum SaveKind { Manual, Auto, Checkpoint }

    public sealed class SaveEnvelope
    {
        public string Magic;
        public int Version;
        public int Slot;
        public string Kind;
        public string Timestamp;
        public float Playtime;
        public string Zone, Character, Mission;
        public string Thumbnail; // base64 JPEG
        public string Checksum;
        public GameStateData State;
        public SettingsData Settings;
    }

    public sealed class SlotInfo
    {
        public int Slot;
        public string Status; // ok | empty | corrupt | recovered (main damaged, backup available)
        public SaveEnvelope Envelope, Backup;
        public string Error;
    }

    /// <summary>
    /// Three save slots with checksums, schema validation, a rolling backup per slot, atomic writes
    /// and post-write verification. Damaged files are detected and recovered from the backup.
    /// </summary>
    public sealed class SaveSystem
    {
        public const int SlotCount = 3;
        const string Magic = "EOA-SAVE";
        const int FormatVersion = 1;
        readonly string dir;
        public int ActiveSlot = 1;
        public bool Writing { get; private set; }
        public float LastSaveTime = -999;

        public SaveSystem(string root = null) { dir = Path.Combine(root ?? Application.persistentDataPath, "saves"); }

        public string MainPath(int slot) => Path.Combine(dir, $"slot{slot}.json");
        public string BackupPath(int slot) => Path.Combine(dir, $"slot{slot}.bak.json");

        static readonly uint[] crcTable = Enumerable.Range(0, 256).Select(n =>
        {
            var c = (uint)n;
            for (var k = 0; k < 8; k++) c = (c & 1) != 0 ? 0xEDB88320u ^ (c >> 1) : c >> 1;
            return c;
        }).ToArray();

        public static string Crc32(string s)
        {
            var c = 0xFFFFFFFFu;
            foreach (var b in Encoding.UTF8.GetBytes(s)) c = crcTable[(c ^ b) & 0xFF] ^ (c >> 8);
            return (c ^ 0xFFFFFFFFu).ToString("x8");
        }

        static string StateJson(GameStateData s) => JsonConvert.SerializeObject(s, Formatting.None, GameData.Json);

        /// <summary>Parse and fully validate a save file's text.</summary>
        public static (SaveEnvelope env, string error) Parse(string raw)
        {
            if (string.IsNullOrEmpty(raw)) return (null, null);
            SaveEnvelope env;
            try
            {
                var obj = JObject.Parse(raw);
                env = obj.ToObject<SaveEnvelope>(JsonSerializer.Create(GameData.Json));
                if (env == null) return (null, "File is empty");
                if (env.Magic != Magic) return (null, "Not a save file");
                if (env.Version > FormatVersion) return (null, $"Save is from a newer version ({env.Version})");
                // Checksum over the state exactly as stored.
                var stateTok = obj["state"];
                if (stateTok == null) return (null, "State missing");
                if (Crc32(stateTok.ToString(Formatting.None)) != env.Checksum) return (null, "Checksum mismatch (file damaged)");
            }
            catch (Exception e) { return (null, "File is not valid JSON" + (Debug.isDebugBuild ? $" ({e.Message})" : "")); }
            var err = GameState.Validate(env.State);
            if (err != null) return (null, "Invalid state: " + err);
            return (env, null);
        }

        static string Read(string path)
        {
            try { return File.Exists(path) ? File.ReadAllText(path, Encoding.UTF8) : null; }
            catch (Exception e) { Debug.LogWarning($"[save] read failed {path}: {e.Message}"); return null; }
        }

        public SlotInfo Info(int slot)
        {
            var main = Parse(Read(MainPath(slot)));
            var bak = Parse(Read(BackupPath(slot)));
            if (main.env != null) return new SlotInfo { Slot = slot, Status = "ok", Envelope = main.env, Backup = bak.env };
            if (main.error != null) return new SlotInfo { Slot = slot, Status = bak.env != null ? "recovered" : "corrupt", Backup = bak.env, Error = main.error };
            return new SlotInfo { Slot = slot, Status = bak.env != null ? "recovered" : "empty", Backup = bak.env };
        }

        public List<SlotInfo> AllInfo() => Enumerable.Range(1, SlotCount).Select(Info).ToList();

        /// <summary>Most recent loadable save across slots (main file, or backup if the main is damaged).</summary>
        public SaveEnvelope Latest()
        {
            SaveEnvelope best = null;
            foreach (var i in AllInfo())
            {
                var e = i.Envelope ?? i.Backup;
                if (e != null && (best == null || string.CompareOrdinal(e.Timestamp, best.Timestamp) > 0)) best = e;
            }
            return best;
        }

        public bool Write(int slot, SaveKind kind, GameStateData state, SettingsData settings, string thumbnail = "")
        {
            if (Writing) { Debug.LogWarning("[save] write skipped: another write in progress"); return false; }
            Writing = true;
            try { return Finish(slot, kind, Commit(slot, kind, StateJson(state), SettingsJson(settings), thumbnail)); }
            finally { Writing = false; }
        }

        /// <summary>
        /// Same as <see cref="Write"/>, but only the state snapshot is taken on the calling (main) thread; validation,
        /// envelope, backup and the verified file writes run on a worker thread (autosaves on zone entry were a 40-80 ms
        /// frame with ~0.5 MB of garbage). WebGL has no threads and writes synchronously.
        /// </summary>
        public async Awaitable<bool> WriteAsync(int slot, SaveKind kind, GameStateData state, SettingsData settings, string thumbnail = "")
        {
            if (Writing) { Debug.LogWarning("[save] write skipped: another write in progress"); return false; }
            Writing = true;
            try
            {
                var stateJson = StateJson(state);
                var settingsJson = SettingsJson(settings);
                string err;
#if UNITY_WEBGL && !UNITY_EDITOR
                err = Commit(slot, kind, stateJson, settingsJson, thumbnail);
#else
                await Awaitable.BackgroundThreadAsync();
                try { err = Commit(slot, kind, stateJson, settingsJson, thumbnail); }
                catch (Exception e) { err = e.Message; }
                await Awaitable.MainThreadAsync();
#endif
                return Finish(slot, kind, err);
            }
            finally { Writing = false; }
        }

        static string SettingsJson(SettingsData s) => s != null ? JsonConvert.SerializeObject(s, Formatting.None, GameData.Json) : null;

        bool Finish(int slot, SaveKind kind, string error)
        {
            if (error != null)
            {
                Debug.LogError($"[save] write failed: {error}");
                Bus.Emit(new SaveFailed { Slot = slot, Reason = error });
                return false;
            }
            LastSaveTime = Time.realtimeSinceStartup;
            Bus.Emit(new SaveWritten { Slot = slot, Kind = kind.ToString().ToLowerInvariant() });
            return true;
        }

        /// <summary>Build, back up, write and verify a save from JSON snapshots. No Unity API: safe on a worker thread.</summary>
        string Commit(int slot, SaveKind kind, string stateJson, string settingsJson, string thumbnail)
        {
            try
            {
                var stateCopy = JsonConvert.DeserializeObject<GameStateData>(stateJson, GameData.Json);
                var err = GameState.Validate(stateCopy);
                if (err != null) throw new Exception("refusing to write invalid state: " + err);
                var mission = stateCopy.Quests.Where(kv => kv.Value.Status == "active").Select(kv => GameData.Quests.TryGetValue(kv.Key, out var q) ? q : null)
                    .FirstOrDefault(q => q != null && q.IsMain)?.Title ?? (new GameState(stateCopy).Flag("game_complete") ? "Epilogue" : "Aether-9");
                var stateTok = JToken.FromObject(stateCopy, JsonSerializer.Create(GameData.Json));
                var envObj = new JObject
                {
                    ["magic"] = Magic,
                    ["version"] = FormatVersion,
                    ["slot"] = slot,
                    ["kind"] = kind.ToString().ToLowerInvariant(),
                    ["timestamp"] = DateTime.UtcNow.ToString("o"),
                    ["playtime"] = stateCopy.Stats.Playtime,
                    ["zone"] = stateCopy.Zone,
                    ["character"] = stateCopy.Character,
                    ["mission"] = mission,
                    ["thumbnail"] = thumbnail ?? "",
                    ["checksum"] = Crc32(stateTok.ToString(Formatting.None)),
                    ["state"] = stateTok,
                    ["settings"] = settingsJson != null ? JToken.Parse(settingsJson) : JValue.CreateNull(),
                };
                var data = envObj.ToString(Formatting.None);
                // Keep the previous valid save as a backup before committing the new one.
                var prev = Read(MainPath(slot));
                if (prev != null && Parse(prev).env != null) SafeFile.WriteAtomic(BackupPath(slot), prev);
                SafeFile.WriteAtomic(MainPath(slot), data);
                var check = Parse(Read(MainPath(slot)));
                if (check.env == null) throw new Exception("post-write verification failed: " + check.error);
                return null;
            }
            catch (Exception e) { return e.Message; }
        }

        public SaveEnvelope Load(int slot, bool preferBackup = false)
        {
            var i = Info(slot);
            return preferBackup ? i.Backup : i.Envelope ?? i.Backup;
        }

        /// <summary>Replace a damaged main file with its backup.</summary>
        public bool Recover(int slot)
        {
            var bakRaw = Read(BackupPath(slot));
            if (bakRaw == null || Parse(bakRaw).env == null) return false;
            SafeFile.WriteAtomic(MainPath(slot), bakRaw);
            return true;
        }

        public void Delete(int slot)
        {
            SafeFile.Delete(MainPath(slot));
            SafeFile.Delete(BackupPath(slot));
        }
    }
}
