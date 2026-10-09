using UnityEngine;

namespace EOA
{
    public enum PickupKind { Fragment, Recording, Cache, Quest, Powerup, Item }

    /// <summary>A collectible, quest item, powerup or drop in the world (procedural visual, bob/spin, halo, light).</summary>
    public sealed class Pickup : MonoBehaviour
    {
        public string Id;
        public PickupKind Kind;
        public string Item, PowerupId;
        public bool Auto, Hidden, Persist, Collected;
        public string[] Conditions;
        public Color Color = Color.cyan;
        Vector3 basePos;
        Transform spin, lid;
        Renderer halo;
        Light glow;
        float t;

        public Vector3 Position => basePos;

        static Mesh crystal, disc;

        public static Pickup Create(Transform parent, string id, PickupKind kind, Vector3 pos, string item = null, string powerup = null, bool auto = true, bool hidden = false, bool persist = true, string[] cond = null)
        {
            var go = new GameObject("Pickup_" + id);
            go.transform.SetParent(parent, false);
            go.transform.position = pos;
            go.layer = CombatLayers.Pickup;
            var p = go.AddComponent<Pickup>();
            p.Id = id; p.Kind = kind; p.Item = item; p.PowerupId = powerup; p.Auto = auto; p.Hidden = hidden; p.Persist = persist; p.Conditions = cond;
            p.basePos = pos;
            p.t = Random.value * 6;
            p.Color = kind switch
            {
                PickupKind.Fragment => new Color(0.37f, 0.85f, 1f),
                PickupKind.Recording => new Color(1f, 0.75f, 0.35f),
                PickupKind.Cache => new Color(0.65f, 0.48f, 1f),
                PickupKind.Quest => new Color(1f, 0.82f, 0.4f),
                PickupKind.Powerup when powerup != null && GameData.Powerups.TryGetValue(powerup, out var pd) => Appearance.ToColor(pd.Color),
                _ => new Color(0.7f, 0.9f, 1f),
            };
            p.Build();
            go.SetActive(!hidden);
            return p;
        }

        void Build()
        {
            var lit = FxMaterials.Lit(Color * 0.4f, 0.1f, 0.85f, "pickup_" + Kind);
            lit.EnableKeyword("_EMISSION");
            lit.SetColor("_EmissionColor", FxMaterials.Hdr(Color, 2.4f));
            var dark = FxMaterials.Lit(new Color(0.16f, 0.17f, 0.19f), 0.6f, 0.55f, "pickup_metal");
            spin = new GameObject("Spin").transform;
            spin.SetParent(transform, false);
            switch (Kind)
            {
                case PickupKind.Fragment:
                    AddMesh(spin, Crystal(), lit, Vector3.zero, new Vector3(0.22f, 0.42f, 0.22f));
                    AddMesh(spin, Crystal(), lit, new Vector3(0.14f, -0.08f, 0.05f), new Vector3(0.1f, 0.2f, 0.1f), 25);
                    break;
                case PickupKind.Recording:
                    AddMesh(spin, Disc(), dark, Vector3.zero, new Vector3(0.32f, 0.04f, 0.32f), 0, 80);
                    AddMesh(spin, Disc(), lit, new Vector3(0, 0, -0.022f), new Vector3(0.14f, 0.02f, 0.14f), 0, 80);
                    break;
                case PickupKind.Cache:
                    AddPrim(transform, PrimitiveType.Cube, dark, new Vector3(0, -0.55f, 0), new Vector3(0.7f, 0.4f, 0.46f));
                    lid = new GameObject("Lid").transform;
                    lid.SetParent(transform, false);
                    lid.localPosition = new Vector3(0, -0.35f, -0.23f);
                    AddPrim(lid, PrimitiveType.Cube, dark, new Vector3(0, 0.03f, 0.23f), new Vector3(0.72f, 0.06f, 0.48f));
                    AddPrim(transform, PrimitiveType.Cube, lit, new Vector3(0, -0.5f, -0.235f), new Vector3(0.5f, 0.03f, 0.01f));
                    break;
                case PickupKind.Quest:
                    AddPrim(spin, PrimitiveType.Cube, dark, Vector3.zero, new Vector3(0.26f, 0.18f, 0.18f));
                    AddPrim(spin, PrimitiveType.Cube, lit, new Vector3(0, 0.1f, 0), new Vector3(0.2f, 0.03f, 0.12f));
                    break;
                default:
                    AddPrim(spin, PrimitiveType.Cylinder, dark, Vector3.zero, new Vector3(0.18f, 0.16f, 0.18f));
                    AddPrim(spin, PrimitiveType.Cylinder, lit, Vector3.zero, new Vector3(0.14f, 0.18f, 0.14f));
                    break;
            }
            // Soft halo billboard + light.
            var q = GameObject.CreatePrimitive(PrimitiveType.Quad);
            Destroy(q.GetComponent<Collider>());
            q.name = "Halo";
            q.transform.SetParent(transform, false);
            q.transform.localScale = Vector3.one * (Kind == PickupKind.Cache ? 1.4f : 1.1f);
            var hm = new Material(FxMaterials.Particle(true, FxMaterials.Glow));
            hm.SetColor("_BaseColor", Color * 0.6f);
            halo = q.GetComponent<Renderer>();
            halo.sharedMaterial = hm;
            halo.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
            var lg = new GameObject("Light");
            lg.transform.SetParent(transform, false);
            glow = lg.AddComponent<Light>();
            glow.type = LightType.Point;
            glow.color = Color;
            glow.intensity = 1.6f;
            glow.range = 3.2f;
            glow.shadows = LightShadows.None;
        }

        static void AddMesh(Transform parent, Mesh mesh, Material m, Vector3 pos, Vector3 scale, float rotZ = 0, float rotX = 0)
        {
            var go = new GameObject("Mesh");
            go.transform.SetParent(parent, false);
            go.transform.localPosition = pos;
            go.transform.localRotation = Quaternion.Euler(rotX, 0, rotZ);
            go.transform.localScale = scale;
            go.AddComponent<MeshFilter>().sharedMesh = mesh;
            var r = go.AddComponent<MeshRenderer>();
            r.sharedMaterial = m;
            r.shadowCastingMode = UnityEngine.Rendering.ShadowCastingMode.Off;
        }

        static void AddPrim(Transform parent, PrimitiveType type, Material m, Vector3 pos, Vector3 scale)
        {
            var go = GameObject.CreatePrimitive(type);
            Destroy(go.GetComponent<Collider>());
            go.transform.SetParent(parent, false);
            go.transform.localPosition = pos;
            go.transform.localScale = scale;
            go.GetComponent<Renderer>().sharedMaterial = m;
        }

        static Mesh Crystal()
        {
            if (crystal != null) return crystal;
            crystal = new Mesh { name = "crystal" };
            var v = new[] { new Vector3(0, 1, 0), new Vector3(1, 0, 0), new Vector3(0, 0, 1), new Vector3(-1, 0, 0), new Vector3(0, 0, -1), new Vector3(0, -1, 0) };
            int[] tris = { 0, 2, 1, 0, 3, 2, 0, 4, 3, 0, 1, 4, 5, 1, 2, 5, 2, 3, 5, 3, 4, 5, 4, 1 };
            // Flat shading: unique vertices per face.
            var verts = new Vector3[tris.Length];
            var idx = new int[tris.Length];
            for (var i = 0; i < tris.Length; i++) { verts[i] = v[tris[i]]; idx[i] = i; }
            crystal.vertices = verts;
            crystal.triangles = idx;
            crystal.RecalculateNormals();
            crystal.RecalculateBounds();
            return crystal;
        }

        static Mesh Disc()
        {
            if (disc != null) return disc;
            var go = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            disc = go.GetComponent<MeshFilter>().sharedMesh;
            Destroy(go);
            return disc;
        }

        public void Reveal()
        {
            Hidden = false;
            gameObject.SetActive(true);
        }

        public void MarkCollected()
        {
            Collected = true;
            if (Kind == PickupKind.Cache)
            {
                if (lid != null) lid.localRotation = Quaternion.Euler(-95, 0, 0);
                if (halo != null) halo.enabled = false;
                if (glow != null) glow.enabled = false;
            }
            else gameObject.SetActive(false);
        }

        void Update()
        {
            if (Collected) return;
            t += Time.deltaTime;
            if (Kind != PickupKind.Cache)
            {
                transform.position = basePos + Vector3.up * (Mathf.Sin(t * 2) * 0.08f);
                spin.Rotate(0, Time.deltaTime * 92f, 0, Space.Self);
            }
            if (halo != null)
            {
                var cam = Camera.main;
                if (cam != null) halo.transform.rotation = cam.transform.rotation;
                var a = 0.75f + Mathf.Sin(t * 3) * 0.25f;
                halo.sharedMaterial.SetColor("_BaseColor", Color * 0.6f * a);
            }
        }
    }
}
