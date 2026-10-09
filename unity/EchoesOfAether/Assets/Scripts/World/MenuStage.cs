using UnityEngine;

namespace EOA
{
    /// <summary>
    /// 3D stage behind the main menu, character select and character designer: a rain-swept rooftop at night
    /// with Kael and Lyra on lit platforms. Framing is applied through the camera rig's cinematic override.
    /// Studio-style key/fill/rim lighting keeps faces readable (no dark lower faces).
    /// </summary>
    public sealed class MenuStage : MonoBehaviour, IMenuStage
    {
        enum Mode { Menu, Select, Designer }
        Mode mode;
        string focus = Characters.Kael;
        bool faceShot;
        readonly CharacterModel[] heroes = new CharacterModel[2];
        readonly Transform[] pads = new Transform[2];
        readonly float[] spin = new float[2];
        Light key, fill, rim;
        Vector3 camPos, camLook;
        float fov = 40;
        GameObject root;

        public static MenuStage Create(Transform parent)
        {
            var go = new GameObject("MenuStage");
            go.transform.SetParent(parent, false);
            var s = go.AddComponent<MenuStage>();
            s.Build();
            return s;
        }

        static readonly Vector3 KaelPad = new(-1.3f, 0, 1.5f), LyraPad = new(1.3f, 0, 1.5f);

        void Build()
        {
            root = new GameObject("Stage");
            root.transform.SetParent(transform, false);
            root.transform.position = new Vector3(0, -500, 0); // far below the zones, never visible from gameplay
            var floorMat = FxMaterials.Lit(new Color(0.09f, 0.1f, 0.11f), 0.1f, 0.78f, "stage_floor");
            var padMat = FxMaterials.Lit(new Color(0.13f, 0.14f, 0.16f), 0.75f, 0.55f, "stage_pad");
            var floor = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            floor.transform.SetParent(root.transform, false);
            floor.transform.localScale = new Vector3(14, 0.05f, 14);
            floor.transform.localPosition = new Vector3(0, -0.05f, 0);
            floor.GetComponent<Renderer>().sharedMaterial = floorMat;
            for (var i = 0; i < 2; i++)
            {
                var pad = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                pad.transform.SetParent(root.transform, false);
                pad.transform.localPosition = (i == 0 ? KaelPad : LyraPad) + new Vector3(0, 0.03f, 0);
                pad.transform.localScale = new Vector3(1.9f, 0.06f, 1.9f);
                pad.GetComponent<Renderer>().sharedMaterial = padMat;
                var ring = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
                ring.transform.SetParent(pad.transform, false);
                ring.transform.localPosition = new Vector3(0, 0.55f, 0);
                ring.transform.localScale = new Vector3(1.02f, 0.1f, 1.02f);
                var rm = FxMaterials.Lit(Color.black, 0, 0.8f, "stage_ring");
                rm.EnableKeyword("_EMISSION");
                rm.SetColor("_EmissionColor", FxMaterials.Hdr(i == 0 ? new Color(0.37f, 0.85f, 1f) : new Color(0.65f, 0.48f, 1f), 1.6f));
                ring.GetComponent<Renderer>().sharedMaterial = rm;
                pads[i] = pad.transform;
            }
            // Portrait lighting: a neutral-warm key from high on the heroes' right (screen left), well off the camera axis, so brows,
            // cheekbones and jaw model with shadow (a frontal warm key flattened faces and turned skin orange); a weaker
            // cool fill on the opposite side of the camera; two subtle coloured rims from behind (cyan left, magenta
            // right) that separate the silhouettes from the dark backdrop.
            key = MakeLight("Key", LightType.Directional, new Color(1f, 0.96f, 0.92f), 2.3f, Quaternion.Euler(38, 215, 0));
            key.shadows = LightShadows.Soft;
            // Half-strength shadows: thin hair cards otherwise stripe the cheeks in face close-ups.
            key.shadowStrength = 0.45f;
            fill = MakeLight("Fill", LightType.Point, new Color(0.74f, 0.84f, 1f), 1.5f, Quaternion.identity);
            fill.range = 7;
            rim = MakeLight("Rim", LightType.Spot, new Color(0.35f, 0.85f, 1f), 30f, Quaternion.identity);
            rim.range = 12; rim.spotAngle = 60;
            rim.transform.localPosition = new Vector3(-2.6f, 3.0f, -1.6f);
            rim.transform.LookAt(root.transform.TransformPoint(new Vector3(-0.4f, 1.2f, 1.5f)));
            var rim2 = MakeLight("Rim2", LightType.Spot, new Color(1f, 0.38f, 0.86f), 26f, Quaternion.identity);
            rim2.range = 12; rim2.spotAngle = 60;
            rim2.transform.localPosition = new Vector3(2.6f, 3.0f, -1.6f);
            rim2.transform.LookAt(root.transform.TransformPoint(new Vector3(0.4f, 1.2f, 1.5f)));
            SpawnHeroes();
            EnterMenu();
        }

        Light MakeLight(string n, LightType t, Color c, float intensity, Quaternion rot)
        {
            var go = new GameObject(n);
            go.transform.SetParent(root.transform, false);
            go.transform.localRotation = rot;
            var l = go.AddComponent<Light>();
            l.type = t; l.color = c; l.intensity = intensity;
            return l;
        }

        void SpawnHeroes()
        {
            for (var i = 0; i < 2; i++)
            {
                var id = i == 0 ? Characters.Kael : Characters.Lyra;
                if (heroes[i] != null) Destroy(heroes[i].gameObject);
                var prefab = Resources.Load<GameObject>("Characters/" + Characters.AssetName(id));
                if (prefab == null) continue;
                var go = Instantiate(prefab, root.transform);
                go.transform.localPosition = (i == 0 ? KaelPad : LyraPad) + new Vector3(0, 0.06f, 0);
                // Models face +Z, toward the camera; each turns slightly toward the centre of the stage.
                go.transform.localRotation = Quaternion.Euler(0, i == 0 ? 12 : -12, 0);
                heroes[i] = go.GetComponent<CharacterModel>();
                // Heroic standing pose on the pedestal (full body; the raw mocap idle reads as bent / knock-kneed).
                if (go.GetComponent<HeroStance>() == null) go.AddComponent<HeroStance>();
                heroes[i]?.ApplyAppearance(G.Manager != null ? G.Manager.AppearanceFor(id) : Appearance.Default(id));
            }
        }

        public void Show(bool on) => root.SetActive(on);

        public void SetAppearance(string character, Appearance a)
        {
            var i = character == Characters.Kael ? 0 : 1;
            heroes[i]?.ApplyAppearance(a);
        }

        Vector3 W(Vector3 local) => root.transform.TransformPoint(local);

        public void EnterMenu()
        {
            mode = Mode.Menu;
            camPos = W(new Vector3(0.6f, 1.55f, 6.4f));
            camLook = W(new Vector3(0, 1.25f, 1.5f));
            fov = 38;
        }

        public void Focus(string character)
        {
            mode = Mode.Select;
            focus = character;
            var pad = character == Characters.Kael ? KaelPad : LyraPad;
            camPos = W(pad + new Vector3(character == Characters.Kael ? 1.0f : -1.0f, 1.35f, 4.2f));
            camLook = W(pad + new Vector3(character == Characters.Kael ? 0.75f : -0.75f, 1.0f, 0));
            fov = 34;
        }

        public void Rotate(float deltaDegrees)
        {
            var i = focus == Characters.Kael ? 0 : 1;
            spin[i] += deltaDegrees;
        }

        public void EnterDesigner(string character)
        {
            mode = Mode.Designer;
            focus = character;
            faceShot = false;
            Frame();
        }

        public void FocusFace(bool face)
        {
            faceShot = face;
            Frame();
        }

        void Frame()
        {
            var i = focus == Characters.Kael ? 0 : 1;
            var pad = focus == Characters.Kael ? KaelPad : LyraPad;
            var h = heroes[i] != null ? heroes[i].BaseHeight * heroes[i].transform.localScale.y : 1.8f;
            if (faceShot)
            {
                camPos = W(pad + new Vector3(-0.55f, h - 0.1f, 1.15f));
                camLook = W(pad + new Vector3(-0.18f, h - 0.13f, 0));
                fov = 26;
            }
            else
            {
                camPos = W(pad + new Vector3(-1.2f, h * 0.62f, 4.0f));
                camLook = W(pad + new Vector3(-0.6f, h * 0.52f, 0));
                fov = 36;
            }
        }

        public void Tick(float dt)
        {
            if (!root.activeSelf) return;
            var cam = G.Manager?.Cam;
            if (cam != null)
            {
                var cur = cam.Cinematic ?? (camPos, camLook, fov);
                var k = 1 - Mathf.Exp(-4 * dt);
                cam.Cinematic = (Vector3.Lerp(cur.pos, camPos, k), Vector3.Lerp(cur.look, camLook, k), Mathf.Lerp(cur.fov, fov, k));
                // Fill sits at a fixed distance from the subject, swung 45 deg from the camera away from the key side, so
                // the shadow side keeps a cool, readable value without flattening the face.
                var toCam = camPos - camLook; toCam.y = 0;
                var dir = Quaternion.Euler(0, -45, 0) * (toCam.sqrMagnitude > 1e-4f ? toCam.normalized : Vector3.forward);
                fill.transform.position = camLook + dir * 1.8f + Vector3.up * 0.15f;
            }
            for (var i = 0; i < 2; i++)
            {
                if (heroes[i] == null) continue;
                var baseYaw = (i == 0 ? 12 : -12) + spin[i];
                var t = heroes[i].transform;
                t.localRotation = Quaternion.Slerp(t.localRotation, Quaternion.Euler(0, baseYaw, 0), 1 - Mathf.Exp(-8 * dt));
            }
        }
    }
}
