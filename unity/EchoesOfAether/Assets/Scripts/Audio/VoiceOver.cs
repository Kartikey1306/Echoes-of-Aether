using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Plays human-recorded voice-over for dialogue lines when a recording exists:
    ///   Resources/Audio/Voice/&lt;dialogueId&gt;/&lt;nodeId&gt; (wav or ogg; see docs/VO_SCRIPT.md for every line to record).
    /// No speech is synthesised: lines without a recording stay subtitle-only. Music is ducked under speech and the
    /// dialogue view holds auto-paced lines for at least the clip length.
    /// </summary>
    public sealed class VoiceOver : MonoBehaviour
    {
        public static VoiceOver Instance { get; private set; }
        AudioSource src;
        string currentKey;
        bool ducked, pausedByGame;

        /// <summary>Seconds left of the line being spoken (0 when silent).</summary>
        public static float Remaining
        {
            get
            {
                var s = Instance != null ? Instance.src : null;
                return s != null && s.isPlaying && s.clip != null ? Mathf.Max(0, s.clip.length - s.time) : 0;
            }
        }

        public static VoiceOver Create(Transform parent)
        {
            var go = new GameObject("VoiceOver");
            go.transform.SetParent(parent, false);
            var v = go.AddComponent<VoiceOver>();
            v.src = go.AddComponent<AudioSource>();
            v.src.playOnAwake = false;
            v.src.spatialBlend = 0;
            v.src.priority = 16;
            Instance = v;
            Bus.On<DialogueLineShown>(e => v.Speak(e.Dialogue, e.Node, e.Speaker));
            Bus.On<DialogueEnded>(_ => v.Stop());
            Bus.On<CinematicEnded>(e => { if (e.Skipped) v.Stop(); });
            return v;
        }

        /// <summary>
        /// Lines spoken by "the active hero"/"the partner" depend on who the player chose: those recordings are
        /// named &lt;node&gt;_kael / &lt;node&gt;_lyra; every other line is &lt;node&gt;.
        /// </summary>
        public void Speak(string dialogue, string node, string speaker = null)
        {
            if (string.IsNullOrEmpty(dialogue) || string.IsNullOrEmpty(node)) return;
            if (!Enabled) { Stop(); return; }
            var key = dialogue + "/" + node;
            if (key == currentKey && src.isPlaying) return;
            currentKey = key;
            AudioClip clip = null;
            if (!string.IsNullOrEmpty(speaker)) clip = Resources.Load<AudioClip>("Audio/Voice/" + key + "_" + speaker);
            if (clip == null) clip = Resources.Load<AudioClip>("Audio/Voice/" + key);
            if (clip == null) { Stop(); return; }
            src.Stop();
            src.clip = clip;
            src.volume = Volume;
            src.Play();
            if (!ducked) { G.Audio?.Duck(0.45f, 0.25f); ducked = true; }
        }

        public void Stop()
        {
            if (src != null && src.isPlaying) src.Stop();
            currentKey = null;
            if (ducked) { G.Audio?.Duck(0, 0.6f); ducked = false; }
        }

        /// <summary>Off by default: the player opts in when starting a game (or in Settings → Audio).</summary>
        public static bool Enabled => G.Settings?.Data?.Audio?.VoiceOver ?? false;

        static float Volume
        {
            get
            {
                var a = G.Settings?.Data?.Audio;
                // Same perceptual (squared) curve as the other buses.
                return a != null ? a.Master * a.Master * a.Voice * a.Voice : 0.7f;
            }
        }

        void Update()
        {
            if (src == null) return;
            var paused = G.Manager != null && G.Manager.Paused;
            if (paused && src.isPlaying) { src.Pause(); pausedByGame = true; }
            else if (!paused && pausedByGame) { src.UnPause(); pausedByGame = false; }
            if (src.isPlaying && !Enabled) Stop();
            if (src.isPlaying) src.volume = Volume;
            else if (ducked && !pausedByGame) { G.Audio?.Duck(0, 0.6f); ducked = false; }
        }
    }
}
