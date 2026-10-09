namespace EOA
{
    /// <summary>Registers the staged cinematics; each zone group owns its script file.</summary>
    public static partial class CinematicScripts
    {
        static partial void RegisterZoneScripts(Cinematics c)
        {
            PlazaCinematics.Register(c);   // cin_intro, cin_meeting
            VaultCinematics.Register(c);   // cin_guardian_reveal, cin_hidden_vault
            CoreCinematics.Register(c);    // cin_ending
        }
    }
}
