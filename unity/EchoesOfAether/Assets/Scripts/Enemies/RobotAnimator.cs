using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace EOA
{
    /// <summary>
    /// Pose buffer in the prototype's convention: per-bone Euler angles in degrees (three.js XYZ order, right-handed,
    /// character facing +Z with its LEFT on +X) plus a hips offset in metres at the 1.8 m reference scale.
    /// Conversion to Unity (left-handed, left on -X) happens in <see cref="RobotAnimator"/> (mirror X:
    /// quaternion (x, -y, -z, w), offset (-x, y, z)). Keeping clip data in prototype units lets clips be copied verbatim.
    /// </summary>
    public sealed class RobotPose
    {
        public const int NB = 20;
        public readonly float[] E = new float[NB * 3];
        public Vector3 P;

        public void Clear()
        {
            Array.Clear(E, 0, E.Length);
            P = Vector3.zero;
        }

        public void CopyFrom(RobotPose o)
        {
            Array.Copy(o.E, E, E.Length);
            P = o.P;
        }

        public void Set(int bone, float x, float y, float z)
        {
            int i = bone * 3;
            E[i] = x; E[i + 1] = y; E[i + 2] = z;
        }

        public static RobotPose From(PoseSpec spec)
        {
            var p = new RobotPose();
            foreach (var kv in spec)
            {
                if (kv.Key == "hipsPos") { p.P = kv.Value; continue; }
                int b = RobotRig.BoneIndex(kv.Key);
                if (b < 0) { Debug.LogWarning("[robot] unknown bone in pose: " + kv.Key); continue; }
                p.Set(b, kv.Value.x, kv.Value.y, kv.Value.z);
            }
            return p;
        }
    }

    /// <summary>
    /// Pose specification: bone name -> Euler degrees (prototype convention), "hipsPos" -> offset.
    /// Built with <see cref="Parse"/> from strings like "hipsPos:0,-0.06,0 spine:10,0,0 upperarm_S:-20,-10,6"
    /// where keys ending in _S expand to _L as-is and _R mirrored (y, z negated), like the prototype's sym().
    /// </summary>
    public sealed class PoseSpec : Dictionary<string, Vector3>
    {
        public static PoseSpec Parse(string spec)
        {
            var p = new PoseSpec();
            if (string.IsNullOrEmpty(spec)) return p;
            foreach (var token in spec.Split(new[] { ' ', '\n', '\t' }, StringSplitOptions.RemoveEmptyEntries))
            {
                int c = token.IndexOf(':');
                if (c <= 0) { Debug.LogWarning("[robot] bad pose token " + token); continue; }
                string key = token.Substring(0, c);
                var parts = token.Substring(c + 1).Split(',');
                if (parts.Length != 3) { Debug.LogWarning("[robot] bad pose token " + token); continue; }
                var v = new Vector3(F(parts[0]), F(parts[1]), F(parts[2]));
                if (key.EndsWith("_S", StringComparison.Ordinal))
                {
                    string b = key.Substring(0, key.Length - 2);
                    p[b + "_L"] = v;
                    p[b + "_R"] = new Vector3(v.x, -v.y, -v.z);
                }
                else p[key] = v;
            }
            return p;
        }

        static float F(string s) => float.Parse(s, NumberStyles.Float, CultureInfo.InvariantCulture);

        /// <summary>Object.assign({}, ...specs): later specs override earlier keys.</summary>
        public static PoseSpec Merge(params PoseSpec[] specs)
        {
            var p = new PoseSpec();
            foreach (var s in specs)
                if (s != null)
                    foreach (var kv in s) p[kv.Key] = kv.Value;
            return p;
        }

        public PoseSpec With(string spec) => Merge(this, Parse(spec));
    }

    public struct RobotClipEvent
    {
        public float T;
        public string Name;
        public RobotClipEvent(float t, string name) { T = t; Name = name; }
    }

    public abstract class RobotClip
    {
        public string Name;
        public float Duration;
        public bool Loop;
        public RobotClipEvent[] Events = Array.Empty<RobotClipEvent>();
        public abstract void Sample(float t, RobotPose output);
    }

    /// <summary>Keyframed clip with Catmull-Rom interpolation of Euler channels (port of KeyClip).</summary>
    public sealed class RobotKeyClip : RobotClip
    {
        readonly float[] times;
        readonly RobotPose[] poses;

        public RobotKeyClip(string name, (float t, PoseSpec pose)[] keys, float duration, bool loop = false, params RobotClipEvent[] events)
        {
            Name = name;
            Duration = duration;
            Loop = loop;
            Events = events ?? Array.Empty<RobotClipEvent>();
            times = new float[keys.Length];
            poses = new RobotPose[keys.Length];
            for (int i = 0; i < keys.Length; i++)
            {
                times[i] = keys[i].t;
                poses[i] = RobotPose.From(keys[i].pose);
            }
        }

        public override void Sample(float t, RobotPose output)
        {
            int n = times.Length;
            if (n == 1)
            {
                output.CopyFrom(poses[0]);
                return;
            }
            if (Loop) t = ((t % Duration) + Duration) % Duration;
            else t = Mathf.Clamp(t, 0f, Duration);
            int i = 0;
            while (i < n - 1 && times[i + 1] <= t) i++;
            if (i >= n - 1 && !Loop)
            {
                output.CopyFrom(poses[n - 1]);
                return;
            }
            int i1 = i, i2 = Loop ? (i + 1) % n : Mathf.Min(i + 1, n - 1);
            int i0 = Loop ? (i - 1 + n) % n : Mathf.Max(0, i - 1);
            int i3 = Loop ? (i + 2) % n : Mathf.Min(n - 1, i + 2);
            float t1 = times[i1];
            float t2 = times[i2];
            if (t2 <= t1) t2 = Duration + (Loop ? times[i2] : 0f);
            float span = Mathf.Max(1e-5f, t2 - t1);
            float u = Mathf.Clamp01((t - t1) / span);
            float u2 = u * u, u3 = u2 * u;
            var P0 = poses[i0]; var P1 = poses[i1]; var P2 = poses[i2]; var P3 = poses[i3];
            for (int k = 0; k < RobotPose.NB * 3; k++) output.E[k] = Cr(P0.E[k], P1.E[k], P2.E[k], P3.E[k], u, u2, u3);
            output.P = new Vector3(
                Cr(P0.P.x, P1.P.x, P2.P.x, P3.P.x, u, u2, u3),
                Cr(P0.P.y, P1.P.y, P2.P.y, P3.P.y, u, u2, u3),
                Cr(P0.P.z, P1.P.z, P2.P.z, P3.P.z, u, u2, u3));
        }

        static float Cr(float a, float b, float c, float d, float u, float u2, float u3)
            => 0.5f * (2f * b + (-a + c) * u + (2f * a - 5f * b + 4f * c - d) * u2 + (-a + 3f * b - 3f * c + d) * u3);
    }

    /// <summary>Clip defined by a function of normalised phase (port of FnClip; used for gaits).</summary>
    public sealed class RobotFnClip : RobotClip
    {
        readonly Action<float, RobotPose> fn;

        public RobotFnClip(string name, float duration, bool loop, Action<float, RobotPose> fn)
        {
            Name = name;
            Duration = duration;
            Loop = loop;
            this.fn = fn;
        }

        public override void Sample(float t, RobotPose output)
        {
            float ph = Loop ? (((t / Duration) % 1f) + 1f) % 1f : Mathf.Clamp01(t / Duration);
            output.Clear();
            fn(ph, output);
        }
    }

    /// <summary>Locomotion clip set (idle / walk / run / sprint / combat idle + stride lengths).</summary>
    public sealed class RobotLoco
    {
        public RobotClip Idle, Walk, Run, Sprint, CombatIdle;
        public float StrideWalk = 1.6f, StrideRun = 3.4f, StrideSprint = 4.6f;
    }

    /// <summary>A playing one-shot action (handle returned by <see cref="RobotAnimator.Play"/>).</summary>
    public sealed class RobotAction
    {
        public RobotClip Clip;
        public float Time, Speed = 1f, Weight, FadeIn, FadeOut;
        public float[] Mask;
        public bool[] Fired;
        public Action<string> OnEvent;
        public Action OnEnd;
        public bool Ending, Hold;
    }

    /// <summary>
    /// Layered procedural animator for robot rigs (port of the prototype's Animator.ts, minus airborne/look/aim/lean
    /// layers that robots never use). Produces local pose rotations per bone in Unity space (<see cref="Local"/>)
    /// and a hips offset (<see cref="HipsOffset"/>, reference scale); <see cref="RobotRig"/> applies them.
    /// </summary>
    public sealed class RobotAnimator
    {
        const int NB = RobotPose.NB;

        public static readonly float[] Full, Upper, Lower;

        static RobotAnimator()
        {
            Full = new float[NB];
            Upper = new float[NB];
            Lower = new float[NB];
            for (int i = 0; i < NB; i++)
            {
                string n = RobotRig.BoneNames[i];
                bool up = n.Contains("spine") || n.Contains("chest") || n.Contains("neck") || n.Contains("head") ||
                          n.Contains("clavicle") || n.Contains("upperarm") || n.Contains("forearm") || n.Contains("hand");
                Full[i] = 1f;
                Upper[i] = n == "spine" ? 0.6f : up ? 1f : 0f;
                Lower[i] = up ? (n == "spine" ? 0.4f : 0f) : 1f;
            }
        }

        public RobotLoco Loco;
        /// <summary>Ground speed (m/s) set by the controller.</summary>
        public float Speed;
        /// <summary>0..1 blend toward the combat idle.</summary>
        public float CombatStance;
        /// <summary>Global time scale (hit stop / slow motion).</summary>
        public float TimeScale = 1f;
        public float Breathe = 1f;

        /// <summary>Local rotation of each bone relative to its rest pose, Unity space (index = RobotRig.BoneNames).</summary>
        public readonly Quaternion[] Local = new Quaternion[NB];
        /// <summary>Hips offset in metres at reference scale, Unity space (multiply by the rig scale).</summary>
        public Vector3 HipsOffset;

        readonly float scale;
        float stanceW, phase, time, hitJolt, hitDir = 1f;

        sealed class StateLayer
        {
            public RobotClip Clip;
            public float Time, W, Target, Fade;
        }

        StateLayer state;
        readonly List<RobotAction> actions = new();
        readonly RobotPose bufA = new(), bufB = new();
        readonly Quaternion[] qBase = new Quaternion[NB], qTmp = new Quaternion[NB], qOut = new Quaternion[NB];
        Vector3 hipsOff;

        public RobotAnimator(RobotLoco loco, float scale)
        {
            Loco = loco;
            this.scale = Mathf.Max(0.01f, scale);
            for (int i = 0; i < NB; i++) Local[i] = Quaternion.identity;
        }

        /// <summary>Play a one-shot (or held) action layered over locomotion. Cross-fades out current actions.</summary>
        public RobotAction Play(RobotClip clip, float fadeIn = 0.08f, float fadeOut = 0.15f, float speed = 1f,
                                Action<string> onEvent = null, Action onEnd = null, bool hold = false, float[] mask = null, bool additiveLayer = false)
        {
            if (clip == null) return null;
            if (!additiveLayer)
            {
                foreach (var a in actions)
                {
                    if (a.Ending) continue;
                    a.Ending = true;
                    a.FadeOut = Mathf.Min(a.FadeOut, fadeIn);
                    a.OnEnd = null;
                    // Deviation from the prototype: cross-faded actions stop firing events (avoids stale hit windows).
                    a.OnEvent = null;
                }
            }
            var st = new RobotAction
            {
                Clip = clip,
                Time = 0f,
                Speed = speed,
                Weight = fadeIn <= 0f ? 1f : 0f,
                FadeIn = fadeIn,
                FadeOut = fadeOut,
                Mask = mask ?? Full,
                Fired = new bool[clip.Events.Length],
                OnEvent = onEvent,
                OnEnd = onEnd,
                Hold = hold,
            };
            actions.Add(st);
            return st;
        }

        public void StopActions(float fade = 0.15f)
        {
            foreach (var a in actions)
            {
                a.Ending = true;
                a.FadeOut = fade;
                a.OnEnd = null;
                a.OnEvent = null;
            }
        }

        public bool ActionActive
        {
            get
            {
                foreach (var a in actions) if (!a.Ending) return true;
                return false;
            }
        }

        public string CurrentAction()
        {
            foreach (var a in actions) if (!a.Ending) return a.Clip.Name;
            return null;
        }

        /// <summary>Full-body state clip (death...) overriding locomotion; null fades it out.</summary>
        public void SetState(RobotClip clip, float fade = 0.2f)
        {
            if (clip != null) state = new StateLayer { Clip = clip, Time = 0f, W = state != null ? state.W : 0f, Target = 1f, Fade = fade };
            else if (state != null)
            {
                state.Target = 0f;
                state.Fade = fade;
            }
        }

        public void Jolt(float dir = 1f, float amount = 1f)
        {
            hitJolt = amount;
            hitDir = dir;
        }

        public void ResetPhase() => phase = 0f;

        // ------------------------------------------------------------------ Update

        public void Update(float dtIn)
        {
            float dt = dtIn * TimeScale;
            time += dt;
            var L = Loco;
            float sp = Speed;
            stanceW += (CombatStance - stanceW) * Mathf.Min(1f, dt * 4f);
            float stride;
            if (sp < 2.2f) stride = L.StrideWalk;
            else if (sp < 5.5f) stride = L.StrideWalk + (L.StrideRun - L.StrideWalk) * CombatMath.SmoothStep(2.2f, 5.0f, sp);
            else stride = L.StrideRun + (L.StrideSprint - L.StrideRun) * CombatMath.SmoothStep(5.5f, 7.5f, sp);
            phase = (phase + (sp / (stride * scale)) * dt) % 1f;

            var idleClip = stanceW > 0.5f && L.CombatIdle != null ? L.CombatIdle : L.Idle;
            idleClip.Sample(time, bufA);
            ToQuats(bufA, qBase);
            hipsOff = bufA.P;
            if (stanceW > 0.01f && stanceW < 0.99f && L.CombatIdle != null)
            {
                var other = idleClip == L.Idle ? L.CombatIdle : L.Idle;
                other.Sample(time, bufB);
                ToQuats(bufB, qTmp);
                float w = idleClip == L.Idle ? stanceW : 1f - stanceW;
                SlerpInto(qBase, qTmp, w, Full, qBase);
                hipsOff = Vector3.Lerp(hipsOff, bufB.P, w);
            }
            BlendLoco(L.Walk, CombatMath.SmoothStep(0.15f, 1.4f, sp));
            BlendLoco(L.Run, CombatMath.SmoothStep(2.2f, 4.6f, sp));
            BlendLoco(L.Sprint, CombatMath.SmoothStep(5.6f, 7.4f, sp));

            // State override
            if (state != null)
            {
                var s = state;
                s.Time += dt;
                s.W += Mathf.Sign(s.Target - s.W) * (dt / Mathf.Max(0.01f, s.Fade));
                s.W = Mathf.Clamp01(s.W);
                if (s.W > 0.001f)
                {
                    s.Clip.Sample(s.Time, bufB);
                    ToQuats(bufB, qTmp);
                    SlerpInto(qBase, qTmp, s.W, Full, qBase);
                    hipsOff = Vector3.Lerp(hipsOff, bufB.P, s.W);
                }
                if (s.Target == 0f && s.W <= 0.001f) state = null;
            }

            // Actions (index loop: callbacks may add actions)
            Array.Copy(qBase, qOut, NB);
            for (int ai = 0; ai < actions.Count; ai++)
            {
                var a = actions[ai];
                float prev = a.Time;
                a.Time += dt * a.Speed;
                if (a.Ending) a.Weight -= dt / Mathf.Max(0.01f, a.FadeOut);
                else a.Weight = Mathf.Min(1f, a.Weight + dt / Mathf.Max(0.01f, a.FadeIn));
                var evs = a.Clip.Events;
                if (evs.Length > 0 && a.OnEvent != null)
                {
                    for (int k = 0; k < evs.Length; k++)
                    {
                        if (!a.Fired[k] && prev <= evs[k].T && a.Time >= evs[k].T)
                        {
                            a.Fired[k] = true;
                            a.OnEvent?.Invoke(evs[k].Name);
                        }
                    }
                }
                if (!a.Clip.Loop && !a.Hold && !a.Ending && a.Time >= a.Clip.Duration)
                {
                    a.Ending = true;
                    var cb = a.OnEnd;
                    a.OnEnd = null;
                    cb?.Invoke();
                }
                if (a.Weight <= 0f) continue;
                a.Clip.Sample(a.Time, bufB);
                ToQuats(bufB, qTmp);
                // Lower body follows locomotion when moving.
                var mask = a.Mask == Full && sp > 1.2f ? Upper : a.Mask;
                SlerpInto(qOut, qTmp, a.Weight, mask, qOut);
                float hw = a.Weight * mask[RobotRig.Hips];
                if (hw > 0f) hipsOff = Vector3.Lerp(hipsOff, bufB.P, Mathf.Min(1f, hw));
            }
            actions.RemoveAll(x => x.Ending && x.Weight <= 0f);

            // Additive layers (radians, prototype convention) and output.
            hitJolt = Mathf.Max(0f, hitJolt - dt * 5f);
            float breath = Mathf.Sin(time * 1.7f) * Breathe;
            for (int i = 0; i < NB; i++)
            {
                Quaternion q = qOut[i];
                float ax = 0f, ay = 0f, az = 0f;
                if (i == RobotRig.Chest)
                {
                    ax += breath * 0.012f - hitJolt * 0.22f;
                    ay += hitJolt * 0.1f * hitDir;
                }
                else if (i == RobotRig.Spine) ax += -hitJolt * 0.1f;
                else if (i == RobotRig.ClavicleL) az += breath * 0.01f;
                else if (i == RobotRig.ClavicleR) az -= breath * 0.01f;
                if (ax != 0f || ay != 0f || az != 0f) q = EulerXYZ(ax, ay, az) * q;
                Local[i] = q;
            }
            HipsOffset = new Vector3(-hipsOff.x, hipsOff.y, hipsOff.z);
        }

        void BlendLoco(RobotClip clip, float w)
        {
            if (clip == null || w <= 0.001f) return;
            clip.Sample(phase * clip.Duration, bufB);
            ToQuats(bufB, qTmp);
            SlerpInto(qBase, qTmp, w, Full, qBase);
            hipsOff = Vector3.Lerp(hipsOff, bufB.P, w);
        }

        static void ToQuats(RobotPose p, Quaternion[] output)
        {
            const float D = Mathf.Deg2Rad;
            for (int i = 0; i < NB; i++) output[i] = EulerXYZ(p.E[i * 3] * D, p.E[i * 3 + 1] * D, p.E[i * 3 + 2] * D);
        }

        static void SlerpInto(Quaternion[] a, Quaternion[] b, float w, float[] mask, Quaternion[] output)
        {
            for (int i = 0; i < NB; i++)
            {
                float k = w * mask[i];
                if (k <= 0.0001f)
                {
                    output[i] = a[i];
                    continue;
                }
                output[i] = Quaternion.Slerp(a[i], b[i], Mathf.Min(1f, k));
            }
        }

        /// <summary>
        /// Rotation from prototype Euler angles (radians, three.js 'XYZ' order, right-handed), converted to Unity's
        /// left-handed space by mirroring X: q = (x, -y, -z, w) of three's setFromEuler.
        /// </summary>
        public static Quaternion EulerXYZ(float x, float y, float z)
        {
            float c1 = Mathf.Cos(x * 0.5f), c2 = Mathf.Cos(y * 0.5f), c3 = Mathf.Cos(z * 0.5f);
            float s1 = Mathf.Sin(x * 0.5f), s2 = Mathf.Sin(y * 0.5f), s3 = Mathf.Sin(z * 0.5f);
            float qx = s1 * c2 * c3 + c1 * s2 * s3;
            float qy = c1 * s2 * c3 - s1 * c2 * s3;
            float qz = c1 * c2 * s3 + s1 * s2 * c3;
            float qw = c1 * c2 * c3 - s1 * s2 * s3;
            return new Quaternion(qx, -qy, -qz, qw);
        }
    }
}
