using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Safety net: if Play is pressed in a scene without a GameManager (e.g. an empty scene), create one so the game
    /// always starts at the main menu. The Boot scene normally contains it already.
    /// </summary>
    static class Bootstrap
    {
        // Automated test runs (Unity -batchmode) and benchmark players stay silent so they don't play through the speakers;
        // set EOA_SOUND=1 to hear one.
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
        static void MuteBatchRuns()
        {
            var benchmark = System.Array.IndexOf(System.Environment.GetCommandLineArgs(), "-benchmark") >= 0;
            if ((Application.isBatchMode || benchmark) && System.Environment.GetEnvironmentVariable("EOA_SOUND") != "1") AudioListener.volume = 0f;
        }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        static void EnsureGameManager()
        {
            if (Object.FindAnyObjectByType<GameManager>() != null) return;
            new GameObject("GameManager").AddComponent<GameManager>();
        }
    }
}
