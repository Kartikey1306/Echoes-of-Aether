using System;
using System.Collections.Generic;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Player-editable look of a protagonist. Body/face values are signed morph amounts (-1..1) that map onto
    /// the character's blendshapes ("{name}_incr" / "{name}_decr"); colours tint the materials; style ids
    /// select meshes exported in the character FBX.
    /// </summary>
    [Serializable]
    public sealed class Appearance
    {
        // Body
        public float Height;      // -1..1 -> uniform scale 0.94..1.06
        public float Muscle, Weight, Shoulders, Hips, Bust;
        // Face
        public float Jaw, Chin, Cheeks, NoseSize, NoseWidth, Lips, EyeSize, BrowHeight, Age;
        // Colours (hex)
        public string Skin = "#b98a6e", Eyes = "#5b3a22", Hair = "#1d1714";
        public string Outfit = "#33363c", Accent = "#25272c", Armor = "#4b4e54", Glow = "#56b8ff", Glow2 = "#56b8ff";
        // Styles
        public string HairStyle = "short", FacialHair = "none";
        public float Stubble;
        /// <summary>Glowing cyberpunk tattoo colour and strength (0 = ink only).</summary>
        /// <summary>Catalog attachments (Resources/Characters/Custom/catalog.json): "none" = not worn.</summary>
        public string Eyewear = "none", ArmorSet = "none", TattooDesign = "";
        public string Tattoo = "#00e5ff";
        public float TattooGlow = 1f;
        public bool Scar, ShoulderPads = true, ChestPlate = true, KneePads = true, Gloves = true, Backpack = true; // Backpack = Lyra's utility harness
        /// <summary>Look revision of a saved appearance (2 = curly defaults retired; see Sanitized).</summary>
        public int LookVersion;

        /// <summary>Former default hair styles, replaced once in saved looks by the current default.</summary>
        static readonly string[] RetiredDefaultHair = { "curly_medium", "curly", "long_curls" };

        public Appearance Clone() => (Appearance)MemberwiseClone();

        public static readonly string[] BodyMorphs = { "muscle", "weight", "shoulders", "hips", "bust" };
        public static readonly string[] FaceMorphs = { "jaw", "chin", "cheeks", "noseSize", "noseWidth", "lips", "eyeSize", "browHeight", "age" };

        public float Get(string morph) => morph switch
        {
            "muscle" => Muscle, "weight" => Weight, "shoulders" => Shoulders, "hips" => Hips, "bust" => Bust,
            "jaw" => Jaw, "chin" => Chin, "cheeks" => Cheeks, "noseSize" => NoseSize, "noseWidth" => NoseWidth,
            "lips" => Lips, "eyeSize" => EyeSize, "browHeight" => BrowHeight, "age" => Age, "height" => Height,
            _ => 0,
        };

        public void Set(string morph, float v)
        {
            v = Mathf.Clamp(v, -1, 1);
            switch (morph)
            {
                case "muscle": Muscle = v; break; case "weight": Weight = v; break; case "shoulders": Shoulders = v; break;
                case "hips": Hips = v; break; case "bust": Bust = v; break; case "jaw": Jaw = v; break; case "chin": Chin = v; break;
                case "cheeks": Cheeks = v; break; case "noseSize": NoseSize = v; break; case "noseWidth": NoseWidth = v; break;
                case "lips": Lips = v; break; case "eyeSize": EyeSize = v; break; case "browHeight": BrowHeight = v; break;
                case "age": Age = Mathf.Clamp01(v); break; case "height": Height = v; break;
            }
        }

        /// <summary>Clamp ranges and repair invalid colours/styles from untrusted data.</summary>
        public Appearance Sanitized(Appearance defaults)
        {
            var a = Clone();
            foreach (var m in BodyMorphs) a.Set(m, a.Get(m));
            foreach (var m in FaceMorphs) a.Set(m, a.Get(m));
            a.Height = Mathf.Clamp(a.Height, -1, 1);
            a.Stubble = Mathf.Clamp01(a.Stubble);
            string Col(string v, string d) => ColorUtility.TryParseHtmlString(v, out _) ? v : d;
            a.Skin = Col(a.Skin, defaults.Skin); a.Eyes = Col(a.Eyes, defaults.Eyes); a.Hair = Col(a.Hair, defaults.Hair);
            a.Outfit = Col(a.Outfit, defaults.Outfit); a.Accent = Col(a.Accent, defaults.Accent); a.Armor = Col(a.Armor, defaults.Armor);
            a.Glow = Col(a.Glow, defaults.Glow); a.Glow2 = Col(a.Glow2, defaults.Glow2);
            a.Tattoo = Col(a.Tattoo, defaults.Tattoo); a.TattooGlow = Mathf.Clamp(a.TattooGlow, 0, 2);
            a.Eyewear = string.IsNullOrEmpty(a.Eyewear) ? "none" : a.Eyewear;
            a.ArmorSet = string.IsNullOrEmpty(a.ArmorSet) ? "none" : a.ArmorSet;
            a.TattooDesign ??= defaults.TattooDesign ?? "";
            a.HairStyle = string.IsNullOrEmpty(a.HairStyle) ? defaults.HairStyle : a.HairStyle;
            // The user asked for no curly hair on the heroes: looks saved before that switch to the new default once.
            if (a.LookVersion < 2 && Array.IndexOf(RetiredDefaultHair, a.HairStyle) >= 0) a.HairStyle = defaults.HairStyle;
            // Remade heroes (v3): looks still on the old bland outfit defaults take the new graphite/violet ones.
            if (a.LookVersion < 3)
            {
                if (a.Outfit == "#8c8577" && a.Accent == "#2a2431") { a.Outfit = defaults.Outfit; a.Accent = defaults.Accent; }
                if (a.TattooDesign == "neon_vine") a.TattooDesign = defaults.TattooDesign;
                // Near-black default hair flattened the strand detail: old defaults take the new, slightly lighter ones.
                if (a.Hair == "#1d1714" || a.Hair == "#2a1a1e") a.Hair = defaults.Hair;
            }
            // v4 (Kael matched to the approved concept): concept hair style/colour and silver-steel armour.
            if (a.LookVersion < 4 && defaults.HairStyle == "swept_fade")
            {
                if (a.HairStyle == "side_part_volume") a.HairStyle = defaults.HairStyle;
                if (a.Hair == "#2e231c") a.Hair = defaults.Hair;
                if (a.Armor == "#a9a59a") a.Armor = defaults.Armor;
            }
            // v5: Kael's concept hair colour is mid-brown (#4a3428 rendered near-black).
            if (a.LookVersion < 5 && defaults.HairStyle == "swept_fade" && (a.Hair == "#4a3428" || a.Hair == "#2e231c")) a.Hair = defaults.Hair;
            // v6 (Giva matched to the approved concept): concept hair, bare hands, graphite/violet suit, silver armour, amber eyes.
            // Giva's concept hair is a warm dark brown: the near-black previous default read as black strings in game
            // (#3a2722 is not in the hair palette, so only untouched defaults carry it).
            // (#3a2722 / #5e3e2e are not in the hair palette, so only untouched defaults carry them; the makeover default
            // is a deeper warm brown, closer to the concept.)
            if (defaults.HairStyle == "waves" && (a.Hair == "#3a2722" || a.Hair == "#5e3e2e" || a.Hair == "#4a3026")) a.Hair = defaults.Hair;
            if (a.LookVersion < 6 && defaults.HairStyle == "waves")
            {
                if (a.HairStyle == "long_waves") a.HairStyle = defaults.HairStyle;
                if (a.Outfit == "#4a4d57" || a.Outfit == "#5a5e69") a.Outfit = defaults.Outfit;
                if (a.Accent == "#5a3f8c" || a.Accent == "#6a4bb0") a.Accent = defaults.Accent;
                if (a.Armor == "#6a6474") a.Armor = defaults.Armor;
                if (a.Eyes == "#5a3920") a.Eyes = defaults.Eyes;
                a.Gloves = defaults.Gloves;
            }
            // v7 (Kael concept pass 2): darker concept-brown hair and a browner (less green) olive for the trousers/sleeve.
            if (a.LookVersion < 7 && defaults.HairStyle == "swept_fade")
            {
                if (a.Hair == "#6b4a33") a.Hair = defaults.Hair;
                if (a.Outfit == "#4d5243") a.Outfit = defaults.Outfit;
            }
            a.LookVersion = 7;
            a.FacialHair = string.IsNullOrEmpty(a.FacialHair) ? "none" : a.FacialHair;
            return a;
        }

        public static Color ToColor(string hex) => ColorUtility.TryParseHtmlString(hex, out var c) ? c : Color.magenta;

        /// <summary>Hero defaults, with hair/tattoo defaults taken from the customization catalog when present.</summary>
        public static Appearance Default(string character)
        {
            var a = BaseDefault(character);
            var cat = CustomCatalog.Get();
            var hair = cat.Default(character, "hair");
            if (!string.IsNullOrEmpty(hair)) a.HairStyle = hair;
            var tattoo = cat.Default(character, "tattoo");
            if (!string.IsNullOrEmpty(tattoo)) a.TattooDesign = tattoo;
            return a;
        }

        static Appearance BaseDefault(string character) => character == Characters.Kael
            ? new Appearance
            {
                Skin = "#b98a6e", Eyes = "#5b3a22", Hair = "#4f3a2e", HairStyle = "swept_fade", Stubble = 0.6f, Scar = true, LookVersion = 7,
                Outfit = "#5c5848", Accent = "#1f2126", Armor = "#c9cdd3", Glow = "#00e5ff", Glow2 = "#ff2bd6",
                Tattoo = "#00e5ff", TattooGlow = 1f,
                Muscle = 0.0f, Shoulders = 0.0f, Jaw = 0.05f, Chin = 0.0f,
            }
            : new Appearance
            {
                Skin = "#c79878", Eyes = "#7a5a32", Hair = "#5a3826", HairStyle = "waves", Stubble = 0, Scar = false, LookVersion = 7,
                Outfit = "#55575e", Accent = "#5e2bb8", Armor = "#a8a4b4", Glow = "#ff2bd6", Glow2 = "#9b5cff",
                Tattoo = "#ff2bd6", TattooGlow = 1f,
                Muscle = 0.05f, Shoulders = 0.0f, Cheeks = 0.0f, Lips = 0.0f, ChestPlate = false, KneePads = false, Gloves = false, // concept: bare hands
            };

        public static readonly string[] SkinPalette = { "#f1d3bd", "#e3b796", "#d2a07c", "#c79878", "#b98a6e", "#9c6e52", "#7f5640", "#5f3f2e", "#4a2f22" };
        public static readonly string[] EyePalette = { "#5b3a22", "#3c2b1d", "#7a5a32", "#4d6a3a", "#3b5f7a", "#6f8fa8", "#5a5a5a" };
        public static readonly string[] HairPalette = { "#0f0d0c", "#1d1714", "#2e231c", "#4a3428", "#6b4a33", "#2a1a1e", "#3a2722", "#2b1b14", "#4a2e1c", "#6b4226", "#8e5a33", "#b07a45", "#d1aa6c", "#e8dcc8", "#9a9a9a", "#7a2420", "#3b2350", "#2b3550", "#5a1f45", "#1e4a5a" };
        public static readonly string[] OutfitPalette = { "#4d5243", "#8c8577", "#2f3238", "#1f2126", "#383b42", "#3d4436", "#4a4237", "#2e3a4a", "#4a2f3a", "#5a5d63" };
        public static readonly string[] GlowPalette = { "#00e5ff", "#ff2bd6", "#ff4f9a", "#3d7bff", "#9b5cff", "#ffe14d", "#5fffc8", "#ff7a2a", "#e8f4ff" };
    }

    /// <summary>Character presets offered in the designer.</summary>
    public static class AppearancePresets
    {
        public static List<(string name, Action<Appearance> apply)> For(string character) => character == Characters.Kael
            ? new()
            {
                ("Survey Lead (Default)", a => { }),
                ("Night Shift", a => { a.Outfit = "#1f2126"; a.Accent = "#25272c"; a.Armor = "#2a2c30"; a.Glow = "#62dcff"; a.HairStyle = "undercut"; a.Stubble = 0.4f; }),
                ("Field Veteran", a => { a.HairStyle = "buzz"; a.Hair = "#5a3a22"; a.FacialHair = "beard"; a.Age = 0.4f; a.Outfit = "#3d4436"; a.Accent = "#4a4237"; a.Armor = "#5a4a3a"; a.Glow = "#ffb45e"; }),
                ("Long Watch", a => { a.HairStyle = "long"; a.Hair = "#3a2416"; a.Stubble = 0.6f; a.Outfit = "#2e3a4a"; a.Armor = "#3a4a5a"; }),
            }
            : new()
            {
                ("Systems Engineer (Default)", a => { }),
                ("Phase Runner", a => { a.HairStyle = "bob"; a.Hair = "#1d1714"; a.Outfit = "#1f2126"; a.Accent = "#2b3550"; a.Glow = "#5fffc8"; a.Glow2 = "#62dcff"; }),
                ("Copper", a => { a.Hair = "#8e5a33"; a.HairStyle = "braid"; a.Skin = "#e3b796"; a.Accent = "#4a2f3a"; a.Glow = "#ffb45e"; a.Glow2 = "#ff5e7a"; }),
                ("Short Cut", a => { a.HairStyle = "short"; a.Hair = "#0f0d0c"; a.Skin = "#7f5640"; a.Outfit = "#3d4436"; a.Glow = "#a77bff"; }),
            };
    }
}
