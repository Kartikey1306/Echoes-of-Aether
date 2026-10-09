using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Route walking for a 'wander' NPC (port of the prototype Npc.update wander branch: walk 1.1 m/s to the next route
    /// point, pause 1.5-4.5 s, loop). The Unity <see cref="Npc"/> has no routes, so the plaza attaches this to Nia.
    /// Runs in LateUpdate (after Npc.Tick wrote its own yaw) and before Npc's head-glance LateUpdate.
    /// </summary>
    [DefaultExecutionOrder(-50)]
    public sealed class PzWander : MonoBehaviour
    {
        static readonly int SpeedId = Animator.StringToHash("Speed");
        Npc npc;
        Vector3[] route;
        int idx;
        float wait, yaw;
        public float Speed = 1.1f;

        /// <summary>route in Unity space.</summary>
        public void Init(Npc n, Vector3[] unityRoute)
        {
            npc = n;
            route = unityRoute;
            yaw = transform.eulerAngles.y;
        }

        void LateUpdate()
        {
            if (npc == null || route == null || route.Length < 2) return;
            var m = G.Manager;
            if (m == null || m.Mode != GameMode.Play || m.Paused) return;
            var dt = Time.deltaTime;
            var speed = 0f;
            if (npc.Talking)
            {
                yaw = transform.eulerAngles.y;
            }
            else
            {
                var target = route[idx];
                var to = target - transform.position;
                to.y = 0;
                var d = to.magnitude;
                if (wait > 0) wait -= dt;
                else if (d < 0.4f)
                {
                    idx = (idx + 1) % route.Length;
                    wait = 1.5f + Random.value * 3f;
                }
                else
                {
                    speed = Speed;
                    var dir = to / d;
                    yaw = Mathf.LerpAngle(yaw, Mathf.Atan2(dir.x, dir.z) * Mathf.Rad2Deg, 1 - Mathf.Exp(-4 * dt));
                    var p = transform.position + dir * (speed * dt);
                    p.y = target.y;
                    transform.position = p;
                }
                transform.rotation = Quaternion.Euler(0, yaw, 0);
            }
            var a = npc.Human != null ? npc.Human.Animator : null;
            if (a != null && a.isActiveAndEnabled) a.SetFloat(SpeedId, speed, 0.12f, dt);
        }
    }
}
