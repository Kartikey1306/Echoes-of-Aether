namespace EOA
{
    public enum GameMode { Boot, Menu, CharSelect, Loading, Play, Credits }

    /// <summary>
    /// Service locator for the running game. GameManager fills these during boot; modules read them
    /// instead of holding cross references.
    /// </summary>
    public static class G
    {
        public static GameManager Manager;
        public static GameInput Input;
        public static Settings Settings;
        public static SaveSystem Saves;
        public static IAudio Audio;
        public static IVfx Vfx;
        public static IWorld World;
        public static IPresentation Presentation;

        public static GameState State => Manager != null ? Manager.State : null;
        public static Inventory Inventory => Manager != null ? Manager.Inventory : null;
        public static Progression Progression => Manager != null ? Manager.Progression : null;
        public static QuestSystem Quests => Manager != null ? Manager.Quests : null;
        public static DialogueSystem Dialogue => Manager != null ? Manager.Dialogue : null;
        public static Powerups Powerups => Manager != null ? Manager.Powerups : null;
    }
}
