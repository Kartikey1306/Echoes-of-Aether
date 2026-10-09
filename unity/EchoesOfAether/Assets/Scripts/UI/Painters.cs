using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UIElements;

namespace EOA
{
    /// <summary>Circular gauge drawn with Painter2D: a ring (ultimate, skip prompt) or a pie wipe (cooldowns).</summary>
    public sealed class RingGauge : VisualElement
    {
        public float Value { get; private set; }
        public float Thickness = 3;
        public Color TrackColor = new(1, 1, 1, 0.12f);
        public Color FillColor = U.Cyan;
        public Color Background = Color.clear;
        /// <summary>Pie mode: filled sector of Value (clockwise from 12 o'clock) instead of a stroked ring.</summary>
        public bool Pie;

        public RingGauge()
        {
            pickingMode = PickingMode.Ignore;
            generateVisualContent += Draw;
        }

        public void Set(float v)
        {
            v = Mathf.Clamp01(v);
            if (Mathf.Abs(v - Value) < 0.002f) return;
            Value = v;
            MarkDirtyRepaint();
        }

        public void SetColors(Color fill, Color track)
        {
            FillColor = fill;
            TrackColor = track;
            MarkDirtyRepaint();
        }

        void Draw(MeshGenerationContext mgc)
        {
            var r = contentRect;
            if (float.IsNaN(r.width) || r.width < 2 || r.height < 2) return;
            var c = r.center;
            var outer = Mathf.Min(r.width, r.height) * 0.5f;
            var p = mgc.painter2D;
            if (Pie)
            {
                // Square slots: radius reaches the corners; the slot clips with overflow: hidden.
                var rad = Mathf.Sqrt(r.width * r.width + r.height * r.height) * 0.5f + 1;
                if (Value <= 0.001f) return;
                p.fillColor = FillColor;
                p.BeginPath();
                if (Value >= 0.999f)
                {
                    p.MoveTo(new Vector2(r.xMin, r.yMin));
                    p.LineTo(new Vector2(r.xMax, r.yMin));
                    p.LineTo(new Vector2(r.xMax, r.yMax));
                    p.LineTo(new Vector2(r.xMin, r.yMax));
                }
                else
                {
                    p.MoveTo(c);
                    p.Arc(c, rad, Angle.Degrees(-90), Angle.Degrees(-90 + 360 * Value));
                }
                p.ClosePath();
                p.Fill();
                return;
            }
            var radius = outer - Thickness * 0.5f;
            if (radius <= 0) return;
            if (Background.a > 0)
            {
                p.fillColor = Background;
                p.BeginPath();
                p.Arc(c, outer, Angle.Degrees(0), Angle.Degrees(360));
                p.ClosePath();
                p.Fill();
            }
            p.lineWidth = Thickness;
            p.lineCap = LineCap.Butt;
            if (TrackColor.a > 0)
            {
                p.strokeColor = TrackColor;
                p.BeginPath();
                p.Arc(c, radius, Angle.Degrees(0), Angle.Degrees(360));
                p.ClosePath();
                p.Stroke();
            }
            if (Value > 0.001f)
            {
                p.strokeColor = FillColor;
                p.BeginPath();
                p.Arc(c, radius, Angle.Degrees(-90), Angle.Degrees(-90 + 360 * Mathf.Min(Value, 0.9999f)));
                p.Stroke();
            }
        }
    }

    /// <summary>
    /// Zone map renderer (full map and rotating minimap) using Painter2D. Coordinates come from
    /// <see cref="ZoneMapData"/> in world metres; labels are pooled child Labels.
    /// </summary>
    public sealed class MapView : VisualElement
    {
        public ZoneMapData Map;
        /// <summary>Full map: fit the zone extents, north up. Otherwise follow Center within RadiusMeters.</summary>
        public bool Fit;
        /// <summary>Minimap: circular frame, clamp the objective to the edge, north indicator.</summary>
        public bool Round;
        public float RadiusMeters = 55;
        public Vector3 Center;
        /// <summary>Camera yaw in degrees (map rotates so the camera's forward points up). Ignored when Fit.</summary>
        public float HeadingDeg;
        public Vector3? Player;
        public float PlayerYawDeg;
        public Vector3? Companion;
        public Vector3? Objective;
        public bool ShowLabels = true;
        public float LabelMinScale = 1.5f;
        public readonly List<Vector3> Npcs = new();
        public readonly List<Vector3> Enemies = new();
        public readonly List<Vector3> Echo = new();

        static readonly Color BgCol = new(5 / 255f, 8 / 255f, 12 / 255f, 0.85f);
        static readonly Color RoadCol = new(60 / 255f, 72 / 255f, 86 / 255f, 0.55f);
        static readonly Color FloorCol = new(96 / 255f, 116 / 255f, 134 / 255f, 0.5f);
        static readonly Color WaterCol = new(60 / 255f, 130 / 255f, 170 / 255f, 0.5f);
        static readonly Color BlockCol = new(30 / 255f, 38 / 255f, 48 / 255f, 0.9f);
        static readonly Color BlockLine = new(140 / 255f, 170 / 255f, 195 / 255f, 0.35f);
        static readonly Color ExitCol = new(95 / 255f, 212 / 255f, 240 / 255f, 0.9f);
        static readonly Color NpcCol = U.Hex("#73e6b0");
        static readonly Color EchoCol = U.Hex("#c39bff");
        static readonly Color EnemyCol = U.Hex("#ff5a4a");
        static readonly Color PartnerCol = U.Hex("#ff2bd6");
        static readonly Color ObjCol = U.Hex("#ffb45e");
        static readonly Color RimCol = new(130 / 255f, 190 / 255f, 220 / 255f, 0.4f);

        readonly List<Label> labels = new();
        readonly List<string> labelRaw = new();
        readonly Label north;
        float scale, cx, cz, rotRad, w, h;

        public MapView()
        {
            pickingMode = PickingMode.Ignore;
            AddToClassList("mapview");
            generateVisualContent += Draw;
            north = U.Label("N", "map-north");
            north.pickingMode = PickingMode.Ignore;
            Add(north);
            RegisterCallback<GeometryChangedEvent>(_ => Refresh());
        }

        /// <summary>Redraw with the current fields.</summary>
        public void Refresh()
        {
            MarkDirtyRepaint();
            LayoutLabels();
        }

        bool Frame()
        {
            var r = contentRect;
            w = r.width;
            h = r.height;
            if (float.IsNaN(w) || w < 4 || h < 4) return false;
            if (Fit && Map != null)
            {
                var mw = Mathf.Max(1, Map.Max.x - Map.Min.x);
                var md = Mathf.Max(1, Map.Max.y - Map.Min.y);
                scale = Mathf.Min(w / mw, h / md) * 0.92f;
                cx = (Map.Min.x + Map.Max.x) * 0.5f;
                cz = (Map.Min.y + Map.Max.y) * 0.5f;
                rotRad = 0;
            }
            else
            {
                scale = w * 0.5f / Mathf.Max(1, RadiusMeters);
                cx = Center.x;
                cz = Center.z;
                rotRad = (Fit ? 0 : HeadingDeg) * Mathf.Deg2Rad;
            }
            return true;
        }

        /// <summary>World (x, z) to local pixels; the heading direction points up.</summary>
        Vector2 Tx(float x, float z)
        {
            float dx = x - cx, dz = z - cz;
            float c = Mathf.Cos(rotRad), s = Mathf.Sin(rotRad);
            var rx = dx * c - dz * s;
            var rz = dx * s + dz * c;
            return new Vector2(w * 0.5f + rx * scale, h * 0.5f - rz * scale);
        }

        void Draw(MeshGenerationContext mgc)
        {
            if (!Frame()) return;
            var p = mgc.painter2D;
            var mid = new Vector2(w * 0.5f, h * 0.5f);

            p.fillColor = BgCol;
            p.BeginPath();
            if (Round) p.Arc(mid, w * 0.5f - 1, Angle.Degrees(0), Angle.Degrees(360));
            else { p.MoveTo(Vector2.zero); p.LineTo(new Vector2(w, 0)); p.LineTo(new Vector2(w, h)); p.LineTo(new Vector2(0, h)); }
            p.ClosePath();
            p.Fill();

            if (Map != null)
            {
                // Minimap: only shapes that can reach the disc (the open city has thousands; tessellating all of them
                // 20 times a second cost milliseconds of main thread).
                var cull = !Fit;
                var reach = (w * 0.5f + 4) / Mathf.Max(0.001f, scale);
                foreach (var s in Map.Rects)
                {
                    if (s == null) continue;
                    if (cull)
                    {
                        var ext = reach + (Mathf.Abs(s.Size.x) + Mathf.Abs(s.Size.y)) * 0.5f;
                        float ddx = s.Center.x - cx, ddz = s.Center.y - cz;
                        if (ddx * ddx + ddz * ddz > ext * ext) continue;
                    }
                    p.fillColor = s.Kind switch { MapRectKind.Road => RoadCol, MapRectKind.Floor => FloorCol, MapRectKind.Water => WaterCol, _ => BlockCol };
                    float hw = s.Size.x * 0.5f, hd = s.Size.y * 0.5f;
                    var yr = s.RotationDeg * Mathf.Deg2Rad;
                    float cy = Mathf.Cos(yr), sy = Mathf.Sin(yr);
                    p.BeginPath();
                    for (var k = 0; k < 4; k++)
                    {
                        var a = k == 0 || k == 3 ? -hw : hw;
                        var b = k < 2 ? -hd : hd;
                        var pt = Tx(s.Center.x + a * cy + b * sy, s.Center.y - a * sy + b * cy);
                        if (k == 0) p.MoveTo(pt); else p.LineTo(pt);
                    }
                    p.ClosePath();
                    p.Fill();
                    if (s.Kind == MapRectKind.Block)
                    {
                        p.strokeColor = BlockLine;
                        p.lineWidth = 1;
                        p.Stroke();
                    }
                }
                foreach (var l in Map.Lines)
                {
                    if (l == null) continue;
                    if (cull)
                    {
                        // Segment vs disc: distance from the centre to the closest point of the segment.
                        var a = new Vector2(l.From.x - cx, l.From.y - cz);
                        var ab = new Vector2(l.To.x - l.From.x, l.To.y - l.From.y);
                        var tt = ab.sqrMagnitude > 1e-6f ? Mathf.Clamp01(-Vector2.Dot(a, ab) / ab.sqrMagnitude) : 0;
                        if ((a + ab * tt).sqrMagnitude > (reach + l.Width) * (reach + l.Width)) continue;
                    }
                    p.strokeColor = l.Color;
                    p.lineWidth = Mathf.Max(1, l.Width * (Fit ? 1 : 0.8f));
                    p.lineCap = LineCap.Round;
                    p.BeginPath();
                    p.MoveTo(Tx(l.From.x, l.From.y));
                    p.LineTo(Tx(l.To.x, l.To.y));
                    p.Stroke();
                }
                foreach (var m in Map.Markers)
                    if (m != null && m.Kind == MapMarkerKind.Exit) Dot(p, m.Position, ExitCol, 4, Shape.Tri);
            }
            foreach (var n in Npcs) Dot(p, n, NpcCol, 3, Shape.Circle);
            foreach (var e in Echo) Dot(p, e, EchoCol, 3, Shape.Diamond);
            foreach (var e in Enemies) Dot(p, e, EnemyCol, 3, Shape.Circle);
            if (Companion.HasValue) Dot(p, Companion.Value, PartnerCol, 3, Shape.Circle);
            if (Objective.HasValue)
            {
                Dot(p, Objective.Value, new Color(ObjCol.r, ObjCol.g, ObjCol.b, 0.3f), 9, Shape.Diamond);
                Dot(p, Objective.Value, ObjCol, 6, Shape.Diamond);
            }
            if (Player.HasValue)
            {
                var pos = Tx(Player.Value.x, Player.Value.z);
                var ang = (PlayerYawDeg - (Fit ? 0 : HeadingDeg)) * Mathf.Deg2Rad;
                float ca = Mathf.Cos(ang), sa = Mathf.Sin(ang);
                var k = Fit ? 1.3f : 1f;
                Vector2 R(float x, float y) => pos + new Vector2(x * ca - y * sa, x * sa + y * ca) * k;
                p.fillColor = Color.white;
                p.BeginPath();
                p.MoveTo(R(0, -8));
                p.LineTo(R(6, 6));
                p.LineTo(R(0, 3));
                p.LineTo(R(-6, 6));
                p.ClosePath();
                p.Fill();
            }
            if (Round)
            {
                p.strokeColor = RimCol;
                p.lineWidth = 2;
                p.BeginPath();
                p.Arc(mid, w * 0.5f - 1, Angle.Degrees(0), Angle.Degrees(360));
                p.ClosePath();
                p.Stroke();
            }
        }

        enum Shape { Circle, Diamond, Tri }

        void Dot(Painter2D p, Vector3 world, Color col, float r, Shape shape)
        {
            var pt = Tx(world.x, world.z);
            if (Round && shape == Shape.Diamond)
            {
                var mid = new Vector2(w * 0.5f, h * 0.5f);
                var d = pt - mid;
                var max = w * 0.5f - 10;
                if (d.magnitude > max) pt = mid + d.normalized * max;
            }
            else if (pt.x < -20 || pt.y < -20 || pt.x > w + 20 || pt.y > h + 20) return;
            p.fillColor = col;
            p.BeginPath();
            switch (shape)
            {
                case Shape.Circle:
                    p.Arc(pt, r, Angle.Degrees(0), Angle.Degrees(360));
                    break;
                case Shape.Diamond:
                    p.MoveTo(pt + new Vector2(0, -r));
                    p.LineTo(pt + new Vector2(r, 0));
                    p.LineTo(pt + new Vector2(0, r));
                    p.LineTo(pt + new Vector2(-r, 0));
                    break;
                default:
                    p.MoveTo(pt + new Vector2(0, -r));
                    p.LineTo(pt + new Vector2(r, r));
                    p.LineTo(pt + new Vector2(-r, r));
                    break;
            }
            p.ClosePath();
            p.Fill();
        }

        void LayoutLabels()
        {
            var ok = Frame();
            var n = 0;
            if (ok && Map != null && ShowLabels && (Fit || scale > LabelMinScale))
            {
                foreach (var l in Map.Labels)
                {
                    if (l == null || string.IsNullOrEmpty(l.Text)) continue;
                    var pt = Tx(l.Position.x, l.Position.y);
                    if (pt.x < 0 || pt.y < 0 || pt.x > w || pt.y > h) continue;
                    if (n >= labels.Count)
                    {
                        var lab = U.Label("", "map-label");
                        lab.pickingMode = PickingMode.Ignore;
                        Insert(0, lab);
                        labels.Add(lab);
                        labelRaw.Add(null);
                    }
                    var li = n++;
                    var e = labels[li];
                    if (!ReferenceEquals(labelRaw[li], l.Text)) { labelRaw[li] = l.Text; e.text = U.Up(l.Text); }
                    e.style.left = pt.x;
                    e.style.top = pt.y;
                    e.EnableInClassList("small", !Fit);
                    U.Show(e, true);
                }
            }
            for (var i = n; i < labels.Count; i++) U.Show(labels[i], false);

            U.Show(north, ok && Round);
            if (ok && Round)
            {
                // North (+Z) rotates with the heading.
                var a = (Fit ? 0 : HeadingDeg) * Mathf.Deg2Rad;
                var rr = w * 0.5f - 12;
                north.style.left = w * 0.5f - Mathf.Sin(a) * rr;
                north.style.top = h * 0.5f - Mathf.Cos(a) * rr;
            }
        }
    }
}
