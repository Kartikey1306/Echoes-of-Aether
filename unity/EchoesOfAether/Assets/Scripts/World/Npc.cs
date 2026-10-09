using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Non-player characters: plaza survivors (MakeHuman models with looping behaviour clips), the Aether echoes
    /// (Nia, Maren: translucent, visible only to Echo Sight when EchoOnly) and the maintenance robot BOLT.
    /// </summary>
    public sealed class Npc : MonoBehaviour
    {
        public ZoneNpc Place;
        public string Id => Place.Id;
        public CharacterModel Human { get; private set; }
        public RobotRig Robot { get; private set; }
        public bool Talking { get; private set; }
        public bool BoltActive;
        public Vector3 Position => transform.position;
        float yaw, reactCd;
        Vector3? talkTarget;
        Transform head;

        public static Npc Spawn(ZoneNpc place, Transform parent)
        {
            var go = new GameObject("NPC_" + place.Id);
            go.transform.SetParent(parent, false);
            go.transform.position = place.Position;
            go.layer = CombatLayers.NPC;
            var npc = go.AddComponent<Npc>();
            npc.Place = place;
            npc.yaw = place.YawDeg;
            if (place.Id == "bolt")
            {
                // BOLT: 1.55 m maintenance robot (Blender model "bolt"; procedural sentinel body at BOLT size otherwise).
                npc.Robot = RobotRig.Create(go.transform, RobotKind.Bolt, new RobotPalette(0x9a7a2a, 0x2a2a2e, 0xffc24a, 2.2f), "bolt");
            }
            else
            {
                var name = char.ToUpperInvariant(place.Id[0]) + place.Id.Substring(1);
                var prefab = Resources.Load<GameObject>("Characters/" + name);
                if (prefab != null)
                {
                    var m = Instantiate(prefab, go.transform);
                    m.name = "Model";
                    npc.Human = m.GetComponent<CharacterModel>();
                    if (npc.Human != null && npc.Human.Echo) npc.Human.SetEcho(true, place.Id == "nia" ? new Color(0.5f, 0.72f, 1f) : new Color(0.62f, 0.75f, 1f));
                    npc.head = npc.Human?.Bone(HumanBodyBones.Head);
                }
                else Debug.LogWarning($"[npc] missing prefab Characters/{name}");
            }
            if (!place.EchoOnly)
            {
                var col = go.AddComponent<CapsuleCollider>();
                col.radius = 0.35f;
                col.height = place.Id == "nia" ? 1.2f : 1.75f;
                col.center = Vector3.up * col.height / 2;
            }
            npc.ApplyBehaviour();
            npc.transform.rotation = Quaternion.Euler(0, npc.yaw, 0);
            return npc;
        }

        public void ApplyBehaviour()
        {
            if (Robot != null)
            {
                var clips = RobotClips.Get(RobotClips.Kind.Sentinel);
                if (!BoltActive && clips.TryGetValue("sit", out var sit)) Robot.Anim.SetState(sit, 0.01f);
                else if (!BoltActive && clips.TryGetValue("stagger", out var slump)) Robot.Anim.SetState(slump, 0.01f);
                else Robot.Anim.SetState(null, 0.4f);
                return;
            }
            var a = Human?.Animator;
            if (a == null) return;
            var b = string.IsNullOrEmpty(Place.Behaviour) || Place.Behaviour == "idle" || Place.Behaviour == "wander" ? "Empty" : Place.Behaviour;
            a.CrossFadeInFixedTime(b, 0.4f, 1, 0f);
        }

        public void StartTalk(Vector3 playerPos)
        {
            Talking = true;
            talkTarget = playerPos;
            Human?.Animator?.CrossFadeInFixedTime("talk", 0.4f, 1, 0f);
            if (Human != null) Human.Talk = 0;
        }

        /// <summary>Mouth movement while this NPC's line is on screen.</summary>
        public void SetSpeaking(bool on)
        {
            if (Human != null) Human.Talk = on ? 1 : 0;
        }

        public void EndTalk()
        {
            Talking = false;
            talkTarget = null;
            if (Human != null) Human.Talk = 0;
            ApplyBehaviour();
        }

        public void React()
        {
            if (reactCd > 0 || Human == null || Talking) return;
            reactCd = 8;
            Human.Animator?.CrossFadeInFixedTime("npc_react", 0.1f, 1, 0f);
        }

        Renderer[] visRenderers;
        bool? visApplied;

        /// <summary>Show/hide (echo-only NPCs follow Echo Sight every frame): renderers cached, applied on change only.</summary>
        public void SetVisible(bool v)
        {
            if (visApplied == v && visRenderers != null) return;
            visApplied = v;
            visRenderers = GetComponentsInChildren<Renderer>(true);
            foreach (var r in visRenderers) if (r != null) r.enabled = v;
        }

        public void Tick(float dt, Vector3? playerPos, bool echoActive)
        {
            reactCd -= dt;
            if (Place.EchoOnly) SetVisible(echoActive);
            if (Talking && talkTarget.HasValue)
            {
                var to = talkTarget.Value - Position;
                yaw = Mathf.LerpAngle(yaw, Mathf.Atan2(to.x, to.z) * Mathf.Rad2Deg, 1 - Mathf.Exp(-5 * dt));
            }
            else if (BoltActive && Robot != null)
            {
                // BOLT walks a small perimeter loop around the camp.
                var t = Time.time;
                var c = Place.Position;
                var target = new Vector3(c.x + Mathf.Cos(t * 0.15f) * 3, Position.y, c.z + Mathf.Sin(t * 0.15f) * 3);
                var dir = target - Position; dir.y = 0;
                if (dir.magnitude > 0.2f)
                {
                    dir.Normalize();
                    yaw = Mathf.LerpAngle(yaw, Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg, 1 - Mathf.Exp(-3 * dt));
                    var p = Position + dir * 0.9f * dt;
                    if (Physics.Raycast(p + Vector3.up, Vector3.down, out var hit, 3, CombatLayers.WorldMask, QueryTriggerInteraction.Ignore)) p.y = hit.point.y;
                    transform.position = p;
                }
            }
            transform.rotation = Quaternion.Euler(0, yaw, 0);
            Robot?.Tick(dt);
        }

        void LateUpdate()
        {
            // Glance at the player when close (head turn on top of the animation).
            if (head == null || Talking || Place.Behaviour == "npc_work" || Place.Behaviour == "lie") return;
            var p = G.Manager?.Player;
            if (p == null) return;
            var to = p.Position + Vector3.up * 1.5f - head.position;
            if (to.magnitude > 3.5f) return;
            var local = transform.InverseTransformDirection(to.normalized);
            var yawRel = Mathf.Clamp(Mathf.Atan2(local.x, local.z) * Mathf.Rad2Deg, -55, 55);
            head.rotation = Quaternion.AngleAxis(yawRel * 0.7f, Vector3.up) * head.rotation;
        }
    }
}
