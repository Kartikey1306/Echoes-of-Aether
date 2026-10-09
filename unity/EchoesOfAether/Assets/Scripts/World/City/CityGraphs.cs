using System.Collections.Generic;
using UnityEngine;
using static EOA.ProtoSpace;

namespace EOA
{
    /// <summary>
    /// Traffic network of the open city (Unity space): intersections, directed lanes (right-hand traffic, one
    /// travel lane per direction) and fixed-time signals. Built once from <see cref="CityLayout"/>.
    /// </summary>
    public sealed class RoadGraph
    {
        public const float LaneOffset = 2.2f;
        /// <summary>Signal cycle: [0,13) traffic along Z green, [13,15) all red, [15,28) traffic along X green, [28,30) all red.</summary>
        public const float Cycle = 30f;

        public Vector3[] Node;
        public float[] Offset;
        public int[] LaneFrom, LaneTo, Reverse;
        /// <summary>0 = lane runs along Unity X, 1 = along Unity Z.</summary>
        public byte[] LaneAxis;
        public Vector3[] LaneStart, LaneEnd, LaneDir;
        public float[] LaneLen;
        public int[][] Out;
        public int Nodes => Node.Length;
        public int Lanes => LaneLen.Length;

        /// <summary>Prototype (x, z) of each node (for the pedestrian graph and dressing).</summary>
        public readonly Dictionary<(int, int), int> ByProto = new();

        public static int Key(float v) => Mathf.RoundToInt(v * 4);

        public float Phase(int node, float t)
        {
            var p = (t + Offset[node]) % Cycle;
            return p < 0 ? p + Cycle : p;
        }

        public bool CarGreen(int node, int axis, float t)
        {
            var p = Phase(node, t);
            return axis == 1 ? p < 13f : p >= 15f && p < 28f;
        }

        /// <summary>Pedestrians may start crossing a road whose traffic runs along `axis` (first 6 s of that road's red).</summary>
        public bool PedStart(int node, int axis, float t)
        {
            var p = Phase(node, t);
            return axis == 1 ? p >= 15f && p < 21f : p < 6f;
        }

        /// <summary>0: Z green, 1: all red, 2: X green, 3: all red.</summary>
        public int PhaseIndex(int node, float t)
        {
            var p = Phase(node, t);
            return p < 13f ? 0 : p < 15f ? 1 : p < 28f ? 2 : 3;
        }

        public Vector3 LanePoint(int lane, float s) => LaneStart[lane] + LaneDir[lane] * s;

        public static RoadGraph Build()
        {
            var g = new RoadGraph();
            var nodes = new List<Vector3>();
            for (var i = 0; i < CityLayout.XL.Length; i++)
            for (var j = 0; j < CityLayout.ZL.Length; j++)
            {
                float x = CityLayout.XL[i], z = CityLayout.ZL[j];
                if (!CityLayout.NodeExists(x, z)) continue;
                g.ByProto[(Key(x), Key(z))] = nodes.Count;
                nodes.Add(V(x, 0, z));
            }
            var segs = new List<(int a, int b)>();
            foreach (var x in CityLayout.XL)
                for (var j = 0; j < CityLayout.ZL.Length - 1; j++)
                {
                    float za = CityLayout.ZL[j], zb = CityLayout.ZL[j + 1];
                    if (!CityLayout.XSeg(x, za, zb)) continue;
                    if (g.ByProto.TryGetValue((Key(x), Key(za)), out var a) && g.ByProto.TryGetValue((Key(x), Key(zb)), out var b)) segs.Add((a, b));
                }
            foreach (var z in CityLayout.ZL)
                for (var i = 0; i < CityLayout.XL.Length - 1; i++)
                {
                    float xa = CityLayout.XL[i], xb = CityLayout.XL[i + 1];
                    if (!CityLayout.ZSeg(z, xa, xb)) continue;
                    if (g.ByProto.TryGetValue((Key(xa), Key(z)), out var a) && g.ByProto.TryGetValue((Key(xb), Key(z)), out var b)) segs.Add((a, b));
                }
            g.Node = nodes.ToArray();
            g.Offset = new float[g.Node.Length];
            for (var n = 0; n < g.Node.Length; n++) g.Offset[n] = (n * 7.37f + (n % 3) * 4.1f) % Cycle;
            var count = segs.Count * 2;
            g.LaneFrom = new int[count]; g.LaneTo = new int[count]; g.Reverse = new int[count];
            g.LaneAxis = new byte[count];
            g.LaneStart = new Vector3[count]; g.LaneEnd = new Vector3[count]; g.LaneDir = new Vector3[count];
            g.LaneLen = new float[count];
            var outs = new List<int>[g.Node.Length];
            for (var n = 0; n < outs.Length; n++) outs[n] = new List<int>(4);
            for (var s = 0; s < segs.Count; s++)
            {
                for (var k = 0; k < 2; k++)
                {
                    var l = s * 2 + k;
                    var from = k == 0 ? segs[s].a : segs[s].b;
                    var to = k == 0 ? segs[s].b : segs[s].a;
                    var d = (g.Node[to] - g.Node[from]).normalized;
                    var right = Vector3.Cross(Vector3.up, d);
                    g.LaneFrom[l] = from; g.LaneTo[l] = to; g.Reverse[l] = s * 2 + (1 - k);
                    g.LaneAxis[l] = (byte)(Mathf.Abs(d.x) > 0.5f ? 0 : 1);
                    g.LaneDir[l] = d;
                    g.LaneStart[l] = g.Node[from] + d * CityLayout.Stop + right * LaneOffset;
                    g.LaneEnd[l] = g.Node[to] - d * CityLayout.Stop + right * LaneOffset;
                    g.LaneLen[l] = Vector3.Distance(g.LaneStart[l], g.LaneEnd[l]);
                    outs[from].Add(l);
                }
            }
            g.Out = new int[outs.Length][];
            for (var n = 0; n < outs.Length; n++) g.Out[n] = outs[n].ToArray();
            return g;
        }
    }

    /// <summary>
    /// Sidewalk network for pedestrians (Unity space): a loop along the sidewalk centreline of every block (and the
    /// plaza reserve ring), joined by zebra crossings at intersections that follow the traffic signals.
    /// </summary>
    public sealed class PedGraph
    {
        public const byte Sidewalk = 0, Crossing = 1;

        public Vector3[] Pos;
        public int[] A, B;
        public float[] Len;
        public Vector3[] Dir, Side;
        public byte[] Kind;
        /// <summary>Crossings: road node whose signal governs them and the traffic axis of the crossed road.</summary>
        public int[] SignalNode;
        public byte[] SignalAxis;
        public int[][] Adj;
        public int Nodes => Pos.Length;
        public int Edges => Len.Length;

        public int Other(int edge, int node) => A[edge] == node ? B[edge] : A[edge];

        public static PedGraph Build(RoadGraph roads)
        {
            const float y = CityLayout.Curb;
            const float ring = CityLayout.Ring;
            // Rings in prototype space: every block plus the plaza reserve.
            var rings = new List<PRect>();
            for (var i = 0; i < CityLayout.XL.Length - 1; i++)
            for (var j = 0; j < CityLayout.ZL.Length - 1; j++)
            {
                float x1 = CityLayout.XL[i], x2 = CityLayout.XL[i + 1], z1 = CityLayout.ZL[j], z2 = CityLayout.ZL[j + 1];
                if (CityLayout.InReserveCell(x1, x2, z1, z2)) continue;
                rings.Add(new PRect(x1 + ring, z1 + ring, x2 - ring, z2 - ring));
            }
            rings.Add(new PRect(-CityLayout.ResX + ring, CityLayout.ResZ0 + ring, CityLayout.ResX - ring, CityLayout.ResZ1 - ring));

            var pos = new List<Vector2>();
            var ids = new Dictionary<(int, int), int>();
            int NodeAt(float x, float z)
            {
                var key = (RoadGraph.Key(x), RoadGraph.Key(z));
                if (ids.TryGetValue(key, out var id)) return id;
                id = pos.Count;
                pos.Add(new Vector2(x, z));
                ids[key] = id;
                return id;
            }
            foreach (var r in rings) { NodeAt(r.X0, r.Z0); NodeAt(r.X1, r.Z0); NodeAt(r.X1, r.Z1); NodeAt(r.X0, r.Z1); }

            // Crossings at every arm of every intersection.
            var cross = new List<(int a, int b, int node, byte axis)>();
            for (var i = 0; i < CityLayout.XL.Length; i++)
            for (var j = 0; j < CityLayout.ZL.Length; j++)
            {
                float x = CityLayout.XL[i], z = CityLayout.ZL[j];
                if (!roads.ByProto.TryGetValue((RoadGraph.Key(x), RoadGraph.Key(z)), out var rn)) continue;
                // Arms along x (z-line road; traffic along Unity X → axis 0) and along z (axis 1).
                if (i < CityLayout.XL.Length - 1 && CityLayout.ZSeg(z, x, CityLayout.XL[i + 1])) cross.Add((NodeAt(x + ring, z - ring), NodeAt(x + ring, z + ring), rn, 0));
                if (i > 0 && CityLayout.ZSeg(z, CityLayout.XL[i - 1], x)) cross.Add((NodeAt(x - ring, z - ring), NodeAt(x - ring, z + ring), rn, 0));
                if (j < CityLayout.ZL.Length - 1 && CityLayout.XSeg(x, z, CityLayout.ZL[j + 1])) cross.Add((NodeAt(x - ring, z + ring), NodeAt(x + ring, z + ring), rn, 1));
                if (j > 0 && CityLayout.XSeg(x, CityLayout.ZL[j - 1], z)) cross.Add((NodeAt(x - ring, z - ring), NodeAt(x + ring, z - ring), rn, 1));
            }

            // Ring edges: nodes on each side of each ring, sorted along the side.
            var edges = new List<(int a, int b, byte kind, int node, byte axis)>();
            var onSide = new List<int>();
            foreach (var r in rings)
            {
                for (var side = 0; side < 4; side++)
                {
                    onSide.Clear();
                    for (var n = 0; n < pos.Count; n++)
                    {
                        var p = pos[n];
                        var hit = side switch
                        {
                            0 => Mathf.Abs(p.y - r.Z0) < 0.05f && p.x >= r.X0 - 0.05f && p.x <= r.X1 + 0.05f,
                            1 => Mathf.Abs(p.x - r.X1) < 0.05f && p.y >= r.Z0 - 0.05f && p.y <= r.Z1 + 0.05f,
                            2 => Mathf.Abs(p.y - r.Z1) < 0.05f && p.x >= r.X0 - 0.05f && p.x <= r.X1 + 0.05f,
                            _ => Mathf.Abs(p.x - r.X0) < 0.05f && p.y >= r.Z0 - 0.05f && p.y <= r.Z1 + 0.05f,
                        };
                        if (hit) onSide.Add(n);
                    }
                    var alongX = side == 0 || side == 2;
                    onSide.Sort((a, b) => alongX ? pos[a].x.CompareTo(pos[b].x) : pos[a].y.CompareTo(pos[b].y));
                    for (var k = 0; k < onSide.Count - 1; k++)
                        if ((pos[onSide[k]] - pos[onSide[k + 1]]).sqrMagnitude > 0.01f) edges.Add((onSide[k], onSide[k + 1], Sidewalk, -1, 0));
                }
            }
            foreach (var c in cross) edges.Add((c.a, c.b, Crossing, c.node, c.axis));

            var g = new PedGraph();
            g.Pos = new Vector3[pos.Count];
            for (var n = 0; n < pos.Count; n++) g.Pos[n] = V(pos[n].x, y, pos[n].y);
            var e = edges.Count;
            g.A = new int[e]; g.B = new int[e]; g.Len = new float[e]; g.Dir = new Vector3[e]; g.Side = new Vector3[e];
            g.Kind = new byte[e]; g.SignalNode = new int[e]; g.SignalAxis = new byte[e];
            var adj = new List<int>[pos.Count];
            for (var n = 0; n < adj.Length; n++) adj[n] = new List<int>(4);
            for (var k = 0; k < e; k++)
            {
                var (a, b, kind, node, axis) = edges[k];
                g.A[k] = a; g.B[k] = b; g.Kind[k] = kind; g.SignalNode[k] = node; g.SignalAxis[k] = axis;
                var d = g.Pos[b] - g.Pos[a]; d.y = 0;
                g.Len[k] = d.magnitude;
                g.Dir[k] = d.normalized;
                g.Side[k] = Vector3.Cross(Vector3.up, g.Dir[k]);
                adj[a].Add(k); adj[b].Add(k);
            }
            g.Adj = new int[adj.Length][];
            for (var n = 0; n < adj.Length; n++) g.Adj[n] = adj[n].ToArray();
            return g;
        }
    }
}
