using System;
using System.Threading.Tasks;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Plaza cinematics (port of introScript/introFinalize and meetingScript/meetingFinalize in Cinematics.ts).
    /// Camera positions are authored in prototype space and converted with <see cref="ProtoSpace.V(float,float,float)"/>;
    /// offsets around actors are prototype offsets converted the same way (V is linear, so pos + V(offset) works on
    /// Unity positions).
    /// </summary>
    public static class PlazaCinematics
    {
        public static void Register(Cinematics c)
        {
            c.Register("cin_intro", Intro, IntroFinalize);
            c.Register("cin_meeting", Meeting, MeetingFinalize);
        }

        /// <summary>Fire-and-forget camera move (prototype <c>void c.shot(...)</c>); a skip ends it quietly.</summary>
        static async void Run(Task t)
        {
            try { await t; }
            catch (CinematicSkipped) { }
            catch (Exception e) { Debug.LogException(e); }
        }

        /// <summary>The prototype's guard(): abort the script as soon as a skip is requested.</summary>
        static void Guard(Cinematics.CineCtx c)
        {
            if (c.Skipped) throw new CinematicSkipped();
        }

        static Vector3 WithY(Vector3 v, float y) => new(v.x, y, v.z);

        // ------------------------------------------------------------------ intro (~90 s)

        static async Task Intro(Cinematics.CineCtx c)
        {
            var g = c.G;
            var p = g.Player;
            if (p == null) return;
            var partner = g.HeroOf(Characters.Partner(p.Character));
            await c.Fade(true, 0.01f);
            c.Music("menu");
            p.PlayClip("lie", true);
            c.Cut(V(-60, 42, 70), V(0, 6, 0), 50);
            Guard(c);
            await c.Fade(false, 2.5f);
            // Aerial push over the district toward the monument.
            Run(c.Shot(V(-60, 42, 70), V(0, 6, 0), V(-30, 26, 36), V(0, 8, 0), 14, 50));
            await c.Lines("cin_intro_lines", "n1", "n1");
            await c.Wait(1.5f);
            // Street-level glide past abandoned cars on the ring road.
            Run(c.Shot(V(-38, 1.6f, 40), V(-38, 1.4f, 0), V(-36, 1.9f, 4), V(-20, 2.5f, -20), 13, 55));
            await c.Lines("cin_intro_lines", "n2", "n2");
            await c.Wait(2);
            // Rise up the monument to the core.
            Run(c.Shot(V(8, 1.2f, 10), V(0, 3.5f, 0), V(5.5f, 8.6f, 6.5f), V(PlazaZone.CoreProto), 12, 45));
            await c.Lines("cin_intro_lines", "n3", "n3");
            await c.Wait(1);
            (g.World?.Script as ProceduralZone)?.ZoneWeather?.TriggerLightning(1);
            CombatSystem.Shake(0.4f);
            c.Sfx("pulse", V(PlazaZone.CoreProto));
            await c.Lines("cin_intro_lines", "n4", "n4");
            await c.Wait(2);
            Guard(c);
            await c.Fade(true, 1.2f);
            // The protagonist lying in the rain beside the monument.
            var pp = p.Position;
            c.Cut(pp + V(2.4f, 0.6f, 1.4f), pp + V(0, 0.3f, 0), 40);
            Guard(c);
            await c.Fade(false, 1.5f);
            c.Drift(pp + V(1.6f, 0.9f, 0.9f), pp + V(0, 0.3f, 0), 10);
            await c.Lines("cin_intro_lines", "n5", "n5");
            // Partner far away at the camp.
            if (partner != null && partner.gameObject.activeInHierarchy)
            {
                var pt = partner.Position;
                c.Cut(pt + V(-2.5f, 1.7f, 3.2f), pt + V(0, 1.4f, 0), 40);
            }
            await c.Lines("cin_intro_lines", "n6", "n6");
            c.Cut(pp + V(1.8f, 1.0f, 2.2f), pp + V(0, 0.6f, 0), 42);
            p.PlayClip("wake");
            await c.Lines("cin_intro_lines", "n7", "n7");
            await c.Lines("cin_intro_lines", "n8", "n8");
            Run(c.Shot(pp + V(1.8f, 1.0f, 2.2f), pp + V(0, 0.8f, 0), pp + V(-1.2f, 1.9f, 3.4f), pp + V(0, 1.5f, -6), 4, 50));
            await c.Lines("cin_intro_lines", "n9", "n9");
            await c.Wait(1.5f);
        }

        static void IntroFinalize()
        {
            var p = G.Manager != null ? G.Manager.Player : null;
            if (p == null) return;
            p.CancelActions();
            G.Audio?.SetMusic("explore");
        }

        // ------------------------------------------------------------------ meeting (~45 s)

        static async Task Meeting(Cinematics.CineCtx c)
        {
            var g = c.G;
            var p = g.Player;
            if (p == null) return;
            var partner = g.HeroOf(Characters.Partner(p.Character));
            if (partner == null) return;
            var oren = g.World?.FindNpc("oren");
            var fire = g.World?.Def != null ? g.World.Def.Marker("fire") : null;
            var camp = V(fire ?? p.Position); // prototype space
            Guard(c);
            await c.Fade(true, 0.6f);
            // Stage: player stands near the fire, partner turns to them (all in prototype space).
            var meetA = new Vector3(camp.x - 3.2f, p.Position.y, camp.z + 1.6f);
            var meetB = new Vector3(camp.x - 1.6f, partner.Position.y, camp.z + 0.2f);
            p.Teleport(V(meetA), Yaw(Mathf.Atan2(meetB.x - meetA.x, meetB.z - meetA.z)));
            partner.CancelActions();
            partner.Teleport(V(meetB), Yaw(Mathf.Atan2(meetA.x - meetB.x, meetA.z - meetB.z)));
            partner.SetScripted(true);
            var mid = WithY(Vector3.Lerp(meetA, meetB, 0.5f), meetA.y + 1.55f);
            var side = new Vector3(meetB.z - meetA.z, 0, -(meetB.x - meetA.x)).normalized;
            c.Cut(V(WithY(mid + side * 3.4f, mid.y + 0.2f)), V(mid), 42);
            Guard(c);
            await c.Fade(false, 1);
            c.Music("sidequest");
            // Shot / reverse shot between the two protagonists.
            var away = meetA - meetB;
            away.y = 0;
            away.Normalize();
            // Over-the-shoulder, wide enough that the near hero's shoulder armour and hair frame the shot
            // instead of filling it.
            var overP = V(WithY(meetA + away * 1.75f + side * 1.0f, meetA.y + 1.75f));
            var overQ = V(WithY(meetB - away * 1.75f - side * 1.0f, meetB.y + 1.75f));
            Vector3 Chest(Hero h) => h.Position + Vector3.up * 1.55f;
            var kael = p.Character == Characters.Kael;
            string first0 = kael ? "k1" : "l1", first1 = kael ? "k4" : "l3";
            c.Cut(overP, Chest(partner), 38);
            partner.PlayClip("talk");
            await c.Lines("cin_meeting_lines", first0, first0);
            c.Cut(overQ, Chest(p), 38);
            p.PlayClip("talk");
            await c.Lines("cin_meeting_lines", kael ? "k2" : "l2", kael ? "k2" : "l2");
            c.Cut(overP, Chest(partner), 38);
            await c.Lines("cin_meeting_lines", kael ? "k3" : "l3", first1);
            // Oren joins.
            var orenCam = V(WithY(mid + side * -2.6f, mid.y + 0.3f));
            if (oren != null)
            {
                oren.StartTalk(V(mid));
                c.Cut(orenCam, oren.Position + Vector3.up * 1.5f, 40);
            }
            await c.Lines("cin_meeting_lines", "c1", "c1");
            c.Cut(overQ, Vector3.Lerp(Chest(partner), Chest(p), 0.5f), 44);
            await c.Lines("cin_meeting_lines", "c2", "c2");
            if (oren != null) c.Cut(orenCam, oren.Position + Vector3.up * 1.5f, 40);
            await c.Lines("cin_meeting_lines", "c3", "c3");
            c.Cut(overQ, Chest(p), 38);
            await c.Lines("cin_meeting_lines", "c4", "c4");
            if (oren != null) c.Cut(orenCam, oren.Position + Vector3.up * 1.5f, 40);
            await c.Lines("cin_meeting_lines", "c5", "c5");
            // Wide shot: the two of them look toward the metro entrance.
            c.Drift(V(WithY(mid + side * 4.5f, mid.y + 1.2f)), V(PlazaZone.MetroLookProto), 6);
            await c.Lines("cin_meeting_lines", "c6", "c6");
            await c.Wait(2.5f);
            if (oren != null) oren.EndTalk();
        }

        static void MeetingFinalize()
        {
            var g = G.Manager;
            if (g == null) return;
            G.State?.SetFlag("swap_unlocked");
            var p = g.Player;
            var partner = p != null ? g.HeroOf(Characters.Partner(p.Character)) : null;
            if (p != null && partner != null)
            {
                partner.CancelActions();
                partner.SetScripted(false);
                partner.FollowLeader = p;
                partner.SetRole(false);
            }
            var oren = g.World != null ? g.World.FindNpc("oren") : null;
            if (oren != null) oren.EndTalk();
        }
    }
}
