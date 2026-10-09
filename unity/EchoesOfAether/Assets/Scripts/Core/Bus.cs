using System;
using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Typed global event bus. Gameplay systems (quests, audio, UI) subscribe here instead of
    /// referencing each other directly. Each event is a small struct.
    /// </summary>
    public static class Bus
    {
        static readonly Dictionary<Type, List<Delegate>> handlers = new();

        /// <summary>Subscribe; returns an action that unsubscribes.</summary>
        public static Action On<T>(Action<T> handler) where T : struct
        {
            if (!handlers.TryGetValue(typeof(T), out var list)) handlers[typeof(T)] = list = new List<Delegate>();
            list.Add(handler);
            return () => Off(handler);
        }

        public static void Off<T>(Action<T> handler) where T : struct
        {
            if (handlers.TryGetValue(typeof(T), out var list)) list.Remove(handler);
        }

        static int depth;
        static bool reportedLoop;

        public static void Emit<T>(T payload) where T : struct
        {
            if (!handlers.TryGetValue(typeof(T), out var list) || list.Count == 0) return;
            // Guard against event loops (a handler re-emitting what it handles): report once and drop the event
            // instead of overflowing the stack.
            if (depth > 24)
            {
                if (!reportedLoop) { reportedLoop = true; Debug.LogError($"[bus] event loop detected while emitting {typeof(T).Name}:\n{Environment.StackTrace}"); }
                return;
            }
            depth++;
            try
            {
                // Copy so handlers may unsubscribe while being dispatched.
                foreach (var d in list.ToArray())
                {
                    try { ((Action<T>)d)(payload); }
                    catch (Exception e) { Debug.LogError($"[bus] handler for {typeof(T).Name} failed: {e}"); }
                }
            }
            finally { depth--; }
        }

        /// <summary>Drop every subscription (tests, returning to the menu).</summary>
        public static void Clear() => handlers.Clear();
    }

    public enum ToastKind { Info, Quest, Item, Warn, Lore }

    public struct EnemyKilled { public int Id; public string Type; public string[] Tags; public string SpawnId; public string Zone; }
    public struct EnemyDamaged { public int Id; public string Type; public float Amount; }
    public struct EnemyAggro { public int Id; public string Type; }
    public struct PlayerDamaged { public float Amount; public string Source; }
    public struct PlayerDied { public string Zone; }
    public struct PlayerRespawned { public string Zone; }
    public struct PlayerLanded { public float Speed; }
    public struct AbilityUsed { public string Ability; public string Character; }
    public struct AbilityUnlocked { public string Ability; }
    public struct ItemAdded { public string Id; public int Qty; public int Total; }
    public struct ItemRemoved { public string Id; public int Qty; public int Total; }
    public struct PowerupActivated { public string Id; public float Duration; }
    public struct PowerupExpired { public string Id; }
    public struct CollectibleFound { public string Id; public string Kind; }
    public struct Interacted { public string Id; public string Kind; }
    public struct TriggerEnter { public string Id; }
    public struct TriggerExit { public string Id; }
    public struct ZoneEntered { public string Zone; public string Entry; }
    public struct ZoneLeaving { public string Zone; }
    public struct FlagSet { public string Flag; public object Value; }
    public struct QuestStarted { public string Id; }
    public struct QuestStage { public string Id; public string Stage; }
    public struct QuestObjective { public string Id; public string Objective; public int Progress; public int Required; }
    public struct QuestCompleted { public string Id; }
    public struct DialogueStarted { public string Id; }
    public struct DialogueEnded { public string Id; }
    public struct DialogueChoiceMade { public string Id; public string Node; public string Choice; }
    public struct CinematicStarted { public string Id; }
    public struct CinematicEnded { public string Id; public bool Skipped; }
    public struct PuzzleSolved { public string Id; }
    public struct EncounterStarted { public string Id; }
    public struct EncounterCleared { public string Id; }
    public struct Talked { public string Npc; }
    public struct PickedUp { public string Id; }
    public struct CharacterSwapped { public string Character; }
    public struct SaveWritten { public int Slot; public string Kind; }
    public struct SaveFailed { public int Slot; public string Reason; }
    public struct CheckpointReached { public string Id; }
    public struct CombatState { public bool InCombat; }
    public struct BossPhase { public string Id; public int Phase; }
    public struct SettingsChanged { public string Section; }
    public struct Toast { public string Text; public ToastKind Kind; }
    public struct Lightning { public float Intensity; }
}
