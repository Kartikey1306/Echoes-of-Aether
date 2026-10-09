using UnityEditor;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Import settings for the rendered audio in Assets/Resources/Audio (see tools/audio/render.mjs):
    ///   SFX/, Thunder/  one-shots: mono, Decompress On Load, Vorbis q0.7 (decoded once, cheap to trigger often).
    ///   Music/          long loops: Streaming, Vorbis q0.6, Load In Background.
    ///   Ambience/       loops: Compressed In Memory, Vorbis q0.5, Load In Background.
    /// WebGL ignores load type/format (the browser decodes AAC), so no WebGL override is set.
    /// </summary>
    public sealed class AudioImportPostprocessor : AssetPostprocessor
    {
        const string Root = "Assets/Resources/Audio/";

        // Bump when the rules below change so Unity re-imports the clips.
        public override uint GetVersion() => 1;

        void OnPreprocessAudio()
        {
            string path = assetPath.Replace('\\', '/');
            if (!path.StartsWith(Root, System.StringComparison.OrdinalIgnoreCase)) return;
            if (assetImporter is not AudioImporter importer) return;

            string sub = path.Substring(Root.Length);
            var s = importer.defaultSampleSettings;
            s.sampleRateSetting = AudioSampleRateSetting.PreserveSampleRate;
            importer.ambisonic = false;

            if (sub.StartsWith("Music/", System.StringComparison.OrdinalIgnoreCase))
            {
                importer.forceToMono = false;
                importer.loadInBackground = true;
                s.loadType = AudioClipLoadType.Streaming;
                s.compressionFormat = AudioCompressionFormat.Vorbis;
                s.quality = 0.6f;
            }
            else if (sub.StartsWith("Ambience/", System.StringComparison.OrdinalIgnoreCase))
            {
                importer.forceToMono = false;
                importer.loadInBackground = true;
                s.loadType = AudioClipLoadType.CompressedInMemory;
                s.compressionFormat = AudioCompressionFormat.Vorbis;
                s.quality = 0.5f;
            }
            else if (sub.StartsWith("Voice/", System.StringComparison.OrdinalIgnoreCase))
            {
                // Recorded voice-over: mono, compressed in memory (lines are a few seconds; loaded on demand).
                importer.forceToMono = true;
                importer.loadInBackground = true;
                s.loadType = AudioClipLoadType.CompressedInMemory;
                s.compressionFormat = AudioCompressionFormat.Vorbis;
                s.quality = 0.7f;
            }
            else
            {
                // SFX/, Thunder/ and anything else under Resources/Audio: short one-shots.
                importer.forceToMono = true;
                DisableMonoNormalize(importer); // clips are already peak-normalized; the manifest gain relies on that
                importer.loadInBackground = false;
                s.loadType = AudioClipLoadType.DecompressOnLoad;
                s.compressionFormat = AudioCompressionFormat.Vorbis;
                s.quality = 0.7f;
            }
            importer.defaultSampleSettings = s;
        }

        /// <summary>"Normalize" (shown under Force To Mono) has no public API; clear it through the serialized importer.</summary>
        static void DisableMonoNormalize(AudioImporter importer)
        {
            var so = new SerializedObject(importer);
            var prop = so.FindProperty("m_Normalize");
            if (prop == null || prop.propertyType != SerializedPropertyType.Boolean || !prop.boolValue) return;
            prop.boolValue = false;
            so.ApplyModifiedPropertiesWithoutUndo();
        }
    }
}
