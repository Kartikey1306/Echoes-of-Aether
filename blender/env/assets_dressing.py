"""City dressing: the dense cyberpunk-street clutter layer. Cables and lantern strings slung between facades, wall
conduits and pipe runs, vents, electrical boxes and cabinets, lamps, soggy cardboard, drums, pallets, sandbags,
makeshift barricades, chain-link fence, scaffolding, dead plants, rebar rubble, facade AC stacks, dishes, antenna
clusters, a rooftop water tower and a roof clutter pack.

Pivot conventions used here (all documented per asset in `notes`):
  base-centre   floor level, centre of the footprint (default).
  back-centre   on the wall plane (Blender y=0, Unity z=0) at the centre of the item; the item sticks out toward
                Unity +Z. Place it on any wall at any height.
  wall-base     on the wall plane at the item's lowest point (floor-standing against a wall, or the bottom of a
                facade stack), centred in X.
  left-attach   for slung cables / lantern strings: the left attach point on the left wall; the span runs toward
                Unity -X and the far attach point is listed in `attach`.
  wall-axis     pipe runs: on the wall plane at the height of the pipe axis; open ends are listed in `ports`.

Shared hardware helpers (bolts, LEDs, conduit, clamps, grime streaks, cables) live here and are reused by
assets_rooftop.py and assets_debris.py.
"""
import math
import random

import bmesh
from mathutils import Vector

import envkit as K
from envkit import box, cyl, lathe, tube, torus, beam, extrude, rock, boolean, inset, faces_where, detail

# ============================================================================================== shared helpers
NEON_HEX = {"magenta": "#ff2bd6", "pink": "#ff4f9a", "cyan": "#00e5ff", "blue": "#3d7bff", "yellow": "#ffe14d",
            "violet": "#9b5cff", "warm": "#ffb070", "red": "#ff3a2e", "green": "#52ff99", "amber": "#ffa21f",
            "white": "#e8f2ff"}


def light(pos, color, rng=4.0, intensity=1.0):
    """Light anchor dict (pos in Blender coords)."""
    return {"position": [round(v, 3) for v in K.to_unity_vec(pos)], "color": NEON_HEX.get(color, color),
            "range": rng, "intensity": intensity}


def U(v):
    return [round(float(c), 3) for c in K.to_unity_vec(v)]


def hexbolt(at, axis="-y", r=0.008, h=0.006, mat="metal_bare"):
    """Hex bolt head sitting on a surface at `at`, protruding along `axis` ('-y', '+y', '+z', '-z', '+x', '-x')."""
    if not detail():
        return None
    x, y, z = at
    s = -1 if axis[0] == "-" else 1
    a = axis[1]
    if a == "y":
        return cyl(r, h, 6, at=(x, y if s > 0 else y - h, z), axis="Y", mat=mat, start=0.0)
    if a == "x":
        return cyl(r, h, 6, at=(x if s > 0 else x - h, y, z), axis="X", mat=mat, start=0.0)
    return cyl(r, h, 6, at=(x, y, z if s > 0 else z - h), mat=mat, start=0.0)


def bolt_grid(xs, zs, y, axis="-y", r=0.008, h=0.006, mat="metal_bare"):
    if not detail():
        return
    for x in xs:
        for z in zs:
            hexbolt((x, y, z), axis, r, h, mat)


def led(at, mat="emit_green", r=0.006, axis="-y", bezel=True):
    """Status LED: black bezel + emissive lens protruding along axis (front faces)."""
    x, y, z = at
    if axis == "-y":
        if bezel:
            cyl(r * 1.7, 0.003, 8, at=(x, y - 0.003, z), axis="Y", mat="black")
        cyl(r, 0.005, 8, at=(x, y - 0.006, z), axis="Y", mat=mat)
    elif axis == "+z":
        if bezel:
            cyl(r * 1.7, 0.003, 8, at=(x, y, z), mat="black")
        cyl(r, 0.005, 8, at=(x, y, z + 0.001), mat=mat)
    elif axis in ("+x", "-x"):
        s = 1 if axis[0] == "+" else -1
        if bezel:
            cyl(r * 1.7, 0.003, 8, at=(x if s > 0 else x - 0.003, y, z), axis="X", mat="black")
        cyl(r, 0.005, 8, at=(x if s > 0 else x - 0.006, y, z), axis="X", mat=mat)


def streak(x, z_top, length, width, y, facing="-y", mat="metal_rusted", taper=0.45, seed=0):
    """Grime / rust run-off streak: a thin tapered sliver lying on a surface (LOD0 only). `y` is the surface
    coordinate along the facing axis (y for +-y faces, x for +-x faces)."""
    if not detail():
        return None
    rnd = random.Random(seed)
    w0, w1 = width, width * taper
    wob = rnd.uniform(-0.25, 0.25) * width
    poly = [(-w0 / 2, 0.0), (w0 / 2, 0.0), (w1 / 2 + wob, -length), (-w1 / 2 + wob, -length)]
    if facing in ("-y", "+y"):
        s = extrude([(x + a, z_top + b) for a, b in poly], 0.0016, plane="XZ", mat=mat, name="streak")
        s.move(0, y + (-0.0009 if facing == "-y" else 0.0009), 0)
    else:
        s = extrude([(x + a, z_top + b) for a, b in poly], 0.0016, plane="YZ", mat=mat, name="streak")
        s.move(y + (0.0009 if facing == "+x" else -0.0009), 0, 0)
    return s


def catenary(p0, p1, sag, n):
    p0, p1 = Vector(p0), Vector(p1)
    return [p0.lerp(p1, i / n) + Vector((0, 0, -4.0 * sag * (i / n) * (1 - i / n))) for i in range(n + 1)]


def ring_at(c, t, R, r, n_major=8, n_minor=4, mat="plastic_dark"):
    """Closed ring (cable tie, clamp band) of radius R around point c, in the plane normal to tangent t."""
    t = Vector(t).normalized()
    up = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((1, 0, 0))
    a = t.cross(up).normalized()
    b = t.cross(a).normalized()
    c = Vector(c)
    pts = [c + (a * math.cos(k * math.tau / n_major) + b * math.sin(k * math.tau / n_major)) * R for k in range(n_major)]
    return tube(pts, r, n_minor, mat, "ring", closed=True)


def arc_pts(center, R, a0, a1, n, plane="XZ"):
    """Points on an arc (degrees) in a plane through `center`."""
    cx, cy, cz = center
    out = []
    for i in range(n + 1):
        a = math.radians(a0 + (a1 - a0) * i / n)
        if plane == "XZ":
            out.append((cx + R * math.cos(a), cy, cz + R * math.sin(a)))
        elif plane == "YZ":
            out.append((cx, cy + R * math.cos(a), cz + R * math.sin(a)))
        else:
            out.append((cx + R * math.cos(a), cy + R * math.sin(a), cz))
    return out


def bend_path(pts, r_bend, n=4):
    """Polyline with rounded corners (fillets of radius r_bend, n segments each)."""
    P = [Vector(p) for p in pts]
    out = [P[0]]
    for i in range(1, len(P) - 1):
        a, b, c = P[i - 1], P[i], P[i + 1]
        d0, d1 = (b - a), (c - b)
        rr = min(r_bend, d0.length * 0.45, d1.length * 0.45)
        d0.normalize()
        d1.normalize()
        p0 = b - d0 * rr
        p1 = b + d1 * rr
        for k in range(n + 1):
            t = k / n
            q = (1 - t) ** 2 * p0 + 2 * (1 - t) * t * b + t * t * p1
            out.append(q)
    out.append(P[-1])
    return [tuple(p) for p in out]


def conduit(pts, r=0.016, mat="metal_bare", bend=0.08, n=8, fittings=True):
    """Rigid conduit along a polyline with bends, couplings at the ends."""
    path = bend_path(pts, bend, 4 if detail() else 2)
    tube(path, r, n, mat, "conduit")
    if fittings and detail():
        for i0, i1 in ((0, 1), (-1, -2)):
            p, q = Vector(path[i0]), Vector(path[i1])
            d = (q - p).normalized()
            tube([tuple(p), tuple(p + d * 0.035)], r * 1.35, 6, "metal_bare", "fitting")


def strap(at, axis_dir, r, wall_axis="+y", mat="metal_bare"):
    """One-hole conduit strap: half ring over a conduit lying on a wall (LOD0 only)."""
    if not detail():
        return
    c = Vector(at)
    t = Vector(axis_dir).normalized()
    w = Vector((0, 1, 0)) if wall_axis == "+y" else Vector((0, 0, -1))
    a = t.cross(w).normalized()
    pts = []
    for k in range(7):
        ang = math.pi * k / 6
        pts.append(c + (a * math.cos(ang) - w * math.sin(ang)) * (r + 0.004))
    pts = [pts[0] + w * 0.0] + pts
    tube(pts, 0.0035, 4, mat, "strap", caps=True)
    foot = c + a * (r + 0.016) + w * (r - 0.002)
    if wall_axis == "+y":
        box(0.018 if abs(a.x) > 0.5 else 0.03, 0.003, 0.03 if abs(a.x) > 0.5 else 0.018, at=tuple(foot), mat=mat)
        hexbolt(tuple(foot - w * 0.0015), "-y", 0.004, 0.003)


def cable_run(p0, p1, sag, r, mat="rubber", n=24):
    return tube(catenary(p0, p1, sag, K.seg(n, 6)), r, 6, mat, "cable")


def warning_triangle(at, size=0.08, facing="-y"):
    """Yellow hazard triangle with an abstract black bolt pictogram (no text)."""
    x, y, z = at
    s = size
    tri = [(-s / 2, -s * 0.43), (s / 2, -s * 0.43), (0, s * 0.43)]
    t = extrude([(x + a, z + b) for a, b in tri], 0.002, plane="XZ", mat="metal_painted_yellow")
    t.move(0, y - 0.001, 0)
    if detail():
        bolt = [(-0.08, 0.2), (0.12, 0.2), (0.0, 0.02), (0.1, 0.02), (-0.1, -0.3), (-0.02, -0.04), (-0.12, -0.04)]
        g = extrude([(x + a * s, z + b * s) for a, b in bolt], 0.0016, plane="XZ", mat="black")
        g.move(0, y - 0.0028, 0)


def hazard_stripes(x0, x1, z0, z1, y, n=None, facing="-y"):
    """Yellow/black diagonal hazard band on a front face (parallelograms)."""
    w = x1 - x0
    h = z1 - z0
    n = n or max(2, int(w / (h * 1.4)))
    box(w, 0.002, h, at=((x0 + x1) / 2, y - 0.001, (z0 + z1) / 2), mat="black")
    if not detail() and K.LOD > 1:
        return
    step = w / n
    for i in range(n):
        a = x0 + i * step
        poly = [(a, z0), (a + step * 0.5, z0), (min(x1, a + step * 0.5 + h * 0.6), z1), (min(x1, a + h * 0.6), z1)]
        poly = [(min(max(px, x0), x1), pz) for px, pz in poly]
        if poly[3][0] - poly[0][0] < 1e-4 and poly[2][0] - poly[1][0] < 1e-4:
            continue
        p = extrude(poly, 0.002, plane="XZ", mat="metal_painted_yellow")
        p.move(0, y - 0.0022, 0)


def wall_plate(x, z, w, h, t=0.012, mat="metal_dark", bolts=True, y=0.0):
    """Mounting plate flat on the wall (back at y=0), facing -Y."""
    box(w, t, h, at=(x, y - t / 2, z), mat=mat, bevel=0.003)
    if bolts:
        bolt_grid((x - w / 2 + 0.022, x + w / 2 - 0.022), (z - h / 2 + 0.022, z + h / 2 - 0.022), y - t, r=0.007, h=0.005)


# ============================================================================================== slung cables
def _side_anchor(x, facing, z=0.0, kind="clamp"):
    """Wall anchor on a wall perpendicular to X (wall plane at x, the anchor sticks out toward facing*X).
    Returns the bundle attach point."""
    f = facing
    box(0.012, 0.13, 0.17, at=(x + f * 0.006, 0, z), mat="metal_dark", bevel=0.003)
    if detail():
        for yy in (-0.045, 0.045):
            for zz in (z - 0.06, z + 0.06):
                cyl(0.007, 0.006, 6, at=(x + (f * 0.012 if f > 0 else -0.018), yy, zz), axis="X", mat="metal_bare", start=0)
    # standoff arm with gusset
    box(0.13, 0.028, 0.028, at=(x + f * 0.077, 0, z + 0.03), mat="metal_dark", bevel=0.003)
    beam((x + f * 0.014, 0, z - 0.06), (x + f * 0.12, 0, z + 0.02), 0.012, 0.02, mat="metal_dark")
    # eye / clamp at the tip
    t = torus(0.02, 0.005, n_major=10, n_minor=4, mat="metal_bare")
    t.rot(x=90).move(x + f * 0.14, 0, z + 0.0)
    return Vector((x + f * 0.15, 0, z - 0.03))


def cable_bundle(L=4.0, sag=0.35, seed=3):
    """Bundle of power / data cables slung between two walls. Pivot = left attach point (wall plane)."""
    rnd = random.Random(seed)
    a = _side_anchor(0.0, 1)
    b = _side_anchor(L, -1)
    n = K.seg(max(20, int(L * 4.5)), 8)
    # messenger wire (steel), least sag
    tube(catenary(a, b, sag * 0.92, n), 0.004, 4, "metal_bare", "messenger")
    specs = [(0.020, 0.000, 0.016, "rubber", 1.00), (-0.016, -0.006, 0.012, "rubber", 1.03),
             (0.002, -0.026, 0.019, "rubber", 1.05), (-0.010, 0.016, 0.010, "plastic_dark", 1.02),
             (0.022, -0.020, 0.009, "rubber", 1.08)]
    if L > 6:
        specs.append((-0.024, -0.024, 0.013, "rubber", 1.06))
    turns = L * 0.35
    paths = []
    for k, (dy, dz, r, m, sk) in enumerate(specs):
        pts = []
        base = catenary(a + Vector((0, 0, -0.025)), b + Vector((0, 0, -0.025)), sag * sk, n)
        for i, p in enumerate(base):
            t = i / n
            ang = t * turns * math.tau + k
            spread = 1.0 + 0.6 * math.sin(math.pi * t)
            oy = (dy * math.cos(ang) - dz * math.sin(ang)) * spread
            oz = (dy * math.sin(ang) + dz * math.cos(ang)) * spread
            pts.append(p + Vector((0, oy, oz)))
        paths.append(pts)
        tube(pts, r, 8 if r > 0.015 else 6, m, "cable")
    # drooping service loop: one cable leaves the bundle and hangs lower
    if detail() or L > 6:
        t0, t1 = (0.22, 0.48) if L > 6 else (0.3, 0.62)
        p0 = Vector(paths[1][int(t0 * n)])
        p1 = Vector(paths[1][int(t1 * n)])
        tube(catenary(p0, p1, 0.22 if L > 6 else 0.12, K.seg(14, 6)), 0.011, 6, "rubber", "loop")
    # cable ties + tags
    if detail():
        nt = int(L / 0.55)
        main = catenary(a + Vector((0, 0, -0.03)), b + Vector((0, 0, -0.03)), sag, n)
        for i in range(1, nt):
            t = i / nt + rnd.uniform(-0.02, 0.02)
            j = min(n - 1, max(1, int(t * n)))
            c = main[j]
            tng = main[j + 1] - main[j - 1]
            ring_at(c, tng, 0.04 + 0.022 * math.sin(math.pi * t), 0.0035, 8, 4, "plastic_dark")
        # hanging tag + splice sleeve
        j = int(0.7 * n)
        c = main[j]
        box(0.006, 0.05, 0.075, at=(c.x, c.y - 0.03, c.z - 0.09), mat="metal_painted_yellow", bevel=0.002)
        tube([(c.x, c.y - 0.03, c.z - 0.04), (c.x, c.y - 0.03, c.z - 0.052)], 0.002, 4, "plastic_dark")
        if L > 6:
            j = int(0.42 * n)
            c, tng = main[j], main[j + 1] - main[j - 1]
            tube([c - tng.normalized() * 0.14, c + tng.normalized() * 0.14], 0.05, 10, "plastic_dark", "splice")
            ring_at(c - tng.normalized() * 0.13, tng, 0.05, 0.006, 10, 4, "black")
            ring_at(c + tng.normalized() * 0.13, tng, 0.05, 0.006, 10, 4, "black")
    return {"colliders": "none", "attach": [U((0, 0, 0)), U((L, 0, 0))], "span": L, "sag": sag}


def lantern_string(L=4.0, sag=0.32, seed=5):
    """String of paper / LED lanterns slung between two walls. Pivot = left attach point (wall plane)."""
    rnd = random.Random(seed)
    a = _side_anchor(0.0, 1)
    b = _side_anchor(L, -1)
    n = K.seg(32, 10)
    rope = catenary(a, b, sag, n)
    tube(rope, 0.005, 6, "rubber", "rope")
    if detail():  # twisted second strand (power lead) wrapping the rope
        tube([p + Vector((0, 0.008 * math.cos(i * 1.7), 0.008 * math.sin(i * 1.7))) for i, p in enumerate(rope)], 0.003, 4, "plastic_dark")
    colors = ["emit_neon_pink", "emit_panel_warm", "emit_neon_magenta", "emit_panel_warm", "emit_neon_pink",
              "emit_panel_warm", "emit_neon_magenta"]
    hexes = {"emit_neon_pink": "pink", "emit_panel_warm": "warm", "emit_neon_magenta": "magenta"}
    cnt = len(colors)
    lights = []
    for i in range(cnt):
        t = (i + 0.5) / cnt
        j = t * n
        j0 = int(j)
        p = Vector(rope[j0]).lerp(Vector(rope[min(n, j0 + 1)]), j - j0)
        drop = 0.07 + 0.05 * ((i * 7) % 3)
        R = 0.12 if i % 2 == 0 else 0.1
        H = R * 2.3
        top = p.z - drop
        cx, cy = p.x, p.y
        # hanger wire + hook
        tube([(cx, cy, p.z), (cx, cy, top)], 0.0025, 4, "metal_dark")
        mat = colors[i]
        # cap and bottom ring (black lacquer)
        cyl(R * 0.42, 0.03, 10, at=(cx, cy, top - 0.03), mat="black")
        cyl(R * 0.36, 0.025, 10, at=(cx, cy, top - H - 0.03 - 0.025 + 0.006), mat="black")
        # ribbed paper body: ellipsoid lathe, thin dark rib bands
        prof = []
        rows = 8 if detail() else 4
        bands = []
        for k in range(rows + 1):
            v = k / rows
            ang = math.pi * (0.08 + 0.84 * v)
            rr, zz = R * math.sin(ang), -0.03 - H * v
            if detail() and 0 < k < rows and k % 2 == 0:
                prof += [(rr, zz + 0.005), (rr + 0.003, zz + 0.004), (rr + 0.003, zz - 0.004), (rr, zz - 0.005)]
                bands.append(zz)
            else:
                prof.append((rr, zz))
        prof = list(reversed(prof))
        body = lathe(prof, 12 if i % 2 == 0 else 10, at=(cx, cy, top), mat=mat, name="lantern")
        if bands:
            body.set_mat("black", where=lambda f: any(abs(f.calc_center_median().z - (top + b)) < 0.0042 for b in bands))
        # tassel
        zt = top - H - 0.055
        tube([(cx, cy, zt), (cx, cy, zt - 0.05)], 0.003, 4, "black")
        cyl(0.012, 0.07, 6, at=(cx, cy, zt - 0.12), r2=0.006, mat="paint_glossy_red")
        lights.append(light((cx, cy, top - 0.03 - H / 2), hexes[mat], 3.0, 0.6))
    return {"colliders": "none", "attach": [U((0, 0, 0)), U((L, 0, 0))], "span": L, "sag": sag, "lights": lights}


# ============================================================================================== wall conduit run
def wall_run(L=4.0):
    """Three conduits + a sagging loose cable and a glowing fibre on unistrut clips, with a pull box.
    Pivot = back-centre (wall plane, centre of the run)."""
    hx = L / 2
    xs = [-hx + 0.4 + i * (L - 0.8) / 4 for i in range(5)]
    for x in xs:
        # unistrut channel standoff
        u = box(0.042, 0.042, 0.26, at=(x, -0.021, -0.01), mat="metal_bare", bevel=0.003)
        if detail():
            inset(u, faces_where(u, lambda f: f.normal.y < -0.9), 0.011, -0.012, mat="black")
            for z in (-0.12, 0.1):
                hexbolt((x, -0.042, z), "-y", 0.007, 0.005)
    # conduits (A galvanized, B dark, both continuous; A is broken by the pull box)
    bx = 0.45
    tube([(-hx, -0.064, 0.07), (bx - 0.12, -0.064, 0.07)], 0.021, 10, "metal_bare", "conduitA")
    tube([(bx + 0.12, -0.064, 0.07), (hx, -0.064, 0.07)], 0.021, 10, "metal_bare", "conduitA")
    tube([(-hx, -0.06, 0.0), (hx, -0.06, 0.0)], 0.017, 8, "metal_dark", "conduitB")
    tube([(-hx, -0.056, -0.06), (hx, -0.056, -0.06)], 0.012, 8, "paint_glossy_dark", "conduitC")
    # couplings at the run ends and mid-span
    for x in (-hx + 0.03, 1.4, hx - 0.03):
        tube([(x - 0.03, -0.064, 0.07), (x + 0.03, -0.064, 0.07)], 0.025, 10, "metal_bare")
        tube([(x - 0.025, -0.06, 0.0), (x + 0.025, -0.06, 0.0)], 0.021, 8, "metal_dark")
    # clamps over the conduits on each unistrut
    if detail():
        for x in xs:
            for (yy, zz, r) in ((-0.064, 0.07, 0.021), (-0.06, 0.0, 0.017), (-0.056, -0.06, 0.012)):
                tube([(x, -0.042, zz + r + 0.004)] + [(x, yy - (r + 0.004) * math.sin(math.pi * k / 6), zz + (r + 0.004) * math.cos(math.pi * k / 6)) for k in range(7)] + [(x, -0.042, zz - r - 0.004)], 0.004, 4, "metal_bare", "clamp")
    # pull box
    pb = box(0.24, 0.1, 0.24, at=(bx, -0.05, 0.02), mat="metal_painted", bevel=0.008)
    box(0.25, 0.012, 0.25, at=(bx, -0.104, 0.02), mat="metal_painted", bevel=0.004)
    if detail():
        bolt_grid((bx - 0.1, bx + 0.1), (-0.08, 0.12), -0.11, r=0.006, h=0.004)
        warning_triangle((bx, -0.11, 0.035), 0.075)
        for sx in (-1, 1):
            cyl(0.026, 0.02, 8, at=(bx + sx * 0.12 + (0 if sx > 0 else -0.02), -0.064, 0.07), axis="X", mat="metal_bare", start=0)
        streak(bx - 0.06, -0.04, 0.06, 0.03, -0.11, seed=1)
        streak(bx + 0.07, -0.02, 0.07, 0.02, -0.11, seed=2)
    # loose rubber cable tied to the clamps, sagging between them
    pts = []
    for i in range(len(xs) - 1):
        seg = catenary((xs[i], -0.07, -0.1), (xs[i + 1], -0.07, -0.1), 0.05 + 0.02 * (i % 2), K.seg(10, 4))
        pts += seg if i == 0 else seg[1:]
    pts = [(-hx, -0.07, -0.1)] + pts + [(hx, -0.07, -0.1)]
    tube(pts, 0.011, 6, "rubber", "loose")
    # glowing fibre riding on conduit B
    tube([(-hx, -0.078, 0.022), (hx, -0.078, 0.022)], 0.0045, 4, "emit_strip_cyan", "fibre")
    if detail():
        for x in xs:
            ring_at((x + 0.08, -0.066, -0.075), (1, 0, 0), 0.03, 0.003, 8, 3)
    return {"colliders": [K.collider_box((0, -0.06, 0.0), (L, 0.12, 0.28))],
            "lights": [light((x, -0.09, 0.022), "cyan", 1.2, 0.15) for x in (-1.0, 1.0)]}


# ============================================================================================== pipe runs
PIPE_R = 0.085
PIPE_Y = -0.22


def _flange(c, d, r=PIPE_R, mat="metal_dark"):
    """Bolted flange pair face centred at c, axis d (unit vector along the pipe)."""
    c, d = Vector(c), Vector(d).normalized()
    tube([c - d * 0.022, c + d * 0.0], r + 0.065, 14, mat, "flange")
    tube([c - d * 0.05, c - d * 0.022], r + 0.018, 12, mat, "hub")
    if detail():
        up = Vector((0, 0, 1)) if abs(d.z) < 0.9 else Vector((1, 0, 0))
        a = d.cross(up).normalized()
        b = d.cross(a).normalized()
        for k in range(8):
            ang = (k + 0.5) * math.tau / 8
            p = c + (a * math.cos(ang) + b * math.sin(ang)) * (r + 0.042)
            tube([p - d * 0.03, p + d * 0.012], 0.008, 6, "metal_bare", "bolt")


def _pipe_bracket(x, z, horizontal=True, r=PIPE_R):
    """Cantilever bracket from the wall carrying the pipe at (x, PIPE_Y, z)."""
    if horizontal:
        zb = z - r - 0.03
        wall_plate(x, zb - 0.03, 0.12, 0.2)
        box(0.06, abs(PIPE_Y) + 0.1, 0.05, at=(x, (PIPE_Y - 0.1) / 2 - 0.006, zb), mat="metal_dark", bevel=0.004)
        beam((x, -0.012, zb - 0.12), (x, PIPE_Y - 0.02, zb - 0.02), 0.035, 0.02, mat="metal_dark", up=(1, 0, 0))
        if detail():
            ub = [(x, PIPE_Y + (r + 0.008) * math.cos(math.pi * k / 8), z + (r + 0.008) * math.sin(math.pi * k / 8)) for k in range(9)]
            tube([(x, PIPE_Y + r + 0.008, zb)] + ub + [(x, PIPE_Y - r - 0.008, zb)], 0.007, 6, "metal_bare", "ubolt")
            for s in (-1, 1):
                cyl(0.012, 0.012, 6, at=(x, PIPE_Y + s * (r + 0.008), zb - 0.037), mat="metal_bare", start=0)
            box(0.07, 0.006, 0.04, at=(x, PIPE_Y + r + 0.06, zb + 0.006), mat="rubber")
    else:
        # vertical pipe: side clamp bracket at height z
        wall_plate(x, z, 0.2, 0.1)
        box(0.05, abs(PIPE_Y) - 0.02, 0.05, at=(x - r - 0.04, (PIPE_Y - 0.012) / 2 - 0.006, z), mat="metal_dark", bevel=0.004)
        if detail():
            ring_at((x, PIPE_Y, z), (0, 0, 1), r + 0.008, 0.008, 12, 4, "metal_bare")
            box(0.05, 0.02, 0.04, at=(x - r - 0.03, PIPE_Y, z), mat="metal_bare")


def _pipe_marks(x0, x1, z, y=PIPE_Y):
    """Yellow ID band + flow arrow on a horizontal pipe."""
    xm = (x0 + x1) / 2
    tube([(xm - 0.06, y, z), (xm + 0.06, y, z)], PIPE_R + 0.002, 14, "metal_painted_yellow", "band")
    if detail():
        arr = [(-0.07, -0.012), (0.02, -0.012), (0.02, -0.03), (0.07, 0.0), (0.02, 0.03), (0.02, 0.012), (-0.07, 0.012)]
        a = extrude([(xm + 0.18 + px, z + pz) for px, pz in arr], 0.004, plane="XZ", mat="metal_painted_white")
        a.move(0, y - PIPE_R - 0.0015, 0)


def pipe_run_straight(L=2.0):
    hx = L / 2
    tube([(-hx + 0.05, PIPE_Y, 0), (hx - 0.05, PIPE_Y, 0)], PIPE_R, 16, "paint_glossy_dark", "pipe")
    _flange((-hx + 0.022, PIPE_Y, 0), (-1, 0, 0))
    _flange((hx - 0.022, PIPE_Y, 0), (1, 0, 0))
    for x in (-hx + 0.45, hx - 0.45):
        _pipe_bracket(x, 0)
    _pipe_marks(-0.2, 0.2, 0)
    # instrument tap: nozzle, needle valve and dial gauge on top of the pipe
    if detail():
        cyl(0.022, 0.06, 10, at=(0.25, PIPE_Y, PIPE_R - 0.01), mat="metal_dark")
        cyl(0.012, 0.07, 8, at=(0.25, PIPE_Y, PIPE_R + 0.05), mat="chrome_scratched")
        box(0.05, 0.012, 0.012, at=(0.25, PIPE_Y, PIPE_R + 0.09), mat="metal_painted_red", bevel=0.003)
        g = cyl(0.045, 0.03, 16, at=(0.25, PIPE_Y + 0.0, PIPE_R + 0.165), axis="Y", mat="metal_dark")
        g.move(0, -0.015, 0)
        cyl(0.04, 0.003, 16, at=(0.25, PIPE_Y - 0.018, PIPE_R + 0.165), axis="Y", mat="metal_painted_white")
        n = box(0.003, 0.002, 0.03, at=(0.25, PIPE_Y - 0.0185, PIPE_R + 0.17), mat="black")
        n.rot_about((0.25, PIPE_Y, PIPE_R + 0.165), y=35)
        box(0.012, 0.02, 0.02, at=(0.25, PIPE_Y, PIPE_R + 0.12), mat="metal_dark")
    return {"colliders": [K.collider_box((0, PIPE_Y, 0), (L, 0.32, 0.32))],
            "ports": [{"position": U((-hx, PIPE_Y, 0)), "dir": [1, 0, 0]}, {"position": U((hx, PIPE_Y, 0)), "dir": [-1, 0, 0]}]}


def pipe_run_elbow(leg=0.6, R=0.3):
    """Horizontal leg from the -X port bending up to a vertical +Z port. Pivot: wall plane at the intersection of
    the two leg axes."""
    x0 = -leg
    tube([(x0 + 0.05, PIPE_Y, 0), (-R, PIPE_Y, 0)], PIPE_R, 16, "paint_glossy_dark", "pipe")
    arc = arc_pts((-R, PIPE_Y, R), R, -90, 0, K.seg(10, 4))
    tube(arc, PIPE_R, 16, "paint_glossy_dark", "bend")
    tube([(0, PIPE_Y, R), (0, PIPE_Y, leg - 0.05)], PIPE_R, 16, "paint_glossy_dark", "pipe")
    # weld beads at the bend ends
    if detail():
        ring_at((-R, PIPE_Y, 0), (1, 0, 0), PIPE_R + 0.002, 0.005, 16, 4, "metal_dark")
        ring_at((0, PIPE_Y, R), (0, 0, 1), PIPE_R + 0.002, 0.005, 16, 4, "metal_dark")
    _flange((x0 + 0.022, PIPE_Y, 0), (-1, 0, 0))
    _flange((0, PIPE_Y, leg - 0.022), (0, 0, 1))
    _pipe_bracket(x0 + 0.3, 0)
    _pipe_bracket(0, leg - 0.2, horizontal=False)
    return {"colliders": [K.collider_box((x0 / 2, PIPE_Y, 0), (leg, 0.32, 0.2)), K.collider_box((0, PIPE_Y, leg / 2), (0.2, 0.32, leg))],
            "ports": [{"position": U((x0, PIPE_Y, 0)), "dir": [1, 0, 0]}, {"position": U((0, PIPE_Y, leg)), "dir": [0, 1, 0]}]}


def pipe_run_tee(leg=0.6):
    """Through-run along X with a vertical branch up. Pivot: wall plane at the branch / run axis intersection."""
    tube([(-leg + 0.05, PIPE_Y, 0), (leg - 0.05, PIPE_Y, 0)], PIPE_R, 16, "paint_glossy_dark", "pipe")
    tube([(0, PIPE_Y, PIPE_R * 0.5), (0, PIPE_Y, leg - 0.05)], PIPE_R, 16, "paint_glossy_dark", "branch")
    # reinforcing saddle + weld at the branch
    tube([(0, PIPE_Y, PIPE_R * 0.6), (0, PIPE_Y, PIPE_R + 0.05)], PIPE_R + 0.016, 16, "metal_dark", "saddle")
    _flange((-leg + 0.022, PIPE_Y, 0), (-1, 0, 0))
    _flange((leg - 0.022, PIPE_Y, 0), (1, 0, 0))
    _flange((0, PIPE_Y, leg - 0.022), (0, 0, 1))
    _pipe_bracket(-leg + 0.28, 0)
    _pipe_bracket(leg - 0.28, 0)
    if detail():
        # drain valve under the tee
        cyl(0.02, 0.05, 8, at=(0, PIPE_Y, -PIPE_R - 0.045), mat="metal_dark")
        cyl(0.03, 0.03, 8, at=(0, PIPE_Y, -PIPE_R - 0.075), mat="chrome_scratched")
        t = torus(0.035, 0.005, n_major=10, n_minor=4, mat="metal_painted_red")
        t.move(0, PIPE_Y, -PIPE_R - 0.08)
    return {"colliders": [K.collider_box((0, PIPE_Y, 0), (2 * leg, 0.32, 0.2)), K.collider_box((0, PIPE_Y, leg / 2), (0.2, 0.32, leg))],
            "ports": [{"position": U((-leg, PIPE_Y, 0)), "dir": [1, 0, 0]}, {"position": U((leg, PIPE_Y, 0)), "dir": [-1, 0, 0]},
                      {"position": U((0, PIPE_Y, leg)), "dir": [0, 1, 0]}]}


# ============================================================================================== wall vents
def wall_vent_a():
    """Louvred exhaust with a rain hood. Pivot back-centre."""
    W, H, D = 0.62, 0.46, 0.17
    wall_plate(0, 0, W + 0.1, H + 0.1, t=0.014, mat="metal_dark", bolts=False)
    h = box(W, D, H, at=(0, -0.014 - D / 2, 0), mat="metal_painted", bevel=0.01, bseg=2)
    front = faces_where(h, lambda f: f.normal.y < -0.9)
    inset(h, front, 0.035, -0.06, mat="black")
    yf = -0.014 - D
    if detail():
        box(W - 0.08, 0.004, H - 0.08, at=(0, yf + 0.05, 0), mat="grating")
    nl = 7
    for i in range(nl):
        z = -H / 2 + 0.07 + i * (H - 0.12) / (nl - 1)
        l = box(W - 0.075, 0.075, 0.008, mat="metal_painted", bevel=0.002)
        l.rot(x=-38).move(0, yf + 0.03, z)
    # rain hood
    hood = box(W + 0.08, 0.2, 0.014, mat="metal_painted", bevel=0.003)
    hood.rot(x=-22).move(0, -0.014 - 0.1, H / 2 + 0.05)
    for sx in (-1, 1):
        cheek = extrude([(-0.014, H / 2 - 0.02), (-0.2, H / 2 + 0.02), (-0.014, H / 2 + 0.1)], 0.008, plane="YZ", mat="metal_painted")
        cheek.move(sx * (W / 2 + 0.034), 0, 0)
    if detail():
        for sx in (-1, 1):
            for z in (-H / 2 + 0.05, 0, H / 2 - 0.05):
                hexbolt((sx * (W / 2 + 0.03), -0.014, z), "-y", 0.007, 0.005)
            for y in (-0.05, -0.12):
                cyl(0.005, 0.003, 6, at=(sx * W / 2, y, -0.15), axis="X", mat="metal_bare")
        streak(-0.06, 0.1, 0.3, 0.05, W / 2, facing="+x", seed=11, mat="black")
        streak(-0.12, -0.05, 0.17, 0.04, -W / 2, facing="-x", seed=12)
    return {"colliders": [K.collider_box((0, -0.1, 0), (W + 0.1, 0.2, H + 0.1))]}


def wall_vent_b():
    """Round fan exhaust in a square housing with a slanted rain shade. Pivot back-centre."""
    W, D = 0.56, 0.2
    wall_plate(0, 0, W + 0.08, W + 0.08, t=0.012, bolts=True)
    h = box(W, D, W, at=(0, -0.012 - D / 2, 0), mat="paint_glossy_dark", bevel=0.012, bseg=2)
    yf = -0.012 - D
    R = 0.22
    shroud = lathe([(R + 0.03, 0.0), (R + 0.03, 0.02), (R + 0.005, 0.03), (R, 0.0)], 24, mat="metal_dark", close_bottom=False, close_top=False)
    shroud.rot(x=90).move(0, yf, 0)
    cyl(R, 0.004, 24, at=(0, yf + 0.11, 0), axis="Y", mat="black")
    # fan blades + hub
    hub = cyl(0.05, 0.05, 12, at=(0, yf + 0.04, 0), axis="Y", mat="metal_dark")
    for k in range(5):
        bl = box(0.15, 0.008, 0.07, at=(0.12, 0, 0), mat="metal_bare", bevel=0.002)
        bl.rot(x=28).rot(y=k * 72).move(0, yf + 0.065, 0)
    # grille: rings + spokes
    for rr in (0.06, 0.11, 0.16, 0.205):
        t = torus(rr, 0.0035, n_major=K.seg(24, 12), n_minor=4, mat="metal_bare")
        t.rot(x=90).move(0, yf - 0.008, 0)
    for k in range(4):
        sp = box(R * 2, 0.008, 0.008, mat="metal_bare")
        sp.rot(y=45 + k * 45).move(0, yf - 0.008, 0)
    # slanted rain shade on top
    s = box(W + 0.06, 0.24, 0.012, mat="paint_glossy_dark", bevel=0.003)
    s.rot(x=-18).move(0, -0.012 - 0.12, W / 2 + 0.045)
    if detail():
        for sx in (-1, 1):
            for sz in (-1, 1):
                hexbolt((sx * (W / 2 - 0.035), yf, sz * (W / 2 - 0.035)), "-y", 0.008, 0.005)
        led((W / 2 - 0.06, yf, -W / 2 + 0.05), "emit_amber", 0.007)
        led((W / 2 - 0.09, yf, -W / 2 + 0.05), "emit_green", 0.007)
        # power conduit from the side into the wall
        conduit([(W / 2, -0.11, -0.12), (W / 2 + 0.12, -0.11, -0.12), (W / 2 + 0.12, -0.11, -0.4), (W / 2 + 0.12, 0.0, -0.4)], 0.014, "metal_bare", 0.05)
        streak(-0.12, -R + 0.02, 0.05, 0.05, yf, seed=21, mat="black")
        streak(0.1, -R + 0.01, 0.045, 0.04, yf, seed=22)
        streak(-0.08, 0.15, 0.3, 0.05, W / 2, facing="+x", seed=23, mat="black")
    return {"colliders": [K.collider_box((0, -0.11, 0), (W + 0.08, 0.22, W + 0.08))]}


# ============================================================================================== electrical
def _door_panel(x, z, w, h, y, mat="metal_painted", t=0.012):
    d = box(w, t, h, at=(x, y - t / 2, z), mat=mat, bevel=0.004)
    return d


def electrical_box_a():
    """Small wall junction box with conduit up/down into the wall, status LEDs. Pivot back-centre."""
    W, D, H = 0.4, 0.16, 0.52
    box(W, D, H, at=(0, -D / 2, 0), mat="metal_painted", bevel=0.01)
    yf = -D
    _door_panel(0, 0, W - 0.03, H - 0.03, yf)
    yd = yf - 0.012
    if detail():
        for z in (-0.17, 0.17):  # hinges (left)
            cyl(0.011, 0.07, 8, at=(-W / 2 - 0.004, yf - 0.006, z - 0.035), mat="metal_dark")
        # quarter-turn latch + padlock hasp
        cyl(0.02, 0.012, 12, at=(W / 2 - 0.05, yd - 0.012, 0.0), axis="Y", mat="metal_dark")
        box(0.012, 0.012, 0.05, at=(W / 2 - 0.05, yd - 0.016, 0.0), mat="chrome_scratched", bevel=0.002)
        for k, m in enumerate(("emit_green", "emit_amber", "emit_red")):
            led((W / 2 - 0.05 - k * 0.028, yd, H / 2 - 0.05), m, 0.006)
        warning_triangle((-0.05, yd, 0.1), 0.09)
        box(0.12, 0.002, 0.05, at=(-0.05, yd - 0.001, -0.02), mat="metal_painted_white")
        for i in range(4):
            box(0.09, 0.0025, 0.004, at=(-0.06, yd - 0.002, -0.004 - i * 0.01), mat="black")
        # side vent slots
        for sx in (-1, 1):
            for i in range(4):
                box(0.004, 0.08, 0.008, at=(sx * W / 2, -D / 2, -H / 2 + 0.06 + i * 0.022), mat="black")
        streak(-W / 2 + 0.03, -0.2, 0.05, 0.02, yd, seed=31)
        streak(W / 2 - 0.05, -0.03, 0.2, 0.035, yd, seed=32, mat="black")
        streak(-0.08, 0.2, 0.3, 0.05, W / 2, facing="+x", seed=33, mat="black")
    # conduits: two down, one up, all elbowing into the wall
    for x in (-0.1, 0.08):
        conduit([(x, -0.07, -H / 2), (x, -0.07, -H / 2 - 0.35 - (0.08 if x > 0 else 0)), (x, 0.0, -H / 2 - 0.35 - (0.08 if x > 0 else 0))], 0.016, "metal_bare", 0.06)
        cyl(0.024, 0.02, 6, at=(x, -0.07, -H / 2 - 0.02), mat="metal_bare", start=0)
    conduit([(0.0, -0.07, H / 2), (0.0, -0.07, H / 2 + 0.45), (0.0, 0.0, H / 2 + 0.45)], 0.02, "metal_bare", 0.06)
    cyl(0.03, 0.02, 6, at=(0.0, -0.07, H / 2), mat="metal_bare", start=0)
    for z in (-H / 2 - 0.2,):
        strap((-0.1, -0.07, z), (0, 0, 1), 0.016)
    strap((0.0, -0.07, H / 2 + 0.25), (0, 0, 1), 0.02)
    return {"colliders": [K.collider_box((0, -D / 2 - 0.006, 0), (W, D + 0.012, H))],
            "lights": [light((W / 2 - 0.078, yd - 0.01, H / 2 - 0.05), "green", 0.6, 0.05)]}


def electrical_box_b():
    """Horizontal meter / breaker box with a meter window, side louvres, a flexible conduit and a messy bundle of
    tapped cables. Pivot back-centre."""
    W, D, H = 0.72, 0.2, 0.42
    b = box(W, D, H, at=(0, -D / 2, 0), mat="metal_painted_green", bevel=0.012, bseg=2)
    yf = -D
    # two doors
    _door_panel(-W / 4 + 0.004, -0.01, W / 2 - 0.022, H - 0.06, yf, "metal_painted_green")
    _door_panel(W / 4 - 0.004, -0.01, W / 2 - 0.022, H - 0.06, yf, "metal_painted_green")
    yd = yf - 0.012
    # meter window on the left door: dark glass with a glowing readout
    box(0.2, 0.01, 0.13, at=(-W / 4, yd - 0.003, 0.05), mat="metal_dark", bevel=0.003)
    box(0.17, 0.006, 0.1, at=(-W / 4, yd - 0.007, 0.05), mat="glass_dark")
    box(0.08, 0.004, 0.025, at=(-W / 4 - 0.02, yd - 0.0095, 0.07), mat="emit_cyan")
    if detail():
        cyl(0.025, 0.003, 12, at=(-W / 4 + 0.05, yd - 0.0105, 0.035), axis="Y", mat="metal_painted_white")
        for k, m in enumerate(("emit_green", "emit_green", "emit_red")):
            led((W / 4 + 0.08 - k * 0.03, yd, H / 2 - 0.07), m, 0.006)
        for sx in (-0.015, 0.015):
            box(0.014, 0.02, 0.06, at=(sx, yd - 0.01, -0.02), mat="chrome_scratched", bevel=0.003)
        # padlock
        t = torus(0.018, 0.004, arc=180, n_major=8, n_minor=4, mat="chrome_scratched", start=0)
        t.rot(x=90).move(0.0, yd - 0.03, -0.06)
        box(0.035, 0.016, 0.04, at=(0.0, yd - 0.03, -0.082), mat="metal_painted_yellow", bevel=0.004)
        warning_triangle((W / 4, yd, 0.03), 0.1)
        for sx in (-1, 1):  # side louvres
            for i in range(5):
                l = box(0.004, 0.12, 0.012, at=(sx * (W / 2 + 0.002), -D / 2, -0.12 + i * 0.05), mat="black")
        streak(-W / 4, -0.03, 0.15, 0.06, yd, seed=41)
        streak(0.1, -0.08, 0.1, 0.05, yd, seed=42, mat="black")
    # flexible conduit loop from the right side into the wall below
    pts = [(W / 2, -0.1, -0.08), (W / 2 + 0.12, -0.12, -0.12), (W / 2 + 0.16, -0.1, -0.32), (W / 2 + 0.08, -0.05, -0.48), (W / 2 + 0.02, 0.0, -0.52)]
    tube(bend_path(pts, 0.08, 4 if detail() else 2), 0.022, 8, "rubber", "flex")
    if detail():
        for i in range(1, 9):
            p = bend_path(pts, 0.08, 4)
            j = int(i * (len(p) - 1) / 9)
            a, c = Vector(p[j]), Vector(p[j + 1])
            ring_at(a, c - a, 0.023, 0.003, 8, 3, "black")
    cyl(0.03, 0.025, 6, at=(W / 2, -0.1, -0.08), axis="X", mat="metal_bare", start=0)
    # tapped cables out of the top, bending up and over into the wall
    for k, (x, r, m) in enumerate(((-0.2, 0.012, "rubber"), (-0.16, 0.009, "plastic_dark"), (-0.12, 0.014, "rubber"), (0.12, 0.01, "rubber"))):
        h2 = 0.35 + 0.06 * k
        pts = [(x, -0.09, H / 2), (x + 0.01 * k, -0.1, H / 2 + h2 * 0.6), (x + 0.03 * k - 0.02, -0.06, H / 2 + h2), (x + 0.03 * k - 0.02, 0.0, H / 2 + h2 + 0.05)]
        tube(bend_path(pts, 0.06, 3 if detail() else 1), r, 6, m, "tap")
        cyl(r + 0.008, 0.02, 6, at=(x, -0.09, H / 2), mat="metal_dark", start=0)
    if detail():
        ring_at((-0.17, -0.1, H / 2 + 0.16), (0, 0, 1), 0.05, 0.004, 10, 3)
    return {"colliders": [K.collider_box((0, -D / 2 - 0.006, 0), (W, D + 0.012, H))],
            "lights": [light((-W / 4 - 0.02, yd - 0.02, 0.07), "cyan", 0.8, 0.1)]}


def electrical_cabinet_tall():
    """Floor-standing street distribution cabinet against a wall: double doors, louvres, rain hood, hazard plinth,
    conduits up into the wall, LED status strip. Pivot wall-base."""
    W, D, H = 0.9, 0.42, 1.85
    pl = 0.08
    box(W - 0.04, D - 0.04, pl, at=(0, -D / 2, 0), mat="concrete_dark", base=True, bevel=0.01)
    body = box(W, D, H - pl, at=(0, -D / 2, pl), mat="metal_painted", base=True, bevel=0.014, bseg=2)
    yf = -D
    # rain hood
    hood = box(W + 0.06, D + 0.05, 0.05, at=(0, -D / 2 - 0.025, H), mat="metal_dark", base=True, bevel=0.01)
    hood.rot_about((0, 0, H), x=4)
    # doors
    dw = W / 2 - 0.025
    for sx in (-1, 1):
        x = sx * (W / 4 - 0.002)
        _door_panel(x, pl + (H - pl) / 2, dw, H - pl - 0.07, yf, "metal_painted")
        yd = yf - 0.012
        # louvre panel low on each door
        lv = box(dw - 0.1, 0.006, 0.3, at=(x, yd - 0.003, pl + 0.28), mat="black")
        for i in range(8):
            l = box(dw - 0.11, 0.03, 0.006, mat="metal_painted")
            l.rot(x=-35).move(x, yd - 0.01, pl + 0.15 + i * 0.037)
        # upper louvres
        for i in range(5):
            l = box(dw - 0.18, 0.025, 0.006, mat="metal_painted")
            l.rot(x=-35).move(x, yd - 0.008, H - 0.22 + i * 0.03)
        box(dw - 0.17, 0.004, 0.15, at=(x, yd - 0.002, H - 0.16), mat="black")
        # handles (vertical bars) near the centre gap
        hx = x - sx * (dw / 2 - 0.06)
        if detail():
            for z in (1.0, 1.25):
                box(0.02, 0.035, 0.02, at=(hx, yd - 0.017, z), mat="metal_dark")
        box(0.022, 0.018, 0.3, at=(hx, yd - 0.04, 1.125), mat="chrome_scratched", bevel=0.005)
        # hinges on the outer edges
        if detail():
            for z in (0.35, 1.0, 1.6):
                cyl(0.013, 0.09, 8, at=(sx * (W / 2 + 0.006), yf - 0.006, z), mat="metal_dark")
    yd = yf - 0.012
    # LED status: vertical cyan strip in the door gap + indicator cluster + tiny status display
    box(0.008, 0.008, H - pl - 0.5, at=(0, yd + 0.0, pl + (H - pl) / 2 + 0.05), mat="emit_strip_cyan")
    for k, m in enumerate(("emit_green", "emit_green", "emit_amber", "emit_red")):
        led((W / 4 + 0.07 - k * 0.03, yd, 1.48), m, 0.007)
    box(0.13, 0.008, 0.06, at=(W / 4 + 0.025, yd - 0.004, 1.4), mat="metal_dark", bevel=0.002)
    box(0.11, 0.004, 0.044, at=(W / 4 + 0.025, yd - 0.009, 1.4), mat="emit_cyan")
    if detail():
        warning_triangle((-W / 4, yd, 1.45), 0.12)
        box(0.18, 0.002, 0.07, at=(-W / 4, yd - 0.001, 1.33), mat="metal_painted_white")
        for i in range(3):
            box(0.15, 0.0025, 0.006, at=(-W / 4 - 0.01, yd - 0.002, 1.355 - i * 0.017), mat="black")
        # padlock on the hasp
        t = torus(0.02, 0.0045, arc=180, n_major=8, n_minor=4, mat="chrome_scratched", start=0)
        t.rot(x=90).move(0.0, yd - 0.035, 0.92)
        box(0.04, 0.018, 0.045, at=(0.0, yd - 0.035, 0.895), mat="metal_painted_yellow", bevel=0.004)
        # side louvres
        for sx in (-1, 1):
            for i in range(6):
                box(0.004, 0.25, 0.012, at=(sx * (W / 2 + 0.001), -D / 2, 0.25 + i * 0.045), mat="black")
        # grime
        for k, (x, z, L_, w) in enumerate(((-0.3, 1.0, 0.5, 0.06), (0.25, 0.7, 0.4, 0.05), (-0.1, 1.75, 0.6, 0.04), (0.35, 1.6, 0.3, 0.04))):
            streak(x, z, L_, w, yd, seed=50 + k, mat="black" if k % 2 else "metal_rusted")
        # earth cable to the ground
        tube(bend_path([(W / 2 - 0.05, yf - 0.002, pl + 0.05), (W / 2 + 0.02, yf - 0.06, pl), (W / 2 + 0.1, yf - 0.1, 0.012)], 0.03, 3), 0.007, 6, "metal_painted_green")
    # hazard plinth band
    hazard_stripes(-W / 2 + 0.02, W / 2 - 0.02, 0.005, pl - 0.008, -D + 0.018, n=8)
    # conduits up out of the hood into the wall
    for k, (x, r) in enumerate(((-0.25, 0.026), (-0.12, 0.02), (0.18, 0.032))):
        top = H + 0.45 + 0.08 * k
        conduit([(x, -D / 2 + 0.05, H + 0.05), (x, -D / 2 + 0.05, top), (x, 0.0, top)], r, "metal_bare", 0.1)
        if detail():
            strap((x, -D / 2 + 0.05, top - 0.2), (0, 0, 1), r)
    return {"colliders": [K.collider_box((0, -D / 2, H / 2), (W, D, H))],
            "lights": [light((0, yd - 0.05, 1.1), "cyan", 1.5, 0.3)]}


def fire_extinguisher_cabinet():
    """Red wall cabinet with a glass door and an extinguisher inside, glowing pictogram sign above. Pivot back-centre
    (centre of the cabinet)."""
    W, D, H = 0.36, 0.2, 0.78
    cab = box(W, D, H, at=(0, -D / 2, 0), mat="metal_painted_red", bevel=0.01)
    yf = -D
    inset(cab, faces_where(cab, lambda f: f.normal.y < -0.9), 0.03, -0.16, mat="metal_painted_white")
    # extinguisher
    ex = (0.0, -0.09, -H / 2 + 0.05)
    body = lathe([(0.001, 0.0), (0.075, 0.0), (0.08, 0.02), (0.08, 0.45), (0.07, 0.5), (0.04, 0.53), (0.022, 0.55), (0.001, 0.555)], 16, at=ex, mat="paint_glossy_red")
    cyl(0.023, 0.05, 8, at=(ex[0], ex[1], ex[2] + 0.55), mat="chrome_scratched")
    box(0.09, 0.02, 0.012, at=(ex[0] + 0.02, ex[1], ex[2] + 0.62), mat="black", bevel=0.003).rot_about((ex[0], ex[1], ex[2] + 0.62), y=-12)
    box(0.08, 0.02, 0.01, at=(ex[0] + 0.02, ex[1], ex[2] + 0.59), mat="black", bevel=0.003)
    if detail():
        cyl(0.018, 0.008, 12, at=(ex[0] - 0.035, ex[1] - 0.01, ex[2] + 0.58), axis="Y", mat="metal_painted_white").move(0, -0.006, 0)
        tube(bend_path([(ex[0] + 0.03, ex[1], ex[2] + 0.57), (ex[0] + 0.1, ex[1] - 0.02, ex[2] + 0.5), (ex[0] + 0.1, ex[1] - 0.03, ex[2] + 0.2), (ex[0] + 0.07, ex[1] - 0.06, ex[2] + 0.12)], 0.04, 3), 0.008, 6, "black")
        box(0.1, 0.002, 0.14, at=(ex[0], ex[1] - 0.081, ex[2] + 0.25), mat="metal_painted_white")
        for i in range(4):
            box(0.07, 0.0025, 0.006, at=(ex[0], ex[1] - 0.083, ex[2] + 0.29 - i * 0.022), mat="black")
        box(0.04, 0.0025, 0.03, at=(ex[0], ex[1] - 0.083, ex[2] + 0.2), mat="emit_red")
    # glass door in a frame + handle
    for sx in (-1, 1):
        box(0.025, 0.018, H - 0.01, at=(sx * (W / 2 - 0.0125), yf - 0.009, 0), mat="metal_painted_red", bevel=0.003)
    for sz in (-1, 1):
        box(W - 0.05, 0.018, 0.025, at=(0, yf - 0.009, sz * (H / 2 - 0.0125)), mat="metal_painted_red", bevel=0.003)
    box(W - 0.05, 0.004, H - 0.05, at=(0, yf - 0.01, 0), mat="glass")
    box(0.02, 0.025, 0.12, at=(W / 2 - 0.035, yf - 0.03, 0.0), mat="chrome_scratched", bevel=0.004)
    # glowing pictogram sign above: red light box with an abstract flame + arrow glyph
    sy = H / 2 + 0.16
    box(0.24, 0.05, 0.2, at=(0, -0.025, sy), mat="metal_dark", bevel=0.006)
    box(0.21, 0.006, 0.17, at=(0, -0.053, sy), mat="emit_panel_white")
    flame = [(0.0, -0.06), (0.045, -0.035), (0.05, 0.01), (0.02, 0.06), (0.018, 0.02), (0.0, 0.035), (-0.02, 0.0), (-0.045, 0.02), (-0.05, -0.03)]
    f = extrude([(x * 1.2 - 0.03, sy + z) for x, z in flame], 0.004, plane="XZ", mat="emit_red")
    f.move(0, -0.058, 0)
    arr = [(0.03, -0.012), (0.07, -0.012), (0.07, -0.03), (0.1, 0.0), (0.07, 0.03), (0.07, 0.012), (0.03, 0.012)]
    a = extrude([(x, sy + z - 0.03) for x, z in arr], 0.004, plane="XZ", mat="emit_red")
    a.move(0, -0.058, 0)
    if detail():
        streak(-0.06, 0.25, 0.4, 0.05, W / 2, facing="+x", seed=61, mat="black")
        bolt_grid((-0.09, 0.09), (sy - 0.07, sy + 0.07), -0.05, r=0.005, h=0.003)
    return {"colliders": [K.collider_box((0, -D / 2, 0), (W, D, H))], "light": light((0, -0.12, sy), "red", 1.5, 0.3)}


# ============================================================================================== wall lamps
def wall_lamp_cage():
    """Jelly-jar bulkhead on a short arm, wire cage, warm bulb. Pivot back-centre (wall plate centre)."""
    wall_plate(0, 0, 0.12, 0.18, t=0.014, bolts=True)
    box(0.05, 0.16, 0.05, at=(0, -0.094, 0.0), mat="metal_dark", bevel=0.006)
    beam((0, -0.014, -0.07), (0, -0.15, -0.01), 0.03, 0.012, mat="metal_dark", up=(1, 0, 0))
    jx, jy = 0.0, -0.17
    # fitter cap
    lathe([(0.03, 0.0), (0.06, -0.01), (0.065, -0.05), (0.06, -0.06), (0.001, -0.061)], 16, at=(jx, jy, 0.02), mat="metal_dark")
    # glass jar (transparent) + bulb
    lathe([(0.055, 0.0), (0.06, -0.03), (0.062, -0.12), (0.05, -0.16), (0.001, -0.17)], 16, at=(jx, jy, -0.04), mat="glass", close_top=False)
    lathe([(0.012, 0.0), (0.03, -0.03), (0.035, -0.06), (0.025, -0.085), (0.001, -0.09)], 12, at=(jx, jy, -0.06), mat="emit_panel_warm")
    # wire cage
    for k in range(4):
        ang = math.radians(45 + k * 90)
        ca, sa = math.cos(ang), math.sin(ang)
        pts = [(jx + ca * 0.068, jy + sa * 0.068, -0.045), (jx + ca * 0.07, jy + sa * 0.07, -0.16), (jx + ca * 0.035, jy + sa * 0.035, -0.215), (jx, jy, -0.222)]
        tube(pts, 0.0035, 4, "metal_dark", "cage")
    for z, rr in ((-0.05, 0.068), (-0.11, 0.07), (-0.165, 0.065)):
        t = torus(rr, 0.0035, n_major=K.seg(16, 8), n_minor=4, mat="metal_dark")
        t.move(jx, jy, z)
    # conduit feeding the plate from above
    conduit([(0, -0.03, 0.09), (0, -0.03, 0.35), (0, 0.0, 0.35)], 0.012, "metal_bare", 0.04)
    if detail():
        streak(0.0, -0.035, 0.05, 0.03, -0.014, seed=71, mat="black")
    return {"colliders": [K.collider_box((0, -0.11, -0.04), (0.16, 0.22, 0.28))],
            "light": light((jx, jy, -0.11), "warm", 6.0, 1.2)}


def wall_lamp_led():
    """Slim angled LED wall-pack: glossy black wedge, white emitter underneath, cyan accent line. Pivot back-centre."""
    W = 0.46
    wall_plate(0, 0, 0.2, 0.14, t=0.012, bolts=True)
    poly = [(0.0, -0.06), (-0.16, -0.045), (-0.17, -0.02), (-0.15, 0.05), (0.0, 0.07)]
    body = extrude([(y, z) for y, z in poly], W, plane="YZ", mat="paint_glossy_dark", bevel=0.006)
    body.move(0, -0.012, 0)
    # emitter panel on the underside (sloped face)
    em = extrude([(-0.005, -0.058), (-0.15, -0.046), (-0.15, -0.049), (-0.005, -0.061)], W - 0.06, plane="YZ", mat="emit_panel_white")
    em.move(0, -0.012, -0.003)
    # cyan accent line along the front lip
    box(W - 0.04, 0.006, 0.006, at=(0, -0.012 - 0.171, -0.02), mat="emit_strip_cyan")
    if detail():
        for i in range(7):  # heatsink fins on top
            x = -W / 2 + 0.06 + i * (W - 0.12) / 6
            f = extrude([(-0.01, 0.068), (-0.13, 0.052), (-0.13, 0.075), (-0.01, 0.09)], 0.006, plane="YZ", mat="metal_dark")
            f.move(x, -0.012, 0)
        for sx in (-1, 1):
            cyl(0.006, 0.004, 6, at=(sx * (W / 2 + 0.001), -0.1, 0.0), axis="X", mat="metal_bare", start=0)
    return {"colliders": [K.collider_box((0, -0.095, 0.005), (W, 0.17, 0.14))],
            "light": light((0, -0.15, -0.12), "white", 7.0, 1.4)}


# ============================================================================================== registry
_W = "back-centre"
ASSETS = {
    "Cable_Bundle_Sag_4m": dict(fn=cable_bundle, kw={"L": 4.0, "sag": 0.35}, cat="dressing", zones=["plaza", "metro", "rooftops"], pivot="left-attach",
                                notes="Bundle of 5 power/data cables on a steel messenger wire, slung across a 4.0 m gap with 0.35 m sag; cable ties, service loop, ID tag. "
                                      "Pivot = left attach point on the left wall plane; the span runs toward Unity -X, far attach point at 'attach'[1] = (-4, 0, 0). "
                                      "Each end has a 0.17 m wall plate + standoff arm (walls are perpendicular to the span). Footprint 4.0 x 0.6 x 0.2. No collider."),
    "Cable_Bundle_Sag_8m": dict(fn=cable_bundle, kw={"L": 8.0, "sag": 0.8, "seed": 7}, cat="dressing", zones=["plaza", "metro", "rooftops"], pivot="left-attach",
                                notes="8.0 m span, 0.8 m sag version of Cable_Bundle_Sag_4m (6 cables, splice sleeve, drooping loop). Pivot = left attach point; far "
                                      "attach point at 'attach'[1] = (-8, 0, 0). Scale X to fit other gaps (keep it within ~0.8-1.25). No collider."),
    "Lantern_String_4m": dict(fn=lantern_string, cat="dressing", zones=["plaza", "metro"], pivot="left-attach",
                              notes="Rope of 7 ribbed paper lanterns (emit_neon_pink / emit_panel_warm / emit_neon_magenta) with black lacquer caps and red "
                                    "tassels, slung across a 4 m gap (0.32 m sag). Pivot = left attach point; far attach at 'attach'[1]. 'lights' lists every "
                                    "lantern centre (use 2-3 real lights, the rest emissive only). No collider."),
    "Cable_Wall_Run_4m": dict(fn=wall_run, cat="dressing", zones=["plaza", "metro", "facility", "rooftops"], pivot=_W,
                              notes="4.0 m wall conduit run: galvanized + dark conduits on unistrut clips, pull box with hazard label, loose rubber cable "
                                    "tied between clips, glowing cyan fibre (emit_strip_cyan). Pivot back-centre (wall plane, run centre, conduit height); "
                                    "sticks 0.12 m out (Unity +Z). Chain end-to-end every 4 m."),
    "Pipe_Run_Straight_2m": dict(fn=pipe_run_straight, cat="dressing", zones=["metro", "facility", "plaza", "vault"], pivot="wall-axis",
                                 notes="2 m flanged pipe spool (r 0.085, glossy dark paint) 0.22 m off the wall on two cantilever brackets with U-bolts; "
                                       "yellow ID band, flow arrow, gauge tap. Pivot on the wall plane at pipe-axis height, centre of the run. 'ports' "
                                       "lists the flange faces (Unity +-1 m on X) for chaining with Pipe_Run_Elbow / Pipe_Run_Tee."),
    "Pipe_Run_Elbow": dict(fn=pipe_run_elbow, cat="dressing", zones=["metro", "facility", "plaza", "vault"], pivot="wall-axis",
                           notes="90 deg long-radius elbow (R 0.3): horizontal leg to a flange at Unity x=+0.6, bending up to a flange at y=+0.6. "
                                 "Pivot on the wall plane at the intersection of the leg axes; ports in 'ports'. Mirror X for the other hand."),
    "Pipe_Run_Tee": dict(fn=pipe_run_tee, cat="dressing", zones=["metro", "facility", "plaza", "vault"], pivot="wall-axis",
                         notes="Tee: through-run flanges at Unity x=+-0.6, branch flange up at y=+0.6, drain valve below. Pivot on the wall plane at "
                               "the run/branch axis intersection; ports in 'ports'."),
    "Wall_Vent_A": dict(fn=wall_vent_a, cat="dressing", zones=["plaza", "metro", "facility", "rooftops"], pivot=_W,
                        notes="Louvred exhaust 0.72 x 0.56 on the wall, 0.2 m deep with a rain hood, bird mesh, rust/grease streaks. Pivot back-centre."),
    "Wall_Vent_B": dict(fn=wall_vent_b, cat="dressing", zones=["plaza", "metro", "facility", "rooftops"], pivot=_W,
                        notes="Round fan exhaust in a 0.56 m glossy black housing, ring grille, slanted rain shade, amber/green status LEDs, side "
                              "conduit into the wall. Pivot back-centre."),
    "Electrical_Box_A": dict(fn=electrical_box_a, cat="dressing", zones=["plaza", "metro", "facility", "rooftops", "vault"], pivot=_W,
                             notes="0.4 x 0.52 x 0.17 wall junction box: hinged door, latch, hazard triangle, green/amber/red status LEDs, conduits "
                                   "running 0.35-0.45 m down/up and elbowing into the wall. Pivot back-centre (box centre). Mount ~1.2-1.8 m."),
    "Electrical_Box_B": dict(fn=electrical_box_b, cat="dressing", zones=["plaza", "metro", "rooftops"], pivot=_W,
                             notes="0.72 x 0.42 x 0.2 green meter/breaker box: two doors, dark meter window with cyan readout, padlock, side louvres, "
                                   "flexible conduit loop, a messy bundle of tapped cables out of the top into the wall. Pivot back-centre."),
    "Electrical_Cabinet_Tall": dict(fn=electrical_cabinet_tall, cat="dressing", zones=["plaza", "metro", "facility"], pivot="wall-base",
                                    notes="0.9 x 1.85 x 0.42 street distribution cabinet on a hazard-striped plinth: double doors with louvres and bar "
                                          "handles, rain hood, cyan LED status strip + indicator cluster + status display, conduits up into the wall. "
                                          "Pivot wall-base (floor, back face on the wall, centred)."),
    "Fire_Extinguisher_Cabinet": dict(fn=fire_extinguisher_cabinet, cat="dressing", zones=["metro", "facility", "plaza", "vault"], pivot=_W,
                                      notes="0.36 x 0.78 x 0.2 red cabinet, glass door, extinguisher inside; glowing pictogram light box above (flame + "
                                            "arrow, no text). Pivot back-centre at the cabinet centre (mount centre ~1.2 m). 'light' = sign glow."),
    "Wall_Lamp_Cage": dict(fn=wall_lamp_cage, cat="dressing", zones=["metro", "facility", "plaza", "rooftops"], pivot=_W,
                           notes="Jelly-jar bulkhead on a short arm with a wire cage and warm bulb (emit_panel_warm), conduit feed from above. "
                                 "Pivot back-centre (wall plate). Point light at 'light' (warm, range ~6)."),
    "Wall_Lamp_LED": dict(fn=wall_lamp_led, cat="dressing", zones=["plaza", "metro", "facility", "rooftops"], pivot=_W,
                          notes="Slim angled LED wall-pack 0.46 m wide: glossy black wedge, white emitter underneath (emit_panel_white), cyan accent "
                                "line (emit_strip_cyan), heatsink fins. Pivot back-centre. Spot light at 'light' pointing down/out."),
}


# ============================================================================================== soft-body helpers
def soft_box(sx, sy, sz, cuts=4, mat="cardboard_wet", fn=None, base=True, name="softbox"):
    """Subdivided box (grid-filled faces) for organic deformation; fn(co)->co in local space (base at z=0)."""
    p = K._new(mat, name)
    bmesh.ops.create_cube(p.bm, size=1.0)
    if cuts > 0:
        bmesh.ops.subdivide_edges(p.bm, edges=p.bm.edges[:], cuts=cuts, use_grid_fill=True)
    bmesh.ops.scale(p.bm, vec=(sx, sy, sz), verts=p.bm.verts)
    if base:
        p.move(0, 0, sz / 2)
    if fn:
        p.displace(fn)
    p.bm.normal_update()
    return p


def ribbon(left, right, mat, out=None, name="ribbon"):
    """Quad strip between two polylines; faces are flipped to agree with out(center) -> outward vector."""
    p = K._new(mat, name)
    bm = p.bm
    Lv = [bm.verts.new(tuple(v)) for v in left]
    Rv = [bm.verts.new(tuple(v)) for v in right]
    for i in range(len(Lv) - 1):
        bm.faces.new((Lv[i], Rv[i], Rv[i + 1], Lv[i + 1]))
    bm.normal_update()
    if out is not None:
        for f in bm.faces:
            if f.normal.dot(Vector(out(f.calc_center_median()))) < 0:
                f.normal_flip()
    return p


def cyl_patch(r, a0, a1, z0, z1, mat, at=(0, 0, 0), n=6):
    """Curved patch (label) on a vertical cylinder of radius r between angles a0..a1 (deg)."""
    cx, cy, cz = at
    left = [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)), cz + z0) for i in range(n + 1)]
    right = [(x, y, cz + z1) for x, y, _ in left]
    return ribbon(left, right, mat, out=lambda c: (c.x - cx, c.y - cy, 0))


# ============================================================================================== soggy cardboard
def _carton_fn(L, W, H, sag, bulge, lean=0.0, crush=0.0, seed=1):
    rnd = random.Random(seed)
    cx, cy = rnd.choice((-1, 1)), rnd.choice((-1, 1))
    crease = rnd.uniform(0.25, 0.4)

    def fn(co):
        x, y, z = co
        u, v, w = 2 * x / L, 2 * y / W, max(0.0, min(1.0, z / H))
        dz = -sag * (1 - u * u) * (1 - v * v) * w ** 3
        k = max(0.0, (u * cx + v * cy - 0.9) / 1.1)
        dz -= crush * k * k * w ** 2
        bx = bulge * math.sin(math.pi * w) * (1 - v * v) * u + 0.012 * (1 - w) ** 6 * u
        by = bulge * math.sin(math.pi * w) * (1 - u * u) * v + 0.012 * (1 - w) ** 6 * v
        cr = 0.012 * math.exp(-((w - crease) / 0.05) ** 2)
        bx -= cr * u * (1 - v * v)
        by -= cr * v * (1 - u * u) * 0.6
        # slight random wrinkle so faces never read as perfectly flat
        n = 0.003 * math.sin(x * 23 + seed) * math.sin(z * 19 + y * 7)
        return (x + bx + lean * w * w + n * u, y + by + n * v, z + dz)
    return fn


def _carton(L, W, H, sag=0.04, bulge=0.012, lean=0.0, crush=0.0, seed=1, tape=True, label=True):
    fn = _carton_fn(L, W, H, sag, bulge, lean, crush, seed)
    b = soft_box(L, W, H, K.seg(6, 2) if K.LOD < 2 else 1, "cardboard_wet", fn)
    b.bevel(0.006, 1, angle=40)
    b.set_mat("cardboard_soaked", where=lambda f: f.calc_center_median().z < H * 0.2 + 0.03 * math.sin(f.calc_center_median().x * 9 + seed))
    b.set_mat("cardboard_soaked", where=lambda f: f.normal.z > 0.5 and abs(f.calc_center_median().x) < L * 0.22 and abs(f.calc_center_median().y) < W * 0.25)
    if tape and K.LOD < 2:
        # packing tape over the lid seam and 9 cm down both ends
        n = 10
        e = 0.0025
        def P(x, y, z, nx=0.0, nz=1.0):
            q = fn(Vector((x, y, z)))
            return (q[0] + nx * e, q[1], q[2] + nz * e)
        left, right = [], []
        for i in range(n + 1):
            x = -L / 2 + L * i / n
            left.append(P(x, -0.026, H))
            right.append(P(x, 0.026, H))
        ribbon(left, right, "tape_brown", out=lambda c: (0, 0, 1))
        for sx in (-1, 1):
            l2 = [P(sx * L / 2, -0.026, H - t, sx, 0) for t in (0.0, 0.03, 0.06, 0.09)]
            r2 = [P(sx * L / 2, 0.026, H - t, sx, 0) for t in (0.0, 0.03, 0.06, 0.09)]
            ribbon(l2, r2, "tape_brown", out=lambda c, sx=sx: (sx, 0, 0))
    if label and detail():
        # soggy shipping label + barcode bars on the front face
        rnd = random.Random(seed + 5)
        lx, lz = rnd.uniform(-L * 0.2, L * 0.15), H * rnd.uniform(0.45, 0.6)
        q = fn(Vector((lx, -W / 2, lz)))
        box(0.13, 0.002, 0.09, at=(q[0], q[1] - 0.002, q[2]), mat="metal_painted_white").rot_about(q, y=rnd.uniform(-8, 8))
        for i in range(9):
            w = 0.002 if i % 3 else 0.005
            box(w, 0.0015, 0.03, at=(q[0] - 0.045 + i * 0.008, q[1] - 0.0035, q[2] - 0.02), mat="black")
        box(0.06, 0.0015, 0.006, at=(q[0] + 0.02, q[1] - 0.0035, q[2] + 0.025), mat="black")
        box(0.04, 0.0015, 0.006, at=(q[0] + 0.03, q[1] - 0.0035, q[2] + 0.01), mat="black")
    return b


def cardboard_box_wet(L=0.6, W=0.42, H=0.4, seed=1, sag=0.045, crush=0.05, lean=0.015):
    _carton(L, W, H, sag, 0.014, lean, crush, seed)
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, W, H))]}


def _flap(hinge_a, hinge_b, outward, fh, th0, k, mat="cardboard_wet"):
    """Bent cardboard flap hinged on the top edge a-b, folding toward `outward` (unit XY vector)."""
    a, b = Vector(hinge_a), Vector(hinge_b)
    o = Vector(outward)
    n = 4 if detail() else 2
    rows = []
    for j in range(n + 1):
        s = fh * j / n
        if abs(k) < 1e-4:
            yo, zu = s * math.sin(th0), s * math.cos(th0)
        else:
            yo = (math.cos(th0) - math.cos(th0 + k * s)) / k
            zu = (math.sin(th0 + k * s) - math.sin(th0)) / k
        rows.append(o * yo + Vector((0, 0, zu)))
    p = K._new(mat, "flap")
    bm = p.bm
    m = 3
    grid = [[bm.verts.new(tuple(a.lerp(b, i / m) + rows[j])) for i in range(m + 1)] for j in range(n + 1)]
    for j in range(n):
        for i in range(m):
            bm.faces.new((grid[j][i], grid[j][i + 1], grid[j + 1][i + 1], grid[j + 1][i]))
    bm.normal_update()
    back = p.copy()
    bmesh.ops.reverse_faces(back.bm, faces=back.bm.faces)
    back.move(*(-o * 0.003))
    back.set_mat("cardboard_soaked")
    return p


def cardboard_box_open(L=0.52, W=0.46, H=0.44, seed=4):
    """Open soggy box: flaps splayed and drooping, wet crumpled paper inside."""
    fn = _carton_fn(L, W, H, 0.0, 0.016, 0.0, 0.0, seed)
    b = soft_box(L, W, H, K.seg(6, 2), "cardboard_wet", fn)
    top = [f for f in b.bm.faces if f.normal.z > 0.9 and f.calc_center_median().z > H * 0.9]
    bmesh.ops.delete(b.bm, geom=top, context="FACES")
    b.set_mat("cardboard_soaked", where=lambda f: f.calc_center_median().z < H * 0.22)
    inner = b.copy()
    bmesh.ops.reverse_faces(inner.bm, faces=inner.bm.faces)
    inner.scale(0.975, 0.97, 1.0)
    inner.move(0, 0, 0.004)
    inner.set_mat("cardboard_soaked")
    # flaps: front/back (long), left/right (short), each splayed and drooping
    q = lambda x, y: Vector(fn(Vector((x, y, H))))
    _flap(q(-L / 2, -W / 2), q(L / 2, -W / 2), (0, -1, 0), W / 2 - 0.01, math.radians(120), 1.6)
    _flap(q(-L / 2, W / 2), q(L / 2, W / 2), (0, 1, 0), W / 2 - 0.01, math.radians(70), 2.4)
    _flap(q(-L / 2, -W / 2), q(-L / 2, W / 2), (-1, 0, 0), L / 2 - 0.02, math.radians(150), 0.8)
    _flap(q(L / 2, -W / 2), q(L / 2, W / 2), (1, 0, 0), L / 2 - 0.02, math.radians(40), 3.0)
    # contents: soaked fill + crumpled paper + a bottle
    K.plane(L * 0.94, W * 0.92, at=(0, 0, H * 0.62), mat="cardboard_soaked")
    rnd = random.Random(seed)
    for i in range(5 if detail() else 2):
        s = rnd.uniform(0.07, 0.13)
        rock((s, s * 0.9, s * 0.7), seed * 13 + i, cuts=10, mat="plaster", rough=0.08, bevel=0.0).move(
            rnd.uniform(-L * 0.3, L * 0.3), rnd.uniform(-W * 0.3, W * 0.3), H * 0.62 + s * 0.25)
    bt = lathe([(0.001, 0.0), (0.032, 0.0), (0.033, 0.16), (0.012, 0.21), (0.011, 0.24), (0.001, 0.24)], 10, mat="glass_dark")
    bt.rot(y=62).rot(z=30).move(0.06, 0.02, H * 0.62 + 0.03)
    return {"colliders": [K.collider_box((0, 0, H / 2), (L, W, H))]}


def cardboard_box_stack(seed=9):
    _carton(0.72, 0.52, 0.46, 0.06, 0.02, 0.0, 0.08, seed)
    m0 = K.part_count()
    _carton(0.56, 0.42, 0.38, 0.045, 0.015, 0.02, 0.05, seed + 1)
    for p in K.parts_since(m0):
        p.rot(z=9).move(0.03, 0.02, 0.46 - 0.035)
    m1 = K.part_count()
    _carton(0.4, 0.32, 0.3, 0.03, 0.01, 0.0, 0.03, seed + 2, label=False)
    for p in K.parts_since(m1):
        p.rot(y=-7).rot(z=-14).move(-0.05, 0.0, 0.46 + 0.38 - 0.06)
    # collapsed box slumped against the stack + flattened sheet on the ground
    m2 = K.part_count()
    _carton(0.5, 0.4, 0.3, 0.09, 0.03, 0.06, 0.12, seed + 3, tape=False, label=False)
    for p in K.parts_since(m2):
        p.rot(y=-4).rot(z=70).move(0.62, -0.08, 0.0)
    sheet = soft_box(0.7, 0.5, 0.006, 4 if detail() else 1, "cardboard_soaked",
                     lambda co: (co.x, co.y, co.z + 0.02 * math.sin(co.x * 6) * (co.y + 0.25)))
    sheet.rot(z=-20).move(-0.25, -0.5, 0.0)
    return {"colliders": [K.collider_box((0, 0, 0.42), (0.72, 0.52, 0.84)), K.collider_box((0.62, -0.08, 0.15), (0.45, 0.55, 0.3))]}


# ============================================================================================== drums, pallets
def barrel_plastic(mat="plastic_blue", seed=2):
    """HDPE 220 L drum: rolling hoops, chimes, two bungs, a weathered label and a dent."""
    prof = [(0.001, 0.016), (0.25, 0.016), (0.262, 0.0), (0.282, 0.0), (0.292, 0.02), (0.292, 0.27), (0.299, 0.283), (0.302, 0.31),
            (0.299, 0.337), (0.292, 0.35), (0.292, 0.6), (0.299, 0.613), (0.302, 0.64), (0.299, 0.667), (0.292, 0.68), (0.292, 0.895),
            (0.286, 0.922), (0.276, 0.935), (0.262, 0.935), (0.256, 0.922), (0.001, 0.922)]
    d = lathe(prof, 28, mat=mat, name="drum")
    rnd = random.Random(seed)
    dent_a = math.radians(rnd.uniform(200, 320))
    dc = Vector((math.cos(dent_a) * 0.292, math.sin(dent_a) * 0.292, rnd.uniform(0.42, 0.52)))

    def dent(co):
        dd = (co - dc).length
        if dd < 0.16:
            f = (1 - dd / 0.16) ** 2 * 0.03
            rr = Vector((co.x, co.y, 0)).normalized()
            return co - rr * f
        return co
    d.displace(dent)
    # bungs
    for a, r in ((0.0, 0.034), (180.0, 0.024)):
        x, y = math.cos(math.radians(a)) * 0.19, math.sin(math.radians(a)) * 0.19
        cyl(r + 0.01, 0.006, 12, at=(x, y, 0.922), mat=mat)
        cyl(r, 0.014, 8, at=(x, y, 0.926), mat=mat, start=0)
        if detail():
            box(r * 1.4, 0.006, 0.006, at=(x, y, 0.944), mat=mat)
    if detail():
        # label: white sheet with an orange hazard diamond and black bars (no text)
        cyl_patch(0.3035, -118, -62, 0.4, 0.58, "metal_painted_white")
        dmd = box(0.06, 0.004, 0.06, at=(0, 0, 0), mat="plastic_orange")
        dmd.rot(y=45).move(0, -0.305, 0.5).rot(z=-14)
        dmd2 = box(0.025, 0.003, 0.025, at=(0, 0, 0), mat="black")
        dmd2.rot(y=45).move(0, -0.308, 0.5).rot(z=-14)
        for i in range(3):
            cyl_patch(0.3045, -84 + 0, -66, 0.555 - i * 0.022, 0.565 - i * 0.022, "black", n=3)
        # grime: dark drip marks from the top chime, scuffs at the base
        for k in range(4):
            a0 = rnd.uniform(0, 360)
            cyl_patch(0.293, a0, a0 + rnd.uniform(3, 7), 0.69, 0.69 + rnd.uniform(0.08, 0.2), "soil_dark", n=1)
        a0 = rnd.uniform(0, 360)
        cyl_patch(0.293, a0, a0 + 60, 0.02, 0.09, "soil_dark", n=6)
    return {"colliders": [{"type": "capsule", "center": [0, 0.47, 0], "radius": 0.3, "height": 0.94, "direction": "Y"}]}


def _pallet(seed=1, broken=0, fine=True):
    rnd = random.Random(seed)
    bv = 0.003 if fine else 0.0
    L, W = 1.2, 0.8
    # bottom boards (along X)
    for y in (-0.3325, 0.0, 0.3325):
        box(L, 0.145 if y == 0 else 0.135, 0.022, at=(0, y + rnd.uniform(-0.004, 0.004), 0), mat="wood", base=True, bevel=bv)
    # blocks
    for x in (-0.5275, 0.0, 0.5275):
        for y in (-0.3275, 0.0, 0.3275):
            box(0.145, 0.1 if y else 0.145, 0.078, at=(x, y, 0.022), mat="wood", base=True, bevel=bv * 1.3)
    # stringer boards (along Y)
    for x in (-0.5275, 0.0, 0.5275):
        box(0.145, W, 0.022, at=(x, 0, 0.1), mat="wood", base=True, bevel=bv)
    # top deck boards (along X)
    ys = [-0.3275, -0.165, 0.0, 0.165, 0.3275]
    ws = [0.145, 0.1, 0.145, 0.1, 0.145]
    for i, (y, w) in enumerate(zip(ys, ws)):
        if i == broken and broken >= 0:
            # snapped board: two pieces, one end lifted
            box(0.62, w, 0.022, at=(-0.29, y, 0.122), mat="wood", base=True, bevel=bv)
            p = box(0.42, w, 0.022, at=(0.0, 0.0, 0.0), mat="wood", base=True, bevel=bv)
            p.rot(y=-8).move(0.39, y, 0.126)
        else:
            p = box(L, w, 0.022, at=(0, y, 0.122), mat="wood", base=True, bevel=bv)
            p.rot(z=rnd.uniform(-0.6, 0.6))
        if detail() and fine:
            for x in (-0.5275, 0.0, 0.5275):
                for dy in (-w * 0.25, w * 0.25):
                    if i == broken and x > 0.2:
                        continue
                    cyl(0.0045, 0.0015, 6, at=(x + rnd.uniform(-0.03, 0.03), y + dy, 0.144), mat="metal_dark")


def pallet_wood(seed=1):
    _pallet(seed, broken=3)
    return {"colliders": [K.collider_box((0, 0, 0.072), (1.2, 0.8, 0.144))]}


def pallet_stack(seed=6, n=6):
    rnd = random.Random(seed)
    for i in range(n):
        m0 = K.part_count()
        _pallet(seed + i, broken=(i * 3) % 7 if i % 2 else -1, fine=i == n - 1)
        for p in K.parts_since(m0):
            p.rot(z=rnd.uniform(-3.5, 3.5)).move(rnd.uniform(-0.03, 0.03), rnd.uniform(-0.03, 0.03), i * 0.146)
    # top pallet slid off and leaning
    m0 = K.part_count()
    _pallet(seed + 20, broken=1)
    for p in K.parts_since(m0):
        p.rot(y=-14).rot(z=12).move(0.12, 0.05, n * 0.146 + 0.13)
    return {"colliders": [K.collider_box((0, 0, n * 0.146 / 2 + 0.1), (1.25, 0.85, n * 0.146 + 0.2))]}


# ============================================================================================== sandbags, barricades
def _sandbag(L=0.58, W=0.33, T=0.14, mat="fabric_sandbag", seed=0):
    rnd = random.Random(seed)
    tied = rnd.choice((-1, 1))
    ph = rnd.uniform(0, 6)

    def fn(co):
        u, v, w = 2 * co.x / L, 2 * co.y / W, 2 * co.z / T
        pin = (1 - 0.55 * abs(u) ** 5) * (1 - 0.45 * abs(v) ** 4)
        z = w * T / 2 * pin * (1.0 if w > 0 else 0.8)
        fold = max(0.0, u * tied - 0.55) / 0.45
        y = co.y * (1 + 0.08 * (1 - w * w)) * (1 - 0.35 * fold ** 2)
        z = z * (1 - 0.5 * fold ** 2) - 0.012 * fold
        x = co.x * (1 + 0.04 * (1 - w * w))
        z += 0.006 * math.sin(co.x * 21 + ph) * math.sin(co.y * 17) * max(0.0, w)
        return (x, y, z)
    b = soft_box(L, W, T, 2 if detail() else 1, mat, fn, base=False)
    b.move(0, 0, T / 2)
    return b


def sandbag_wall(L=2.0, seed=12):
    rnd = random.Random(seed)
    T = 0.135
    courses = 6
    n0 = K.part_count()
    for c in range(courses):
        z = c * (T - 0.012)
        rows = (-0.165, 0.165) if c < 3 else (0.0,)
        odd = c % 2
        for ry in rows:
            if odd:
                xs = [(-0.5, 0), (0.0, 0), (0.5, 0), (-0.86, 90), (0.86, 90)]
            else:
                xs = [(-0.73, 0), (-0.245, 0), (0.245, 0), (0.73, 0)]
            for x, rz in xs:
                if rz and ry > 0.1:
                    continue
                mat = "tarp" if rnd.random() < 0.18 else "fabric_sandbag"
                b = _sandbag(0.56 if not rz else 0.6, 0.33 if not rz else 0.29, T, mat, seed * 100 + c * 10 + int(x * 10) + int(ry * 7))
                b.rot(z=rz + rnd.uniform(-4, 4), x=rnd.uniform(-2, 2)).move(x + rnd.uniform(-0.02, 0.02), (0.0 if rz and len(rows) == 1 else ry) + rnd.uniform(-0.015, 0.015), z)
    # burst bag spilling sand at the foot (front)
    if detail():
        s = rock((0.4, 0.25, 0.1), seed, cuts=12, mat="fabric_sandbag", rough=0.05, bevel=0.0)
        s.move(0.55, -0.42, 0.02)
        g = rock((0.5, 0.35, 0.06), seed + 1, cuts=12, mat="gravel", rough=0.02, bevel=0.0)
        g.move(0.5, -0.5, 0.0)
    K.ground(K.parts_since(n0))
    return {"colliders": [K.collider_box((0, 0, 0.42), (2.0, 0.6, 0.84))]}


def barricade_sheet_metal(L=2.0, seed=5):
    """Makeshift wall: overlapping corrugated sheets on pipe posts with back braces, razor wire on top and a
    battery amber flasher on the left post."""
    rnd = random.Random(seed)
    H = 1.95
    for sx in (-1, 1):
        x = sx * (L / 2 - 0.08)
        cyl(0.04, H + 0.1, 10, at=(x, 0.06, 0), mat="metal_dark")
        box(0.2, 0.2, 0.012, at=(x, 0.06, 0), mat="metal_dark", base=True, bevel=0.003)
        beam((x, 0.06, 1.3), (x, 0.75, 0.02), 0.05, 0.05, mat="metal_rusted")
        box(0.16, 0.16, 0.012, at=(x, 0.75, 0), mat="metal_rusted", base=True)
        # sandbag ballast on the brace foot
        b = _sandbag(0.5, 0.3, 0.13, "fabric_sandbag", seed + sx)
        b.rot(z=90 + 10 * sx).move(x, 0.78, 0.012)
    for z in (0.35, 1.55):
        box(L - 0.1, 0.05, 0.05, at=(0, 0.045, z), mat="metal_rusted", bevel=0.004)
    # corrugated sheets (double-sided, real corrugation)
    specs = [(-0.6, 0.82, 1.82, "corrugated", 2.0), (0.05, 0.78, 1.95, "metal_painted_red", -1.5), (0.62, 0.8, 1.74, "corrugated", 1.0)]
    for i, (x, w, h, m, tilt) in enumerate(specs):
        nx = K.seg(int(w / 0.019), 6)
        p = K.plane(w, h, mat=m, nx=nx, ny=K.seg(6, 2), name="sheet")
        p.rot(x=90)
        ph = rnd.uniform(0, 3)
        p.displace(lambda co, ph=ph, h=h: (co.x, co.y + 0.012 * math.sin(co.x * 2 * math.pi / 0.076) + 0.025 * (co.z / h) ** 2 * math.sin(co.x * 4 + ph), co.z))
        p.move(x, 0.0 - 0.012 * i, h / 2 + 0.03)
        p.rot_about((x, 0, 0), y=tilt)
        back = p.copy()
        bmesh.ops.reverse_faces(back.bm, faces=back.bm.faces)
        back.move(0, 0.003, 0)
        if detail():
            for z in (0.35, 1.55):
                for k in range(3):
                    hexbolt((x - w / 2 + 0.12 + k * (w - 0.24) / 2, -0.03 - 0.012 * i, z), "-y", 0.009, 0.006)
    # welded patch plate and graffiti-style painted glyph block (abstract strokes, no letters)
    pp = box(0.36, 0.006, 0.28, at=(0.1, -0.04, 0.75), mat="metal_plate", bevel=0.002)
    pp.rot_about((0.1, -0.04, 0.75), y=6)
    if detail():
        for i in range(4):
            box(0.012, 0.003, 0.012, at=(0.1 + (i % 2 - 0.5) * 0.32, -0.044, 0.75 + (i // 2 - 0.5) * 0.24), mat="metal_bare")
        hazard_stripes(-1.0, -0.22, 0.06, 0.22, -0.035, n=6)
    # razor wire coil along the top
    turns = K.seg(18, 8)
    pts = []
    m = turns * (10 if detail() else 6)
    for i in range(m + 1):
        t = i / m
        a = t * turns * math.tau
        pts.append((-L / 2 + 0.05 + (L - 0.1) * t + 0.03 * math.sin(a), 0.03 + 0.15 * math.cos(a), H + 0.17 + 0.15 * math.sin(a)))
    tube(pts, 0.0035, 4, "metal_bare", "razor")
    for sx in (-1, 1):
        beam((sx * (L / 2 - 0.08), 0.06, H + 0.08), (sx * (L / 2 - 0.08), 0.06, H + 0.32), 0.03, 0.03, mat="metal_dark")
    # amber flasher on the left post
    fx = -(L / 2 - 0.08)
    box(0.1, 0.07, 0.12, at=(fx, -0.02, H + 0.1), mat="plastic_orange", base=True, bevel=0.01)
    lathe([(0.055, 0.0), (0.055, 0.03), (0.04, 0.07), (0.001, 0.08)], 14, at=(fx, -0.02, H + 0.22), mat="emit_amber")
    return {"colliders": [K.collider_box((0, 0.02, 1.0), (L, 0.16, 2.0))], "light": light((fx, -0.02, H + 0.27), "amber", 4.0, 0.8)}


# ============================================================================================== chain-link fence, scaffold
def _post(x, y, h, r=0.03, mat="metal_bare", footing=True):
    cyl(r, h, 10, at=(x, y, 0), mat=mat)
    lathe([(r + 0.006, 0.0), (r + 0.006, 0.02), (r * 0.6, 0.04), (0.001, 0.045)], 10, at=(x, y, h), mat=mat)
    if footing:
        cyl(r + 0.06, 0.04, 12, at=(x, y, 0), r2=r + 0.03, mat="concrete")


def _mesh_panel(x0, x1, z0, z1, y=0.0, slack=0.02):
    nx = K.seg(8, 2)
    p = K.plane(x1 - x0, z1 - z0, mat="grating", nx=nx, ny=K.seg(4, 1), name="mesh")
    p.rot(x=90).move((x0 + x1) / 2, y, (z0 + z1) / 2)
    p.displace(lambda co: (co.x, co.y + slack * math.sin(math.pi * (co.x - x0) / (x1 - x0)) * math.sin(math.pi * (co.z - z0) / (z1 - z0)), co.z))
    return p


def _barbed_wire(a, b, n=14):
    tube([a, b], 0.0022, 4, "metal_bare", "barb")
    if detail():
        a, b = Vector(a), Vector(b)
        for i in range(1, n):
            c = a.lerp(b, i / n)
            beam(c + Vector((-0.012, -0.012, 0.012)), c + Vector((0.012, 0.012, -0.012)), 0.003, mat="metal_bare")


def fence_chainlink(L=2.0, gate=False, seed=3):
    hx = L / 2
    H = 2.0
    pr = 0.045 if gate else 0.032
    for sx in (-1, 1):
        _post(sx * hx, 0, H, pr)
        # barbed-wire extension arm leaning out (+Y, Unity -Z = the 'outside')
        beam((sx * hx, 0.0, H - 0.02), (sx * hx, 0.24, H + 0.24), 0.03, 0.012, mat="metal_bare", up=(1, 0, 0))
        if detail():
            for z in (0.3, 0.95, 1.6):  # tension bands
                t = torus(pr + 0.005, 0.005, n_major=10, n_minor=4, mat="metal_bare")
                t.move(sx * hx, 0, z)
    for k in range(3):
        f = (k + 1) / 3
        _barbed_wire((-hx, 0.08 * f * 3, H + 0.08 * f * 3), (hx, 0.08 * f * 3, H + 0.08 * f * 3))
    meta = {}
    if not gate:
        tube([(-hx, 0, H - 0.05), (hx, 0, H - 0.05)], 0.021, 8, "metal_bare", "rail")
        tube([(-hx, 0, 0.06), (hx, 0, 0.06)], 0.004, 4, "metal_bare", "tension")
        _mesh_panel(-hx + pr, hx - pr, 0.06, H - 0.05, 0.0, 0.03)
        if detail():
            for i in range(9):
                x = -hx + 0.2 + i * (L - 0.4) / 8
                t = torus(0.025, 0.002, n_major=6, n_minor=3, mat="metal_bare")
                t.rot(y=90).move(x, 0, H - 0.05)
            # trash caught at the foot of the fence
            rnd = random.Random(seed)
            for i in range(3):
                s = rnd.uniform(0.06, 0.12)
                rock((s * 1.4, s, s * 0.7), seed + i, cuts=9, mat=rnd.choice(("plastic_dark", "plaster", "cardboard_soaked")), rough=0.06, bevel=0.0).move(rnd.uniform(-0.8, 0.8), 0.06, s * 0.3)
    else:
        # gate leaf: tube frame hinged on the -X post (Unity +X), braced, mesh in-fill, drop latch + chain + padlock
        x0, x1, z0, z1 = -hx + 0.07, hx - 0.07, 0.08, H - 0.08
        fr = [(x0, 0, z0), (x1, 0, z0), (x1, 0, z1), (x0, 0, z1)]
        tube(fr, 0.022, 8, "metal_bare", "gateframe", closed=True)
        tube([(x0, 0, (z0 + z1) / 2), (x1, 0, (z0 + z1) / 2)], 0.018, 8, "metal_bare")
        tube([(x0, 0, z0), (x1, 0, (z0 + z1) / 2)], 0.016, 8, "metal_bare")
        _mesh_panel(x0, x1, z0, z1, 0.0, 0.015)
        for z in (0.35, H - 0.35):
            t = torus(0.05, 0.01, n_major=10, n_minor=4, mat="metal_dark")
            t.move(-hx, 0, z)
            box(0.07, 0.02, 0.03, at=(-hx + 0.05, 0, z), mat="metal_dark")
        # fork latch + chain + padlock on the +X post
        box(0.1, 0.04, 0.04, at=(hx - 0.05, 0, 1.0), mat="metal_dark", bevel=0.004)
        cyl(0.01, 0.6, 6, at=(x1 - 0.05, -0.03, 0.05), mat="metal_bare")
        if detail():
            for i in range(7):
                t = torus(0.018, 0.0045, n_major=8, n_minor=4, mat="chrome_scratched")
                t.rot(x=90 if i % 2 else 0, y=0 if i % 2 else 90).move(hx - 0.02, -0.05 + 0.0 * i, 1.12 - i * 0.03)
            box(0.045, 0.02, 0.05, at=(hx - 0.02, -0.06, 0.88), mat="metal_painted_yellow", bevel=0.005)
            t = torus(0.016, 0.004, arc=180, n_major=8, n_minor=4, mat="chrome_scratched", start=0)
            t.rot(x=90).move(hx - 0.02, -0.06, 0.905)
            # warning plate wired to the mesh (abstract pictogram, no text)
            box(0.34, 0.004, 0.24, at=(0.0, -0.025, 1.35), mat="metal_painted_white", bevel=0.002)
            warning_triangle((0.0, -0.027, 1.36), 0.16)
            box(0.3, 0.002, 0.02, at=(0.0, -0.028, 1.255), mat="metal_painted_red")
        meta = {"hinge": U((-hx, 0, 0)), "opening": [L - 0.14, H - 0.16]}
    return dict({"colliders": [K.collider_box((0, 0, H / 2), (L, 0.08, H))]}, **meta)


def scaffolding_section(L=2.0, W=1.0, lift=2.0, seed=4):
    """Tube-and-clamp scaffold bay: 4 standards on sole boards, ledgers, transoms, face brace, plank deck with toe
    boards, guard + mid rails, a clamped LED work light and a torn mesh net."""
    rnd = random.Random(seed)
    r = 0.024
    hx, hy = L / 2, W / 2
    top = lift + 1.05
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * hx, sy * hy
            box(0.22, 0.6, 0.035, at=(x, y, 0), mat="wood", base=True, bevel=0.003)
            box(0.15, 0.15, 0.006, at=(x, y, 0.035), mat="metal_bare", base=True)
            cyl(r, top, 8, at=(x, y, 0.041), mat="metal_bare")
    # ledgers (along X) and transoms (along Y)
    for z in (0.2, lift, lift + 0.5, top - 0.02):
        for sy in (-1, 1):
            if z > lift and sy > 0 and z < top - 0.1:
                continue
            tube([(-hx - 0.12, sy * hy - sy * 0.05, z), (hx + 0.12, sy * hy - sy * 0.05, z)], r, 8, "metal_bare", "ledger")
    for z in (0.26, lift + 0.055):
        for sx in (-1, 1):
            tube([(sx * hx + sx * 0.05, -hy - 0.12, z), (sx * hx + sx * 0.05, hy + 0.12, z)], r, 8, "metal_bare", "transom")
    tube([(0, -hy - 0.12, lift + 0.055), (0, hy + 0.12, lift + 0.055)], r, 8, "metal_bare", "transom")
    # face brace on the front (-Y)
    tube([(-hx, -hy - 0.05, 0.2), (hx, -hy - 0.05, lift)], r, 8, "metal_bare", "brace")
    # clamps at the joints
    if detail():
        for sx in (-1, 1):
            for sy in (-1, 1):
                for z in (0.2, 0.26, lift, lift + 0.055, lift + 0.5, top - 0.02):
                    c = box(0.065, 0.065, 0.075, at=(sx * hx, sy * hy, z), mat="metal_dark", bevel=0.008)
                    hexbolt((sx * hx + sx * 0.032, sy * hy, z), "+x" if sx > 0 else "-x", 0.01, 0.012)
    # deck planks (scaffold boards) + toe boards
    zd = lift + 0.055 + r
    nb = 4
    for i in range(nb):
        y = -hy + 0.13 + i * (W - 0.26) / (nb - 1)
        p = box(L + 0.3, 0.215, 0.038, at=(rnd.uniform(-0.04, 0.04), y, zd), mat="wood", base=True, bevel=0.004)
        p.rot(z=rnd.uniform(-0.7, 0.7))
        if detail():
            for sx in (-1, 1):
                box(0.006, 0.217, 0.03, at=(sx * (L / 2 + 0.13), y, zd + 0.004), mat="metal_bare", base=True)
    for sy in (-1, 1):
        box(L + 0.2, 0.03, 0.15, at=(0, sy * (hy + 0.04), zd), mat="wood", base=True, bevel=0.003)
    # torn mesh net hanging off the back guard rail (+Y)
    net = K.plane(L * 0.8, 1.1, mat="grating", nx=K.seg(8, 2), ny=K.seg(5, 2), name="net")
    net.rot(x=90).move(-0.15, hy + 0.06, top - 0.6)
    net.displace(lambda co: (co.x, co.y + 0.06 * math.sin(co.x * 3.0) * (top - co.z), co.z - 0.08 * (co.x + 1) ** 2 * 0.2))
    # LED work light clamped to the front-left standard, with its cable
    wx, wy, wz = -hx + 0.02, -hy - 0.09, lift + 0.85
    box(0.06, 0.06, 0.07, at=(-hx, -hy - 0.04, wz), mat="metal_dark")
    hd = box(0.24, 0.08, 0.17, at=(0, 0, 0), mat="metal_painted_yellow", bevel=0.012)
    em = box(0.2, 0.01, 0.13, at=(0, -0.042, 0), mat="emit_panel_white")
    for p in (hd, em):
        p.rot(x=-35).rot(z=20).move(wx + 0.1, wy - 0.06, wz)
    tube(bend_path([(wx + 0.1, wy, wz - 0.06), (-hx + 0.03, -hy - 0.04, wz - 0.2), (-hx + 0.03, -hy - 0.03, 0.5), (-hx + 0.3, -hy - 0.25, 0.01)], 0.12, 3), 0.007, 6, "rubber")
    cols = [K.collider_box((0, 0, zd + 0.019), (L + 0.3, W, 0.04))]
    cols += [K.collider_box((sx * hx, sy * hy, top / 2), (0.06, 0.06, top)) for sx in (-1, 1) for sy in (-1, 1)]
    cols += [K.collider_box((0, sy * hy, top - 0.4), (L, 0.06, 0.8)) for sy in (-1,)]
    return {"colliders": cols, "deckHeight": round(zd + 0.038, 3), "light": light((wx + 0.1, wy - 0.15, wz - 0.1), "white", 8.0, 1.5)}


# ============================================================================================== dead plants
def _branch(rnd, p, d, L, r, depth, mat="plant_dead"):
    p, d = Vector(p), Vector(d).normalized()
    side = d.cross(Vector((0, 0, 1)))
    if side.length < 0.1:
        side = Vector((1, 0, 0))
    side.normalize()
    n = 3 if detail() else 2
    pts = [p]
    for i in range(1, n + 1):
        t = i / n
        pts.append(p + d * L * t + side * rnd.uniform(-0.04, 0.04) * L + Vector((0, 0, -0.08 * L * t * t)))
    tube(pts, r, 5 if r > 0.008 else 4, mat, "branch", radii=[r * (1 - 0.45 * i / n) for i in range(n + 1)])
    if depth > 0:
        for k in range(rnd.choice((2, 2, 3))):
            nd = d + Vector((rnd.uniform(-0.8, 0.8), rnd.uniform(-0.8, 0.8), rnd.uniform(-0.1, 0.5)))
            _branch(rnd, pts[-1] if k == 0 else pts[-2], nd, L * rnd.uniform(0.5, 0.75), r * 0.6, depth - 1, mat)
    elif detail() and rnd.random() < 0.5:
        lf = box(0.03, 0.002, 0.045, at=tuple(pts[-1]), mat="plant_dead")
        lf.rot_about(tuple(pts[-1]), x=rnd.uniform(-60, 60), z=rnd.uniform(0, 180))


def plant_pot_dead_a(seed=3):
    """Terracotta pot with a dead shrub, chipped rim, dry leaves."""
    prof = [(0.001, 0.0), (0.16, 0.0), (0.17, 0.02), (0.235, 0.46), (0.262, 0.47), (0.268, 0.53), (0.25, 0.54), (0.238, 0.5)]
    pot = lathe(prof, 24, mat="terracotta", close_top=False)
    if detail():
        boolean(pot, rock((0.14, 0.14, 0.12), seed, cuts=10, mat="terracotta", rough=0.05, bevel=0.0).move(0.2, -0.16, 0.54))
    soil = lathe([(0.237, 0.47), (0.15, 0.475), (0.05, 0.48), (0.001, 0.482)], 20, mat="soil_dark", close_bottom=False)
    rnd = random.Random(seed)
    # salt / lime crust stains on the pot
    if detail():
        _branch(rnd, (0.0, 0.0, 0.47), (0.08, 0.05, 1.0), 0.42, 0.016, 3)
        _branch(rnd, (0.03, -0.02, 0.47), (-0.6, -0.3, 1.0), 0.32, 0.01, 2)
        for i in range(10):
            a, d = rnd.uniform(0, math.tau), rnd.uniform(0.0, 0.22)
            z = 0.484 if d < 0.2 else 0.0
            if i >= 6:
                d, z = rnd.uniform(0.3, 0.5), 0.002
            lf = box(0.035, 0.03, 0.003, at=(math.cos(a) * d, math.sin(a) * d, z), mat="plant_dead")
            lf.rot_about((math.cos(a) * d, math.sin(a) * d, z), x=rnd.uniform(-20, 20), z=rnd.uniform(0, 180))
    else:
        _branch(rnd, (0.0, 0.0, 0.47), (0.08, 0.05, 1.0), 0.42, 0.016, 1)
    return {"colliders": [K.collider_box((0, 0, 0.27), (0.54, 0.54, 0.54))]}


def plant_pot_dead_b(seed=8):
    """Square concrete planter with a dead dwarf palm (ringed trunk, drooping brown fronds) and litter."""
    S, H = 0.56, 0.5
    pl = box(S, S, H, mat="concrete_dark", base=True, bevel=0.012, bseg=2)
    inset(pl, faces_where(pl, lambda f: f.normal.z > 0.9), 0.05, -0.06, mat="soil_dark")
    if detail():
        streak(-0.15, H - 0.03, 0.22, 0.06, -S / 2, seed=91, mat="concrete_wet")
        streak(0.12, H - 0.03, 0.16, 0.04, -S / 2, seed=92, mat="concrete_wet")
        streak(0.05, H - 0.03, 0.2, 0.05, S / 2, facing="+x", seed=93, mat="concrete_wet")
    rnd = random.Random(seed)
    # trunk: ringed lathe
    prof = []
    nr = 12 if detail() else 5
    for i in range(nr + 1):
        z = H - 0.06 + 0.75 * i / nr
        rr = 0.055 - 0.018 * i / nr + (0.008 if i % 2 else 0.0)
        prof.append((rr, z))
    tr = lathe(prof, 10, mat="plant_dead", close_bottom=False)
    tr.displace(lambda co: (co.x + 0.06 * ((co.z - H) / 0.75) ** 2, co.y, co.z))
    tx, tz = 0.06, H - 0.06 + 0.75
    # fronds: drooping spines with leaflet strips
    nf = 8 if detail() else 5
    for k in range(nf):
        a = k * math.tau / nf + rnd.uniform(-0.2, 0.2)
        droop = rnd.uniform(0.5, 1.2)
        Lf = rnd.uniform(0.45, 0.65)
        pts = []
        for i in range(6):
            t = i / 5
            pts.append((tx + math.cos(a) * Lf * t, math.sin(a) * Lf * t, tz + 0.25 * t - droop * Lf * t * t))
        tube(pts, 0.006, 4, "plant_dead", "frond")
        if K.LOD < 2:
            for i in range(1, 6, 1 if detail() else 2):
                p0 = Vector(pts[i - 1])
                p1 = Vector(pts[i])
                mid = (p0 + p1) / 2
                for sgn in (-1, 1):
                    # leaflet: flat strip hanging down and out from the spine
                    side = Vector((-math.sin(a) * sgn, math.cos(a) * sgn, 0))
                    tip = mid + side * (0.15 - 0.012 * i) + Vector((math.cos(a), math.sin(a), 0)) * 0.05 + Vector((0, 0, -0.1 - 0.02 * i))
                    w = Vector((math.cos(a), math.sin(a), 0)) * 0.016
                    ribbon([mid - w, tip - w * 0.3], [mid + w, tip + w * 0.3], "plant_dead", out=lambda c, side=side: (side.x, side.y, 0.3))
                    ribbon([mid + w, tip + w * 0.3], [mid - w, tip - w * 0.3], "plant_dead", out=lambda c, side=side: (-side.x, -side.y, -0.3))
    # litter: crushed can, cigarette butts on the soil
    if detail():
        c = cyl(0.033, 0.07, 10, mat="chrome_scratched")
        c.displace(lambda co: (co.x * (1 - 0.3 * math.sin(co.z * 40)), co.y, co.z))
        c.rot(y=80).move(-0.12, -0.12, H - 0.06 + 0.03)
        for i in range(4):
            cyl(0.004, 0.025, 6, axis="X", mat="paint_glossy_white").rot(z=rnd.uniform(0, 180)).move(rnd.uniform(-0.18, 0.18), rnd.uniform(-0.18, 0.18), H - 0.055)
    return {"colliders": [K.collider_box((0, 0, H / 2), (S, S, H))]}


# ============================================================================================== rebar rubble
def rebar(pts_or_start, direction=None, length=None, r=0.009, rnd=None):
    if direction is None:
        return tube(pts_or_start, r, 6 if detail() else 4, "metal_rusted", "rebar")
    rnd = rnd or random.Random(1)
    d = Vector(direction).normalized()
    p0 = Vector(pts_or_start)
    side = d.cross(Vector((0, 0, 1)))
    if side.length < 0.1:
        side = Vector((1, 0, 0))
    side.normalize()
    bend = rnd.uniform(-0.5, 0.5)
    droop = rnd.uniform(-0.5, 0.15)
    pts = [p0 + d * length * (i / 4) + side * bend * length * (i / 4) ** 2 * 0.5 + Vector((0, 0, droop * length * (i / 4) ** 2 * 0.5)) for i in range(5)]
    return tube(pts, r, 6 if detail() else 4, "metal_rusted", "rebar")


def broken_slab(L, W, T, seed, edges=("+x",), mat="concrete", chips=4, bars=True, spacing=0.16):
    """Slab with fractured edges (boolean chunks) and exposed, bent rebar mesh at the breaks."""
    rnd = random.Random(seed)
    s = box(L, W, T, mat=mat, bevel=0.012 if detail() else 0.0)
    for e in edges:
        sx = 1 if e[0] == "+" else -1
        ax = e[1]
        span = W if ax == "x" else L
        nb = chips if detail() else max(2, chips // 2)
        for i in range(nb):
            f = (i + 0.5) / nb - 0.5
            c = rock((0.45, 0.5, T * 3.0), seed * 7 + i + (0 if ax == "x" else 50), cuts=10, mat="concrete_dark", rough=0.05, bevel=0.0)
            c.rot(z=rnd.uniform(0, 90))
            if ax == "x":
                c.move(sx * (L / 2 + rnd.uniform(-0.12, 0.08)), f * span, rnd.uniform(-T * 0.4, T * 0.4))
            else:
                c.move(f * span, sx * (W / 2 + rnd.uniform(-0.12, 0.08)), rnd.uniform(-T * 0.4, T * 0.4))
            boolean(s, c)
        if bars and K.LOD < 2:
            n = max(2, int(span / spacing))
            for i in range(n if detail() else max(2, n // 2)):
                f = (i + 0.5) / n - 0.5
                zz = (-T * 0.25) if i % 2 else (T * 0.22)
                if ax == "x":
                    st = (sx * (L / 2 - 0.25), f * span * 0.92, zz)
                    d = (sx, rnd.uniform(-0.25, 0.25), rnd.uniform(-0.45, 0.35))
                else:
                    st = (f * span * 0.92, sx * (W / 2 - 0.25), zz)
                    d = (rnd.uniform(-0.25, 0.25), sx, rnd.uniform(-0.45, 0.35))
                rebar(st, d, rnd.uniform(0.35, 0.75), 0.008, rnd)
            if detail():  # one exposed cross bar tying the ends
                if ax == "x":
                    rebar([(sx * (L / 2 + 0.02), -span * 0.35, T * 0.22), (sx * (L / 2 + 0.06), 0.0, T * 0.1), (sx * (L / 2 + 0.03), span * 0.3, T * 0.22)], r=0.007)
                else:
                    rebar([(-span * 0.35, sx * (W / 2 + 0.02), T * 0.22), (0.0, sx * (W / 2 + 0.06), T * 0.1), (span * 0.3, sx * (W / 2 + 0.03), T * 0.22)], r=0.007)
    return s


def chips_scatter(rnd, n, region, z=0.0, smin=0.05, smax=0.16, mats=("concrete", "concrete_dark")):
    x0, x1, y0, y1 = region
    for i in range(n if detail() else max(1, n // 3)):
        s = rnd.uniform(smin, smax)
        r = rock((s * rnd.uniform(1, 1.4), s, s * rnd.uniform(0.5, 0.8)), rnd.randint(0, 99999), cuts=rnd.randint(9, 12),
                 mat=rnd.choice(mats), rough=0.04, bevel=0.04)
        r.rot(z=rnd.uniform(0, 360)).move(rnd.uniform(x0, x1), rnd.uniform(y0, y1), z + s * 0.2)


def rubble_rebar_a(seed=14):
    """Broken floor-slab piece with a bent rebar mesh, propped on chunks, with a dust/grit pile."""
    rnd = random.Random(seed)
    m0 = K.part_count()
    broken_slab(1.4, 0.95, 0.22, seed, ("+x", "-y"), chips=4)
    for p in K.parts_since(m0):
        p.rot(y=-14, x=6).move(0, 0, 0.36)
    rock((0.5, 0.45, 0.32), seed + 1, cuts=14, mat="concrete_dark", rough=0.04).move(0.45, 0.05, 0.12)
    rock((0.3, 0.3, 0.2), seed + 2, cuts=12, mat="concrete", rough=0.04).move(-0.1, -0.2, 0.08)
    g = rock((1.2, 0.9, 0.12), seed + 3, cuts=16, mat="gravel", rough=0.02, bevel=0.0)
    g.move(0.2, 0.0, 0.0)
    chips_scatter(rnd, 9, (-0.8, 0.9, -0.65, 0.6))
    K.ground()
    return {"colliders": [K.collider_box((0.05, 0.0, 0.3), (1.5, 1.05, 0.6))]}


def rubble_rebar_b(seed=22):
    """Fallen square column chunk: snapped ends with the rebar cage (verticals + stirrups) bent out."""
    rnd = random.Random(seed)
    S, L = 0.45, 1.5
    c = box(L, S, S, mat="concrete", bevel=0.015 if detail() else 0.0)
    for sx in (-1, 1):
        for i in range(3 if detail() else 2):
            k = rock((0.5, 0.7, 0.7), seed * 3 + i + (10 if sx > 0 else 0), cuts=10, mat="concrete_dark", rough=0.06, bevel=0.0)
            k.rot(z=rnd.uniform(0, 90)).move(sx * (L / 2 + rnd.uniform(-0.05, 0.12)), rnd.uniform(-0.2, 0.2), rnd.uniform(-0.2, 0.2))
            boolean(c, k)
    # longitudinal bars at the corners + mid-faces, bent out of both ends
    cov = S / 2 - 0.05
    for (yy, zz) in ((-cov, -cov), (cov, -cov), (-cov, cov), (cov, cov), (0, cov), (0, -cov)):
        for sx in (-1, 1):
            st = (sx * (L / 2 - 0.25), yy, zz)
            d = (sx, yy * rnd.uniform(0.5, 2.0), zz * rnd.uniform(0.0, 2.5) + rnd.uniform(-0.3, 0.3))
            rebar(st, d, rnd.uniform(0.4, 0.7), 0.011, rnd)
    if detail():  # exposed stirrups at the +X break
        for k in range(2):
            x = L / 2 + 0.04 + k * 0.12
            pts = [(x, -cov, -cov), (x, cov, -cov), (x + 0.02, cov, cov), (x + 0.01, -cov, cov), (x, -cov, -cov + 0.06)]
            rebar(pts, r=0.006)
    for p in K._parts:
        p.rot(z=12, y=4).move(0, 0, S / 2 + 0.04)
    chips_scatter(rnd, 8, (-1.0, 1.0, -0.6, 0.6))
    rock((0.5, 0.35, 0.12), seed + 9, cuts=14, mat="gravel", rough=0.02, bevel=0.0).move(0.75, 0.25, 0.0)
    K.ground()
    return {"colliders": [{"type": "box", "center": U((0, 0, S / 2 + 0.04)), "size": K.to_unity_size((L, S, S)), "rotationEuler": [0, -12, 0]}]}


ASSETS.update({
    "Cardboard_Box_Wet_A": dict(fn=cardboard_box_wet, cat="dressing", zones=["plaza", "metro", "rooftops"],
                                notes="Rain-soaked taped carton 0.6 x 0.4 x 0.42 (Unity w x h x d): sagging lid, bulging walls, soaked dark foot, "
                                      "crushed corner, soggy shipping label. Base-centre. Materials cardboard_wet / cardboard_soaked / tape_brown (matext_dressing)."),
    "Cardboard_Box_Wet_B": dict(fn=cardboard_box_open, cat="dressing", zones=["plaza", "metro", "rooftops"],
                                notes="Open soggy box 0.52 x 0.44 x 0.46: flaps splayed and drooping, wet crumpled paper and a bottle inside. Base-centre."),
    "Cardboard_Box_Stack": dict(fn=cardboard_box_stack, cat="dressing", zones=["plaza", "metro", "rooftops"],
                                notes="Three soggy cartons stacked and slumping + a collapsed one at +X (Unity -X) + a flattened sheet in front. "
                                      "Footprint ~1.2 x 0.85 x 1.0. Base-centre at the main stack."),
    "Barrel_Plastic_Blue": dict(fn=barrel_plastic, cat="dressing", zones=["plaza", "metro", "rooftops", "facility"],
                                notes="Blue HDPE 220 L drum (d 0.6, h 0.94): rolling hoops, two bungs, weathered hazard label (abstract diamond, no text), "
                                      "dent, grime drips. Base-centre. Capsule collider."),
    "Barrel_Plastic_Black": dict(fn=barrel_plastic, kw={"mat": "plastic_dark", "seed": 5}, cat="dressing", zones=["plaza", "metro", "rooftops", "facility"],
                                 notes="Black HDPE drum variant of Barrel_Plastic_Blue."),
    "Pallet_Wood": dict(fn=pallet_wood, cat="dressing", zones=["plaza", "metro", "rooftops", "facility"],
                        notes="EUR pallet 1.2 x 0.144 x 0.8: 5 deck boards (one snapped and lifted), stringers, 9 blocks, nail heads. Base-centre."),
    "Pallet_Stack": dict(fn=pallet_stack, cat="dressing", zones=["plaza", "metro", "rooftops", "facility"],
                         notes="Six jittered EUR pallets plus one slid off the top. ~1.3 x 1.2 x 0.9. Base-centre."),
    "Sandbag_Wall_2m": dict(fn=sandbag_wall, cat="dressing", zones=["plaza", "metro", "rooftops"],
                            notes="Chest-high cover: 6 courses of pillowed sandbags (double row below, single above, headers at the ends), "
                                  "2.0 x 0.85 x 0.6, burst bag with spilled sand in front (+Z). Chain every 2 m. Base-centre."),
    "Barricade_Sheet_Metal_2m": dict(fn=barricade_sheet_metal, cat="dressing", zones=["plaza", "metro", "rooftops"],
                                     notes="Makeshift wall 2.0 m: three overlapping corrugated sheets (one red) bolted to rails on pipe posts with back braces "
                                           "and sandbag ballast (back = Unity -Z), welded patch plate, hazard band, razor-wire coil, amber battery flasher "
                                           "(emit_amber, 'light'). Base-centre; the face is at Unity z=0."),
    "Fence_ChainLink_2m": dict(fn=fence_chainlink, cat="dressing", zones=["plaza", "metro", "rooftops"],
                               notes="2 m chain-link bay: galvanized posts at Unity x=+-1 on concrete footings, top rail, tension bands, mesh panel "
                                     "(grating cutout, slack), 3 strands of barbed wire on arms leaning to Unity -Z, trash caught at the foot. Base-centre; "
                                     "chain every 2 m (posts coincide)."),
    "Fence_ChainLink_Gate": dict(fn=fence_chainlink, kw={"gate": True}, cat="dressing", zones=["plaza", "metro", "rooftops"],
                                 notes="2 m gate bay for Fence_ChainLink_2m runs: braced tube-frame leaf with mesh, hinges at Unity x=+1 ('hinge'), "
                                       "drop rod, chain and padlock at x=-1, hazard plate. Static mesh (leaf closed). Base-centre."),
    "Scaffolding_Section_2m": dict(fn=scaffolding_section, cat="dressing", zones=["plaza", "metro", "rooftops"],
                                   notes="Tube-and-clamp bay 2.0 x 1.0 m, deck at ~2.1 m ('deckHeight') with 4 boards and toe boards, guard/mid rails on the "
                                         "back (Unity -Z), face brace on the front, sole boards, clamps, torn safety net, clamped LED work light "
                                         "(emit_panel_white, 'light'). Base-centre. Chain bays every 2 m along X."),
    "Plant_Pot_Dead_A": dict(fn=plant_pot_dead_a, cat="dressing", zones=["plaza", "rooftops", "facility"],
                             notes="Terracotta pot 0.54 x 0.54 with a chipped rim, dead branching shrub, dry leaves on soil and floor. Base-centre."),
    "Plant_Pot_Dead_B": dict(fn=plant_pot_dead_b, cat="dressing", zones=["plaza", "rooftops", "facility"],
                             notes="Square concrete planter 0.56 x 0.5 with a dead dwarf palm (ringed trunk, drooping brown fronds), crushed can and "
                                   "cigarette butts. Base-centre."),
    "Rubble_Rebar_A": dict(fn=rubble_rebar_a, cat="dressing", zones=["plaza", "metro", "rooftops"],
                           notes="Broken floor-slab piece ~1.6 x 0.7 x 1.2 propped on chunks, fractured edges with a bent rebar mesh, grit pile and "
                                 "chips. Base-centre."),
    "Rubble_Rebar_B": dict(fn=rubble_rebar_b, cat="dressing", zones=["plaza", "metro", "rooftops"],
                           notes="Fallen square column chunk 1.5 m (0.45 section) with snapped ends, rebar verticals and stirrups bent out, chips. "
                                 "Base-centre; rotated box collider."),
})


# ============================================================================================== facade AC stack
def grille_round(cx, y, cz, R, rings=3, mat="metal_dark", facing="-y"):
    """Fan guard: concentric rings + 4 spokes in the XZ plane at y (front faces -Y)."""
    for k in range(rings):
        rr = R * (k + 1) / rings
        t = torus(rr, 0.0035, n_major=K.seg(18, 10), n_minor=3, mat=mat)
        t.rot(x=90).move(cx, y, cz)
    for k in range(4):
        sp = box(R * 2, 0.006, 0.006, mat=mat)
        sp.rot(y=45 + k * 45).move(cx, y, cz)
    cyl(0.03, 0.01, 10, at=(cx, y - 0.005, cz), axis="Y", mat=mat)


def split_condenser(W=0.8, H=0.55, D=0.29, paint="metal_painted_white", seed=1, led_mat=None):
    """Outdoor split-AC condenser built at origin: back at y=0, base z=0, front -Y. Returns pipe exit point."""
    rnd = random.Random(seed)
    body = box(W, D, H, at=(0, -D / 2, 0), mat=paint, base=True, bevel=0.012, bseg=1)
    R = min(H * 0.4, W * 0.28)
    fx = -W * 0.14
    boolean(body, cyl(R + 0.012, 0.1, K.seg(24, 12), at=(fx, -D - 0.05, H / 2), axis="Y", mat="black"))
    cyl(R + 0.01, 0.004, K.seg(24, 12), at=(fx, -D + 0.06, H / 2), axis="Y", mat="black")
    # fan blades + motor
    cyl(0.05, 0.05, 12, at=(fx, -D + 0.012, H / 2), axis="Y", mat="metal_dark")
    for k in range(3):
        bl = box(R * 0.85, 0.006, R * 0.42, at=(R * 0.45, 0, 0), mat="plastic_dark")
        bl.rot(x=25).rot(y=k * 120 + rnd.uniform(0, 40)).move(fx, -D + 0.035, H / 2)
    grille_round(fx, -D - 0.006, H / 2, R + 0.005, 3 if K.LOD == 0 else 2, "metal_dark")
    # coil fins visible on the back/left side behind a guard
    box(0.004, D - 0.06, H - 0.08, at=(-W / 2 - 0.002, -D / 2, H / 2), mat="grating")
    box(W - 0.06, 0.004, H - 0.08, at=(0, -0.002, H / 2), mat="grating")
    # right-hand service panel + valve cover
    box(0.16, 0.006, H - 0.06, at=(W / 2 - 0.1, -D - 0.003, H / 2), mat=paint, bevel=0.002)
    vc = box(0.012, 0.14, 0.16, at=(W / 2 + 0.006, -D * 0.45, 0.14), mat=paint, bevel=0.003)
    if detail():
        for i in range(5):  # top vent slots
            box(0.012, D - 0.08, 0.004, at=(W / 2 - 0.08 - i * 0.03, -D / 2, H), mat="black")
        for (x, z) in ((W / 2 - 0.05, H - 0.05), (W / 2 - 0.05, 0.05), (W / 2 - 0.15, H - 0.05), (W / 2 - 0.15, 0.05)):
            hexbolt((x, -D - 0.006, z), "-y", 0.005, 0.003)
        # rating plate + glyph sticker (abstract)
        box(0.09, 0.002, 0.05, at=(W / 2 - 0.1, -D - 0.007, H * 0.72), mat="metal_bare")
        box(0.05, 0.002, 0.05, at=(W / 2 - 0.1, -D - 0.007, H * 0.38), mat="metal_painted_yellow")
        box(0.03, 0.0025, 0.006, at=(W / 2 - 0.1, -D - 0.008, H * 0.38), mat="black")
        box(0.006, 0.0025, 0.03, at=(W / 2 - 0.1, -D - 0.008, H * 0.38), mat="black")
        if led_mat:
            led((W / 2 - 0.05, -D - 0.006, H * 0.2), led_mat, 0.005)
        # grime: rust run-off from the bolts, dirt under the grille
        streak(W / 2 - 0.05, H - 0.07, H * 0.5, 0.025, -D - 0.006, seed=seed)
        streak(fx - R * 0.5, H / 2 - R - 0.02, 0.08, 0.1, -D, seed=seed + 1, mat="metal_dark")
        streak(fx + R * 0.3, H / 2 - R - 0.01, 0.07, 0.07, -D, seed=seed + 2)
        streak(-0.1, H - 0.02, H * 0.6, 0.06, -W / 2, facing="-x", seed=seed + 3, mat="metal_dark")
    return Vector((W / 2 + 0.012, -D * 0.45, 0.14))


def ac_unit_stack_wall(seed=4):
    """Three split-AC condensers stacked up a facade on angle brackets, with refrigerant lines, drip hoses and
    power cables into the wall. Pivot wall-base = wall plane at the foot of the lowest bracket."""
    rnd = random.Random(seed)
    units = [(-0.08, 0.0, 0.82, 0.56, "metal_painted_white", "emit_green"), (0.14, 0.86, 0.9, 0.62, "metal_painted", None),
             (-0.02, 1.82, 0.8, 0.55, "paint_glossy_white", "emit_amber")]
    gap = 0.07
    cols = []
    for k, (x, z, W, H, paint, ledm) in enumerate(units):
        D = 0.29 if k != 1 else 0.32
        # angle brackets (pair) from the wall
        arm = D + gap + 0.08
        for sx in (-1, 1):
            bx = x + sx * (W / 2 - 0.12)
            box(0.04, 0.006, 0.38, at=(bx, -0.003, z - 0.33), mat="metal_rusted", base=True)
            box(0.04, arm, 0.04, at=(bx, -arm / 2, z - 0.04), mat="metal_rusted", base=True)
            beam((bx, -0.01, z - 0.31), (bx, -arm + 0.04, z - 0.03), 0.03, 0.006, mat="metal_rusted", up=(1, 0, 0))
            if detail():
                hexbolt((bx, -0.006, z - 0.27), "-y", 0.007, 0.005)
                hexbolt((bx, -0.006, z - 0.08), "-y", 0.007, 0.005)
                streak(-0.01, z - 0.27, 0.12, 0.02, bx + 0.02, facing="+x", seed=k * 3 + sx + 10)
                box(0.06, 0.08, 0.012, at=(bx, -gap - D / 2, z), mat="rubber", base=True)
        m0 = K.part_count()
        out = split_condenser(W, H, D, paint, seed + k, ledm)
        for p in K.parts_since(m0):
            p.move(x, -gap, z + 0.012)
        out = out + Vector((x, -gap, z + 0.012))
        # refrigerant lines: insulated suction line (black foam + tape) + thin liquid line, into the wall
        for j, (r, m) in enumerate(((0.016, "rubber"), (0.008, "metal_bare"))):
            dz = -0.03 * j
            pts = [(out.x, out.y - 0.02 * j, out.z + dz), (out.x + 0.08, out.y - 0.02 * j, out.z + dz), (out.x + 0.1, out.y * 0.5, out.z + dz - 0.12),
                   (out.x + 0.1, -0.01, out.z + dz - 0.2)]
            tube(bend_path(pts, 0.05, 3 if detail() else 1), r, 6, m, "lineset")
        # power cable sagging into the wall
        tube(catenary((out.x, out.y + 0.05, out.z + 0.2), (out.x + 0.18, 0.0, out.z + 0.32), 0.08, K.seg(8, 3)), 0.007, 4, "rubber")
        # drip hose dangling from the base pan
        hx = x - W * 0.3
        tube(bend_path([(hx, -gap - D * 0.5, z + 0.012), (hx, -gap - D * 0.5, z - 0.08), (hx + 0.06, -gap - D * 0.6, z - 0.25 - 0.05 * k), (hx + 0.03, -gap - D * 0.55, z - 0.4 - 0.05 * k)], 0.05, 3 if detail() else 1),
             0.009, 5, "plastic_dark", "drip")
        cols.append(K.collider_box((x, -gap - D / 2, z + H / 2), (W, D + 0.02, H + 0.02)))
    # shared cable bundle running up the wall beside the stack, clipped
    xs = 0.62
    for j, r in enumerate((0.012, 0.009, 0.014)):
        tube([(xs + j * 0.028, -0.02, -0.3), (xs + j * 0.028, -0.02, 2.55)], r, 6, "rubber", "riser")
    if detail():
        for z in (0.2, 0.9, 1.6, 2.3):
            box(0.11, 0.012, 0.025, at=(xs + 0.028, -0.034, z), mat="metal_bare")
            hexbolt((xs - 0.02, -0.04, z), "-y", 0.005, 0.004)
    return {"colliders": cols, "lights": [light((-0.08 + 0.41 - 0.05, -0.37, 0.12), "green", 0.4, 0.05)]}


# ============================================================================================== dishes, antennas
def dish_shell(R, depth, t=0.012, n=24, mat="metal_painted_white", lip=0.015):
    """Closed paraboloid shell opening toward +Z, vertex at the origin."""
    rows = K.seg(7, 3)
    front = [(max(0.001, R * (i / rows)), depth * (i / rows) ** 2) for i in range(rows + 1)]
    back = [(r, z - t) for r, z in reversed(front)]
    prof = front + [(R + lip, depth + lip * 0.3), (R + lip, depth - t)] + back
    p = lathe(prof, n, mat=mat, close_bottom=False, close_top=False, name="dish")
    bmesh.ops.recalc_face_normals(p.bm, faces=p.bm.faces)
    return p


def satellite_dish_wall():
    """Wall-mounted 0.75 m offset-style dish on a J-arm, LNB on its arm, cable into the wall. Pivot back-centre."""
    wall_plate(0, 0, 0.12, 0.26, t=0.012, bolts=True)
    tube(bend_path([(0, -0.012, -0.08), (0, -0.32, -0.08), (0, -0.32, 0.32)], 0.08, 4 if detail() else 2), 0.024, 10, "metal_painted_white", "arm")
    cyl(0.03, 0.08, 10, at=(0, -0.32, 0.22), mat="metal_dark")
    box(0.1, 0.06, 0.12, at=(0, -0.34, 0.33), mat="metal_dark", bevel=0.006)
    e = 22.0
    d = dish_shell(0.36, 0.06, 0.008, K.seg(24, 12))
    d.scale(1.0, 1.08, 1.0)
    d.rot(x=90 - e).move(0, -0.42, 0.4)
    # back mount plate
    box(0.18, 0.03, 0.18, at=(0, -0.385, 0.39), mat="metal_dark", bevel=0.004).rot_about((0, -0.385, 0.39), x=-e)
    # LNB arm from the dish's lower rim to the focus
    fz = 0.4 - 0.3 * math.cos(math.radians(90 - e)) + 0.05
    a0 = Vector((0, -0.44, 0.08))
    f = Vector((0, -0.42 - 0.3 * math.cos(math.radians(e)), 0.4 + 0.3 * math.sin(math.radians(e))))
    beam(tuple(a0), tuple(f + Vector((0, 0.02, -0.06))), 0.02, 0.015, mat="metal_painted_white")
    lnb = cyl(0.025, 0.09, 10, mat="metal_painted_white")
    horn = lathe([(0.02, 0.0), (0.035, 0.03), (0.036, 0.035), (0.001, 0.036)], 10, mat="black")
    horn.move(0, 0, 0.09)
    for p in (lnb, horn):
        p.rot(x=-(90 - e) + 180).move(*f)
    if detail():
        led(tuple(f + Vector((0.026, 0.0, -0.03))), "emit_green", 0.004, axis="+x")
    # coax cable from the LNB down the arm into the wall
    tube(bend_path([tuple(f + Vector((0, 0.03, -0.05))), tuple(a0 + Vector((0.02, 0.0, 0.02))), (0.03, -0.32, 0.25), (0.03, -0.3, -0.06), (0.03, -0.01, -0.12)], 0.05, 3 if detail() else 1), 0.005, 4, "black", "coax")
    if detail():
        for z in (0.0, 0.15):
            ring_at((0.0, -0.32, z), (0, 0, 1), 0.03, 0.003, 8, 3)
    return {"colliders": [K.collider_box((0, -0.35, 0.25), (0.75, 0.7, 0.8))]}


def satellite_dish_roof():
    """1.8 m prime-focus dish on a ballasted non-penetrating roof frame with quadpod feed, back truss, equipment box."""
    S = 1.5
    hs = S / 2
    # ballast frame: channels + trays + concrete blocks + rubber pads
    for sy in (-1, 1):
        box(S, 0.08, 0.1, at=(0, sy * hs, 0.02), mat="metal_dark", base=True, bevel=0.005)
    for sx in (-1, 1):
        box(0.08, S, 0.1, at=(sx * hs, 0, 0.02), mat="metal_dark", base=True, bevel=0.005)
    for sx in (-1, 1):
        for sy in (-1, 1):
            box(0.2, 0.2, 0.02, at=(sx * hs, sy * hs, 0), mat="rubber", base=True)
            box(0.4, 0.2, 0.1, at=(sx * hs * 0.55, sy * (hs - 0.12), 0.12), mat="concrete", base=True, bevel=0.01)
    beam((-hs, 0, 0.07), (hs, 0, 0.07), 0.08, 0.1, mat="metal_dark")
    # mast + braces
    cyl(0.055, 1.2, 12, at=(0, 0, 0.12), mat="metal_painted_white")
    box(0.25, 0.25, 0.02, at=(0, 0, 0.12), mat="metal_dark", base=True)
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        beam((sx * hs * 0.9, sy * hs * 0.9, 0.12), (0, 0, 0.8), 0.035, 0.035, mat="metal_dark")
    # az-el head
    box(0.18, 0.2, 0.16, at=(0, 0, 1.32), mat="metal_dark", base=True, bevel=0.01)
    e = 32.0
    piv = Vector((0, -0.12, 1.5))
    m0 = K.part_count()
    R, dep = 0.9, 0.22
    dish_shell(R, dep, 0.014, K.seg(32, 14))
    # back truss: ring + radial ribs
    t = torus(R * 0.55, 0.015, n_major=K.seg(20, 8), n_minor=4, mat="metal_dark")
    t.move(0, 0, dep * 0.3 - 0.03)
    for k in range(8 if detail() else 4):
        a = k * math.tau / (8 if detail() else 4)
        beam((0.08 * math.cos(a), 0.08 * math.sin(a), -0.03), (R * 0.95 * math.cos(a), R * 0.95 * math.sin(a), dep * 0.9 - 0.02), 0.025, 0.04, mat="metal_dark")
    box(0.3, 0.3, 0.06, at=(0, 0, -0.05), mat="metal_dark", bevel=0.006)
    # quadpod feed
    fz = R * R / (4 * dep * 1.0) * 0.9
    for k in range(4):
        a = k * math.tau / 4 + math.pi / 4
        beam((R * 0.95 * math.cos(a), R * 0.95 * math.sin(a), dep * 0.9), (0.06 * math.cos(a), 0.06 * math.sin(a), fz - 0.1), 0.018, 0.018, mat="metal_painted_white")
    cyl(0.07, 0.16, 12, at=(0, 0, fz - 0.12), mat="metal_painted_white")
    lathe([(0.035, 0.0), (0.075, -0.1), (0.078, -0.105), (0.001, -0.106)], 12, at=(0, 0, fz - 0.12), mat="black")
    box(0.1, 0.06, 0.08, at=(0, 0.08, fz - 0.02), mat="metal_dark", bevel=0.005)
    for p in K.parts_since(m0):
        p.rot(x=90 - e).move(*piv)
    # elevation strut from the head to the dish back
    beam((0, 0.05, 1.35), (0, 0.18, 1.85), 0.04, 0.04, mat="metal_bare")
    cyl(0.03, 0.25, 8, at=(0, 0.1, 1.45), mat="chrome_scratched").rot_about((0, 0.1, 1.45), x=-25)
    # equipment box on the frame + cable up the mast
    box(0.32, 0.2, 0.36, at=(0.35, 0.45, 0.12), mat="metal_painted", base=True, bevel=0.01)
    led((0.43, 0.349, 0.4), "emit_green", 0.006)
    led((0.4, 0.349, 0.4), "emit_cyan", 0.006)
    tube(bend_path([(0.3, 0.45, 0.48), (0.1, 0.1, 0.6), (0.06, 0.0, 1.3), (0.05, 0.05, 1.5)], 0.08, 3 if detail() else 1), 0.008, 5, "black")
    return {"colliders": [K.collider_box((0, 0, 0.11), (S + 0.1, S + 0.1, 0.22)), K.collider_box((0, 0, 0.8), (0.2, 0.2, 1.3)),
                          K.collider_box((0, -0.35, 1.6), (1.9, 0.7, 1.3))]}


def _sector_panel(x, y, z, yaw, h=0.95):
    with K.placed(x=x, y=y, z=z, rz=yaw):
        box(0.26, 0.09, h, at=(0, 0, 0), mat="metal_painted_white", base=True, bevel=0.02, bseg=2)
        box(0.24, 0.002, h - 0.06, at=(0, -0.046, 0.03), mat="paint_glossy_white", base=True)
        cyl(0.03, 0.04, 8, at=(0, 0, h), mat="metal_dark")
        cyl(0.03, 0.04, 8, at=(0, 0, -0.04), mat="metal_dark")
        for zz in (0.15, h - 0.15):
            box(0.06, 0.12, 0.05, at=(0, 0.1, zz), mat="metal_dark")
        # remote radio unit behind the panel
        box(0.22, 0.12, 0.36, at=(0, 0.24, 0.2), mat="metal_dark", base=True, bevel=0.008)
        if detail():
            for i in range(6):
                box(0.004, 0.035, 0.32, at=(-0.09 + i * 0.036, 0.315, 0.38), mat="metal_dark")
        # jumpers looping from the radio to the panel bottom
        tube(bend_path([(0.05, 0.24, 0.2), (0.05, 0.16, 0.05), (0.03, 0.02, -0.06), (0.0, 0.0, -0.04)], 0.05, 2), 0.008, 4, "black")


def antenna_cluster_roof():
    """Ballasted telecom cluster: tripod base with ballast, 4.2 m mast, three sector panels with radios, yagi, small
    dish, omni whip and a red aviation beacon; cable ladder and status-lit equipment box."""
    T = 1.7
    pts = [(T * 0.577 * math.cos(math.radians(90 + k * 120)), T * 0.577 * math.sin(math.radians(90 + k * 120))) for k in range(3)]
    for k in range(3):
        a, b = pts[k], pts[(k + 1) % 3]
        beam((a[0], a[1], 0.06), (b[0], b[1], 0.06), 0.08, 0.1, mat="metal_dark")
        beam((a[0], a[1], 0.08), (0, 0, 1.4), 0.04, 0.04, mat="metal_dark")
        box(0.24, 0.24, 0.02, at=(a[0], a[1], 0), mat="rubber", base=True)
        blk = box(0.4, 0.2, 0.1, at=(0, 0, 0), mat="concrete", base=True, bevel=0.01)
        blk.rot(z=90 + k * 120).move((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, 0.11)
    H = 4.2
    cyl(0.06, H, 12, at=(0, 0, 0.0), mat="metal_bare")
    box(0.3, 0.3, 0.02, at=(0, 0, 0.0), mat="metal_dark", base=True)
    # triangular head frame + sector panels
    zr = 2.75
    for k in range(3):
        a = math.radians(-90 + k * 120)
        beam((0, 0, zr + 0.6), (0.42 * math.cos(a), 0.42 * math.sin(a), zr + 0.6), 0.04, 0.04, mat="metal_dark")
        beam((0, 0, zr + 0.05), (0.42 * math.cos(a), 0.42 * math.sin(a), zr + 0.05), 0.04, 0.04, mat="metal_dark")
        cyl(0.025, 1.0, 8, at=(0.42 * math.cos(a), 0.42 * math.sin(a), zr - 0.1), mat="metal_bare")
        _sector_panel(0.5 * math.cos(a), 0.5 * math.sin(a), zr - 0.12, math.degrees(a) + 90)
    # yagi on a side arm pointing -Y
    zy = 2.05
    beam((0, 0, zy), (0, -0.4, zy), 0.035, 0.035, mat="metal_dark")
    tube([(0, -0.4, zy), (0, -1.25, zy)], 0.012, 6, "metal_bare", "boom")
    for i in range(9 if detail() else 5):
        y = -0.45 - i * 0.8 / (8 if detail() else 4)
        L = 0.42 - i * 0.02
        tube([(-L / 2, y, zy), (L / 2, y, zy)], 0.005, 4, "metal_bare", "element")
    # small dish on the mast
    m0 = K.part_count()
    dish_shell(0.25, 0.05, 0.008, K.seg(18, 10))
    for p in K.parts_since(m0):
        p.rot(x=80).rot(z=-120).move(0.25, 0.15, 1.65)
    beam((0.06, 0.03, 1.65), (0.2, 0.12, 1.65), 0.03, 0.03, mat="metal_dark")
    # omni whip + aviation beacon on the mast top
    cyl(0.02, 0.9, 8, at=(0, 0, H), r2=0.008, mat="paint_glossy_white")
    cyl(0.07, 0.04, 12, at=(0, 0, H), mat="metal_dark")
    bz = H - 0.25
    box(0.06, 0.2, 0.04, at=(0, 0.12, bz), mat="metal_dark")
    lathe([(0.055, 0.0), (0.055, 0.05), (0.042, 0.11), (0.001, 0.125)], 12, at=(0.0, 0.22, bz + 0.02), mat="emit_red")
    cyl(0.06, 0.03, 12, at=(0.0, 0.22, bz - 0.01), mat="metal_dark")
    # cable ladder up the mast with a bundle of feeders
    for j in range(4):
        tube([(0.07 + j * 0.018, -0.05, 0.3), (0.07 + j * 0.018, -0.05, zr - 0.1)], 0.009, 5, "black", "feeder")
    if detail():
        for z in (0.6, 1.2, 1.8, 2.4):
            box(0.1, 0.03, 0.02, at=(0.1, -0.05, z), mat="metal_bare")
    # equipment cabinet at the base
    box(0.5, 0.35, 0.65, at=(-0.55, 0.0, 0.14), mat="metal_painted", base=True, bevel=0.012)
    box(0.52, 0.38, 0.03, at=(-0.55, 0.0, 0.79), mat="metal_dark", base=True, bevel=0.006)
    for k, m in enumerate(("emit_green", "emit_cyan", "emit_green")):
        led((-0.67 + k * 0.03, -0.175, 0.7), m, 0.006)
    box(0.12, 0.004, 0.05, at=(-0.45, -0.177, 0.66), mat="emit_cyan")
    tube(bend_path([(-0.4, 0.0, 0.79), (-0.2, -0.04, 0.85), (0.07, -0.05, 0.6), (0.07, -0.05, 0.3)], 0.1, 3 if detail() else 1), 0.012, 5, "black")
    return {"colliders": [K.collider_box((0, 0, 0.15), (T, T, 0.3)), K.collider_box((0, 0, H / 2), (0.14, 0.14, H)),
                          K.collider_box((-0.55, 0.0, 0.47), (0.5, 0.35, 0.66))],
            "beacon": U((0.0, 0.22, bz + 0.08)), "light": light((0.0, 0.22, bz + 0.08), "red", 6.0, 1.0)}


# ============================================================================================== rooftop water tower
def water_tower_roof(seed=7):
    """NYC-style wooden water tower: staved tank with steel hoops, conical roof with hatch and finial, steel
    tower with X-bracing and grating catwalk + rail, ladders, outlet pipe; magenta LED eave ring and a red beacon."""
    rnd = random.Random(seed)
    Lh = 1.25
    Hs = 2.5
    # steel legs (I-section) on base plates, bracing
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = sx * Lh, sy * Lh
            box(0.3, 0.3, 0.025, at=(x, y, 0), mat="metal_dark", base=True)
            box(0.16, 0.16, 0.06, at=(x, y, 0.025), mat="concrete", base=True)
            box(0.14, 0.02, Hs, at=(x, y - 0.06, 0.085), mat="metal_dark", base=True)
            box(0.14, 0.02, Hs, at=(x, y + 0.06, 0.085), mat="metal_dark", base=True)
            box(0.02, 0.12, Hs, at=(x, y, 0.085), mat="metal_dark", base=True)
    faces = [((-Lh, -Lh), (Lh, -Lh)), ((Lh, -Lh), (Lh, Lh)), ((Lh, Lh), (-Lh, Lh)), ((-Lh, Lh), (-Lh, -Lh))]
    for a, b in faces:
        beam((a[0], a[1], 0.4), (b[0], b[1], Hs - 0.1), 0.05, 0.012, mat="metal_rusted")
        beam((b[0], b[1], 0.4), (a[0], a[1], Hs - 0.1), 0.05, 0.012, mat="metal_rusted")
        beam((a[0], a[1], 0.35), (b[0], b[1], 0.35), 0.1, 0.06, mat="metal_dark")
    # grillage + catwalk
    zt = Hs + 0.085
    for sx in (-1, 0, 1):
        box(0.12, 2 * Lh + 0.3, 0.2, at=(sx * Lh * (1 if sx else 0), 0, zt), mat="metal_dark", base=True)
    for sy in (-1, 1):
        box(2 * Lh + 0.3, 0.12, 0.2, at=(0, sy * Lh, zt), mat="metal_dark", base=True)
    P = 3.7
    box(P, P, 0.04, at=(0, 0, zt + 0.2), mat="grating", base=True)
    for sy in (-1, 1):
        box(P, 0.06, 0.08, at=(0, sy * (P / 2 - 0.03), zt + 0.16), mat="metal_dark", base=True)
        box(0.06, P, 0.08, at=(sy * (P / 2 - 0.03), 0, zt + 0.16), mat="metal_dark", base=True)
    zc = zt + 0.24
    # railing around the catwalk (gap at the ladder, -Y centre)
    rp = P / 2 - 0.04
    posts = [(-rp, -rp), (rp, -rp), (rp, rp), (-rp, rp)]
    for (x, y) in posts + [(0, rp), (rp, 0), (-rp, 0), (-0.4, -rp), (0.4, -rp)]:
        cyl(0.02, 1.05, 6, at=(x, y, zc), mat="metal_painted_yellow")
    for z in (zc + 0.5, zc + 1.05):
        tube([(-0.4, -rp, z), (-rp, -rp, z), (-rp, rp, z), (rp, rp, z), (rp, -rp, z), (0.4, -rp, z)], 0.02, 6, "metal_painted_yellow", "rail")
    # staved tank
    Rt, Ht = 1.55, 2.9
    ns = K.seg(36, 18)
    zb = zc + 0.25
    for sx in (-1, 0, 1):  # timber dunnage under the tank
        box(0.15, 2 * Rt, 0.25, at=(sx * 1.0, 0, zc), mat="wood", base=True, bevel=0.01)
    cyl(Rt - 0.03, 0.06, ns, at=(0, 0, zb), mat="wood")
    sw = 2 * math.pi * Rt / ns
    for k in range(ns):
        a = k * 360.0 / ns
        st = box(sw * 1.02, 0.07, Ht, at=(0, 0, 0), mat="wood", base=True, bevel=0.008 if detail() else 0.0)
        st.displace(lambda co: (co.x, co.y, co.z + (0.0 if co.z < Ht * 0.5 else 0.0)))
        st.scale(1.0 - 0.0, 1, 1)
        st.move(0, -Rt, zb).rot_about((0, 0, zb), z=a + rnd.uniform(-0.4, 0.4))
        if k % 5 == 0 and detail():
            st.move(0, 0, rnd.uniform(-0.01, 0.01))
    # hoops (denser near the bottom where the pressure is highest)
    hz = [0.12, 0.38, 0.66, 0.97, 1.32, 1.72, 2.2, 2.75]
    for z in (hz if detail() else hz[::2]):
        t = torus(Rt + 0.045, 0.012, n_major=K.seg(36, 16), n_minor=3, mat="metal_rusted")
        t.move(0, 0, zb + z)
        if detail():
            box(0.06, 0.05, 0.05, at=(math.cos(math.radians(30 + z * 50)) * (Rt + 0.06), math.sin(math.radians(30 + z * 50)) * (Rt + 0.06), zb + z), mat="metal_rusted").rot_about(
                (math.cos(math.radians(30 + z * 50)) * (Rt + 0.06), math.sin(math.radians(30 + z * 50)) * (Rt + 0.06), zb + z), z=30 + z * 50)
    # dark water stain streaks running down the staves
    if detail():
        for k in range(7):
            a = math.radians(rnd.uniform(0, 360))
            cyl_patch(Rt + 0.038, math.degrees(a), math.degrees(a) + rnd.uniform(2, 4), Ht * rnd.uniform(0.2, 0.5), Ht - 0.02, "soil_dark", at=(0, 0, zb), n=1)
    # conical roof + eave LED ring + hatch + finial + beacon
    zr = zb + Ht
    lathe([(Rt + 0.12, -0.05), (Rt + 0.14, 0.02), (0.25, 0.95), (0.1, 1.05), (0.001, 1.06)], ns, at=(0, 0, zr), mat="metal_dark")
    if detail():
        for k in range(12):
            a = k * math.tau / 12
            beam((math.cos(a) * (Rt + 0.12), math.sin(a) * (Rt + 0.12), zr + 0.03), (math.cos(a) * 0.25, math.sin(a) * 0.25, zr + 0.97), 0.03, 0.02, mat="metal_rusted")
    t = torus(Rt + 0.135, 0.014, n_major=K.seg(48, 20), n_minor=4, mat="emit_strip_magenta")
    t.move(0, 0, zr - 0.03)
    hx = box(0.45, 0.35, 0.12, at=(0, 0, 0), mat="wood", base=True, bevel=0.01)
    hx.rot(x=-33).move(0, -0.95, zr + 0.42)
    cyl(0.04, 0.35, 8, at=(0, 0, zr + 1.04), mat="metal_rusted")
    lathe([(0.001, 0.0), (0.08, 0.04), (0.09, 0.08), (0.06, 0.12), (0.001, 0.13)], 10, at=(0, 0, zr + 1.39), mat="metal_rusted")
    lathe([(0.05, 0.0), (0.05, 0.05), (0.038, 0.1), (0.001, 0.12)], 10, at=(0, 0, zr + 1.52), mat="emit_red")
    # ladder up the tank side (-Y) from the catwalk to the roof
    ly = -Rt - 0.2
    for x in (-0.22, 0.22):
        box(0.05, 0.03, Ht + 0.6, at=(x, ly, zc), mat="metal_dark", base=True)
        for z in (zc + 0.8, zc + 2.2):
            box(0.04, 0.2, 0.04, at=(x, ly + 0.1, z), mat="metal_dark")
    for i in range(int((Ht + 0.4) / 0.3)):
        cyl(0.012, 0.44, 6, at=(-0.22, ly, zc + 0.3 + i * 0.3), axis="X", mat="metal_painted_yellow")
    # access ladder from the roof deck to the catwalk on a leg (-Y side)
    lx = -0.35
    for x in (lx - 0.22, lx + 0.22):
        box(0.05, 0.03, zc + 0.9, at=(x, -P / 2 - 0.05, 0), mat="metal_dark", base=True)
    for i in range(int(zc / 0.3)):
        cyl(0.012, 0.44, 6, at=(lx - 0.22, -P / 2 - 0.05, 0.3 + i * 0.3), axis="X", mat="metal_painted_yellow")
    # outlet pipe + valve, overflow
    tube(bend_path([(0.6, 0.6, zb), (0.6, 0.6, 0.6), (0.6, 1.6, 0.6), (0.6, 1.95, 0.6)], 0.25, 4 if detail() else 2), 0.08, 10, "metal_rusted", "outlet")
    cyl(0.12, 0.16, 12, at=(0.6, 0.6, 1.4), mat="metal_painted_red")
    torus(0.12, 0.012, n_major=10, n_minor=4, mat="metal_painted_red").move(0.75, 0.6, 1.48)
    tube(bend_path([(-0.9, 1.2, zr - 0.15), (-0.9, Rt + 0.25, zr - 0.15), (-0.9, Rt + 0.25, zc + 0.05)], 0.12, 3 if detail() else 1), 0.04, 8, "metal_rusted", "overflow")
    return {"colliders": [K.collider_box((sx * Lh, sy * Lh, zt / 2), (0.2, 0.2, zt)) for sx in (-1, 1) for sy in (-1, 1)] +
            [K.collider_box((0, 0, zt + 0.12), (P, P, 0.24)), {"type": "capsule", "center": U((0, 0, zb + Ht / 2)), "radius": Rt + 0.06, "height": Ht + 0.6, "direction": "Y"}],
            "beacon": U((0, 0, zr + 1.6)), "lights": [light((0, 0, zr + 1.6), "red", 8.0, 1.0), light((0, -Rt - 0.4, zr - 0.2), "magenta", 6.0, 0.8)],
            "deckHeight": round(zc, 3)}


# ============================================================================================== roof clutter pack
def roof_clutter_pack_a(seed=12):
    """~4 x 3 m roof clutter: upblast exhaust fan on a curb, gooseneck intake, rectangular duct with an elbow,
    pipes on sleeper blocks, unistrut H-frame with electrical boxes and conduits, plumbing vent stacks, pads."""
    rnd = random.Random(seed)
    cols = []
    # 1. upblast exhaust fan on a curb (-X, back)
    fx, fy = -1.35, 0.7
    box(0.75, 0.75, 0.3, at=(fx, fy, 0), mat="metal_bare", base=True, bevel=0.01)
    box(0.85, 0.85, 0.05, at=(fx, fy, 0.3), mat="metal_dark", base=True, bevel=0.005)
    lathe([(0.36, 0.35), (0.36, 0.55), (0.3, 0.6), (0.28, 0.85), (0.33, 0.9), (0.001, 0.92)], 20, at=(fx, fy, 0), mat="metal_bare")
    lathe([(0.33, 0.9), (0.42, 0.95), (0.43, 0.99), (0.3, 1.02), (0.001, 1.03)], 20, at=(fx, fy, 0), mat="metal_dark")
    if detail():
        for k in range(12):
            a = k * math.tau / 12
            box(0.02, 0.05, 0.22, at=(fx + math.cos(a) * 0.36, fy + math.sin(a) * 0.36, 0.45), mat="black").rot_about((fx + math.cos(a) * 0.36, fy + math.sin(a) * 0.36, 0.45), z=math.degrees(a))
        streak(0.0, 0.3, 0.2, 0.15, fy - 0.375, seed=1)
    cols.append(K.collider_box((fx, fy, 0.5), (0.85, 0.85, 1.0)))
    # 2. gooseneck intake (rectangular riser with a 180 deg hood)
    gx, gy = -0.3, 0.95
    box(0.5, 0.4, 0.2, at=(gx, gy, 0), mat="metal_dark", base=True, bevel=0.008)
    box(0.36, 0.3, 0.8, at=(gx, gy, 0.2), mat="metal_bare", base=True, bevel=0.006)
    secs = []
    na = K.seg(10, 4)
    for i in range(na + 1):
        a = math.radians(180 - 180 * i / na)
        c = Vector((gx + 0.22 + 0.22 * math.cos(a), gy, 1.0 + 0.22 * math.sin(a)))
        rd = Vector((math.cos(a), 0, math.sin(a)))
        Y = Vector((0, 0.15, 0))
        secs.append([tuple(c - rd * 0.18 - Y), tuple(c + rd * 0.18 - Y), tuple(c + rd * 0.18 + Y), tuple(c - rd * 0.18 + Y)])
    K.loft(secs, mat="metal_bare", cap_start=False, cap_end=False, name="gooseneck")
    if detail():
        for i in (na // 3, 2 * na // 3):
            ring = [Vector(v) for v in secs[i]]
            cc = sum(ring, Vector()) / 4
            K.loft([[tuple(cc + (v - cc) * 1.04 + Vector((0, 0, 0)) - (Vector(secs[i + 1][0]) - Vector(secs[i][0])) * 0.15) for v in ring],
                    [tuple(cc + (v - cc) * 1.04 + (Vector(secs[i + 1][0]) - Vector(secs[i][0])) * 0.15) for v in ring]], mat="metal_dark", name="seam")
    box(0.36, 0.3, 0.3, at=(gx + 0.44, gy, 0.7), mat="metal_bare", base=True, bevel=0.006)
    box(0.34, 0.28, 0.01, at=(gx + 0.44, gy, 0.695), mat="grating", base=True)
    if detail():
        for z in (0.5, 0.8):
            box(0.37, 0.31, 0.02, at=(gx, gy, z), mat="metal_dark", base=True)
    cols.append(K.collider_box((gx + 0.2, gy, 0.6), (0.9, 0.4, 1.2)))
    # 3. rectangular duct out of a box plenum running along X with an elbow down
    dz = 0.55
    box(0.7, 0.55, 0.75, at=(1.4, 0.75, 0), mat="metal_painted", base=True, bevel=0.012)
    box(0.74, 0.59, 0.04, at=(1.4, 0.75, 0.75), mat="metal_dark", base=True, bevel=0.004)
    box(1.1, 0.4, 0.32, at=(0.5, 0.75 - 0.05, dz), mat="metal_bare", base=True, bevel=0.004)
    if detail():
        for x in (0.15, 0.55, 0.9):
            box(0.03, 0.42, 0.34, at=(x, 0.7, dz), mat="metal_dark", base=True)
        for i in range(5):
            box(0.05, 0.004, 0.012, at=(1.25 + i * 0.07, 0.75 - 0.276, 0.55), mat="black")
        led((1.62, 0.474, 0.62), "emit_green", 0.006)
        led((1.59, 0.474, 0.62), "emit_amber", 0.006)
        warning_triangle((1.3, 0.474, 0.35), 0.1)
    # duct support stand
    for x in (0.2, 0.75):
        beam((x, 0.7, 0.0), (x, 0.7, dz), 0.04, 0.04, mat="metal_dark")
        box(0.12, 0.45, 0.03, at=(x, 0.7, dz - 0.03), mat="metal_dark", base=True)
        box(0.2, 0.2, 0.02, at=(x, 0.7, 0), mat="rubber", base=True)
    cols.append(K.collider_box((1.4, 0.75, 0.39), (0.74, 0.59, 0.79)))
    # 4. two pipes on sleeper blocks along the front edge
    for x in (-1.5, -0.3, 0.9):
        box(0.25, 0.5, 0.15, at=(x, -0.95, 0), mat="concrete", base=True, bevel=0.01)
        box(0.06, 0.42, 0.04, at=(x, -0.95, 0.15), mat="metal_dark", base=True)
        if detail():
            for y, r in ((-1.07, 0.06), (-0.85, 0.035)):
                ub = [(x, y + (r + 0.006) * math.cos(math.pi * k / 6), 0.19 + r + (r + 0.006) * math.sin(math.pi * k / 6)) for k in range(7)]
                tube(ub, 0.005, 4, "metal_bare", "ubolt")
    tube([(-1.95, -1.07, 0.25), (1.2, -1.07, 0.25)], 0.06, 12, "metal_painted_yellow", "gas")
    tube(bend_path([(-1.95, -0.85, 0.225), (1.0, -0.85, 0.225), (1.3, -0.85, 0.225), (1.3, -0.85, 0.75), (1.3, 0.25, 0.75), (1.3, 0.47, 0.75)], 0.15, 3 if detail() else 1), 0.035, 8, "metal_bare", "line")
    for x in (-1.95,):
        cyl(0.075, 0.03, 12, at=(x - 0.03, -1.07, 0.25), axis="X", mat="metal_dark")
        cyl(0.05, 0.03, 10, at=(x - 0.03, -0.85, 0.225), axis="X", mat="metal_dark")
    if detail():
        box(0.14, 0.12, 0.14, at=(-0.9, -1.07, 0.18), mat="metal_painted_red", base=True, bevel=0.01)
        torus(0.07, 0.008, n_major=10, n_minor=4, mat="metal_painted_red").move(-0.9, -1.07, 0.42)
        cyl(0.012, 0.1, 6, at=(-0.9, -1.07, 0.31), mat="metal_bare")
    cols.append(K.collider_box((-0.4, -0.95, 0.15), (3.2, 0.5, 0.3)))
    # 5. unistrut H-frame with electrical boxes + conduits into the roof
    hx0 = 0.55
    for x in (hx0 - 0.35, hx0 + 0.35):
        box(0.042, 0.042, 1.3, at=(x, -0.1, 0.0), mat="metal_bare", base=True)
        box(0.25, 0.4, 0.03, at=(x, -0.1, 0.0), mat="rubber", base=True)
        box(0.042, 0.35, 0.042, at=(x, -0.1, 0.02), mat="metal_bare", base=True)
    for z in (0.45, 1.25):
        box(0.8, 0.042, 0.042, at=(hx0, -0.1, z), mat="metal_bare", base=True)
    for k, (x, w, h) in enumerate(((hx0 - 0.18, 0.28, 0.36), (hx0 + 0.18, 0.24, 0.3))):
        box(w, 0.14, h, at=(x, -0.2, 0.6), mat="metal_painted_green" if k else "metal_painted", base=True, bevel=0.008)
        box(w - 0.02, 0.012, h - 0.02, at=(x, -0.276, 0.61), mat="metal_painted_green" if k else "metal_painted", base=True, bevel=0.003)
        led((x + w / 2 - 0.03, -0.282, 0.6 + h - 0.04), ("emit_green", "emit_cyan")[k], 0.006)
        conduit([(x, -0.2, 0.6), (x, -0.2, 0.25), (x - 0.05, -0.35, 0.05), (x - 0.05, -0.35, 0.0)], 0.016, "metal_bare", 0.06)
    if detail():
        warning_triangle((hx0 - 0.18, -0.283, 0.8), 0.08)
    cols.append(K.collider_box((hx0, -0.15, 0.65), (0.8, 0.4, 1.3)))
    # 6. plumbing vent stacks + pitch pocket
    for (x, y, h) in ((-0.9, 0.05, 0.6), (-0.7, 0.2, 0.45)):
        cyl(0.11, 0.08, 12, at=(x, y, 0), mat="rubber")
        cyl(0.045, h, 10, at=(x, y, 0), mat="metal_dark")
        lathe([(0.05, 0.0), (0.06, 0.02), (0.001, 0.05)], 10, at=(x, y, h), mat="metal_dark")
    # roof walkway pads
    for i in range(3):
        box(0.6, 0.6, 0.02, at=(-1.6 + i * 0.65, -0.2, 0), mat="rubber", base=True, bevel=0.003)
    return {"colliders": cols}


ASSETS.update({
    "AC_Unit_Stack_Wall": dict(fn=ac_unit_stack_wall, cat="dressing", zones=["plaza", "rooftops", "metro"], pivot="wall-base",
                               notes="Classic facade clutter: three split-AC condensers (0.8-0.9 m) stacked up a wall on rusty angle brackets, ~1.1 x 2.8 "
                                     "(+0.4 hoses below) x 0.5. Fan grilles, coil guards, service panels, refrigerant line sets and power cables into the "
                                     "wall, dangling drip hoses, cable riser at the side, green/amber status LEDs, rust run-off. Pivot wall-base = wall "
                                     "plane at the foot of the lowest bracket (hoses hang 0.4 m below it). Units face Unity +Z."),
    "Satellite_Dish_Wall": dict(fn=satellite_dish_wall, cat="dressing", zones=["plaza", "rooftops", "metro"], pivot=_W,
                                notes="0.75 m dish on a white J-arm, elevation ~22 deg facing Unity +Z, LNB on its arm with a green LED, coax down into "
                                      "the wall. Pivot back-centre (wall plate). ~0.75 x 0.9 x 0.75."),
    "Satellite_Dish_Roof": dict(fn=satellite_dish_roof, cat="dressing", zones=["rooftops", "plaza"],
                                notes="1.8 m prime-focus dish on a ballasted non-penetrating frame (1.6 x 1.6): concrete blocks, braced mast, az-el head, "
                                      "back truss, quadpod feed, equipment box with status LEDs. Faces Unity +Z at 32 deg. Base-centre."),
    "Antenna_Cluster_Roof": dict(fn=antenna_cluster_roof, cat="dressing", zones=["rooftops", "plaza"],
                                 notes="Telecom cluster on a ballasted tripod (1.7 m): 4.2 m mast, 3 sector panels with radios, yagi (Unity +Z), small "
                                       "dish, omni whip, feeder ladder, base cabinet with status LEDs, red aviation beacon (emit_red) at 'beacon'. "
                                       "~1.9 x 5.1 x 2.3. Base-centre."),
    "Water_Tower_Roof": dict(fn=water_tower_roof, cat="dressing", zones=["rooftops", "plaza"], lods=3,
                             notes="Wooden-stave rooftop water tower (tank d 3.2, 2.9 tall) with steel hoops, conical roof, hatch and finial, on a "
                                   "2.5 m braced steel tower with a 3.7 m grating catwalk + yellow rail (deck at 'deckHeight'). Ladders on Unity +Z, "
                                   "outlet pipe with red valve, overflow. Magenta LED eave ring (emit_strip_magenta) and red beacon (emit_red, "
                                   "'beacon'). ~3.9 x 7.4 x 4.3. Base-centre; leg/deck/tank colliders."),
    "Roof_Clutter_Pack_A": dict(fn=roof_clutter_pack_a, cat="dressing", zones=["rooftops", "plaza"],
                                notes="Pre-composed roof clutter ~4.2 x 1.3 x 2.6: upblast exhaust fan on a curb, gooseneck intake, plenum box with a "
                                      "rectangular duct on stands, yellow gas line + process pipe on sleeper blocks with a red valve, unistrut H-frame "
                                      "with two electrical boxes (status LEDs) and conduits, vent stacks, walkway pads. Base-centre; several box colliders."),
})
