using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>
    /// Driving HUD, in place of the ability bar while the player is in a car (<see cref="Driving.Active"/>): a 270 deg
    /// speed dial (ticks every 20 km/h, cyan fill turning violet near the top speed, RPM arc inside), digital km/h, the
    /// gear (R / N / 1-5) and the handbrake / reset keys. The "get out" prompt is the regular interaction prompt.
    /// Labels only change when the shown value does.
    /// </summary>
    public sealed class DriveHud
    {
        public readonly VisualElement Root;
        readonly SpeedDial dial;
        readonly Label speed, gear, hbKey, resetKey;
        int speedShown = -1, gearShown = int.MinValue;
        bool shown;

        public DriveHud()
        {
            dial = new SpeedDial();
            dial.AddToClassList("drive-arc");
            speed = U.Label("0", "drive-speed");
            var unit = U.Label(U.Up(U.T("drive.kmh")), "drive-unit");
            gear = U.Label("N", "drive-gear");
            var face = U.El("drive-dial", dial, U.El("drive-center", speed, unit), gear);
            hbKey = U.Keycap("Space");
            resetKey = U.Keycap("R");
            var keys = U.El("drive-keys",
                U.El("drive-key", hbKey, U.Label(U.Up(U.T("drive.handbrake")), "drive-key-l")),
                U.El("drive-key", resetKey, U.Label(U.Up(U.T("drive.reset")), "drive-key-l")));
            Root = U.El("drive", face, keys);
            U.Show(Root, false);
        }

        public void RefreshKeys(GameInput inp)
        {
            if (inp == null) return;
            hbKey.text = inp.Label("handbrake");
            resetKey.text = inp.Label("vehicleReset");
        }

        public void Tick(bool on)
        {
            if (on != shown) { shown = on; U.Show(Root, on); }
            var car = Driving.Car;
            if (!on || car == null) return;
            var kmh = Mathf.RoundToInt(Mathf.Abs(car.ForwardSpeed) * 3.6f);
            if (kmh != speedShown) { speedShown = kmh; speed.text = kmh.ToString(); }
            var g = car.Gear;
            if (g != gearShown) { gearShown = g; gear.text = g < 0 ? "R" : g == 0 ? "N" : g.ToString(); }
            dial.Set(Mathf.Abs(car.ForwardSpeed) * 3.6f, car.TopSpeed * 3.6f, car.Rpm01);
        }
    }

    /// <summary>Speed dial painter: 270 deg track with ticks, speed fill and an inner RPM arc.</summary>
    public sealed class SpeedDial : VisualElement
    {
        const float Start = 135f, Sweep = 270f;
        float kmh, max = 200f, rpm;

        public SpeedDial()
        {
            pickingMode = PickingMode.Ignore;
            generateVisualContent += Draw;
        }

        public void Set(float speedKmh, float maxKmh, float rpm01)
        {
            maxKmh = Mathf.Max(60f, Mathf.Ceil(maxKmh / 20f) * 20f);
            if (Mathf.Abs(speedKmh - kmh) < 0.4f && Mathf.Abs(rpm01 - rpm) < 0.01f && Mathf.Approximately(maxKmh, max)) return;
            kmh = speedKmh;
            max = maxKmh;
            rpm = rpm01;
            MarkDirtyRepaint();
        }

        void Draw(MeshGenerationContext mgc)
        {
            var r = contentRect;
            if (float.IsNaN(r.width) || r.width < 10 || r.height < 10) return;
            var c = r.center;
            var outer = Mathf.Min(r.width, r.height) * 0.5f;
            var p = mgc.painter2D;
            var rad = outer - 6f;
            // Backing disc.
            p.fillColor = new Color(6 / 255f, 9 / 255f, 13 / 255f, 0.62f);
            p.BeginPath();
            p.Arc(c, outer, Angle.Degrees(0), Angle.Degrees(360));
            p.ClosePath();
            p.Fill();
            // Track.
            p.lineCap = LineCap.Butt;
            p.lineWidth = 5f;
            p.strokeColor = new Color(1, 1, 1, 0.12f);
            p.BeginPath();
            p.Arc(c, rad, Angle.Degrees(Start), Angle.Degrees(Start + Sweep));
            p.Stroke();
            // Ticks every 20 km/h (longer every 40).
            p.lineWidth = 1.5f;
            for (var v = 0f; v <= max + 0.1f; v += 20f)
            {
                var a = (Start + Sweep * v / max) * Mathf.Deg2Rad;
                var dir = new Vector2(Mathf.Cos(a), Mathf.Sin(a));
                var major = Mathf.RoundToInt(v) % 40 == 0;
                p.strokeColor = new Color(1, 1, 1, major ? 0.55f : 0.28f);
                p.BeginPath();
                p.MoveTo(c + dir * (rad - (major ? 15f : 10f)));
                p.LineTo(c + dir * (rad - 5f));
                p.Stroke();
            }
            // Speed fill: cyan, violet over 80 % of the top speed.
            var f = Mathf.Clamp01(kmh / max);
            if (f > 0.002f)
            {
                p.lineWidth = 5f;
                p.strokeColor = f > 0.8f ? U.Violet : U.Cyan;
                p.BeginPath();
                p.Arc(c, rad, Angle.Degrees(Start), Angle.Degrees(Start + Sweep * f));
                p.Stroke();
            }
            // RPM: thin inner arc.
            var rr = rad - 22f;
            if (rr > 10f)
            {
                p.lineWidth = 2f;
                p.strokeColor = new Color(1, 1, 1, 0.08f);
                p.BeginPath();
                p.Arc(c, rr, Angle.Degrees(Start), Angle.Degrees(Start + Sweep));
                p.Stroke();
                var k = Mathf.Clamp01(rpm);
                if (k > 0.002f)
                {
                    p.strokeColor = k > 0.88f ? new Color(1f, 0.35f, 0.29f, 0.9f) : new Color(0.87f, 0.91f, 0.94f, 0.6f);
                    p.BeginPath();
                    p.Arc(c, rr, Angle.Degrees(Start), Angle.Degrees(Start + Sweep * k));
                    p.Stroke();
                }
            }
        }
    }
}
