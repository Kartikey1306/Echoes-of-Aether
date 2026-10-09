"""Shop interiors seen through the shop windows: eight small 3D rooms modelled procedurally in Blender and rendered with
Cycles from straight in front of the window (2:1 frame = the window opening), packed into the emissive atlas
emit_st_interiors (st_layout.INTERIOR_RECTS). The storefront modules put this image on a back card 0.4 m behind the
glass, with modelled counters / shelf fronts / cabinets in between for real parallax.

  Blender -b --factory-startup --python st_interiors.py -- [--samples 96] [names...]
"""
import json
import math
import os
import random
import sys

import bpy
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import stpaths  # noqa: E402

sys.path.insert(1, stpaths.ENV)
import pngio  # noqa: E402
import st_layout as L  # noqa: E402

W_ROOM, D_ROOM, H_ROOM = 6.0, 4.2, 3.0


def lin(h):
    h = h.lstrip("#")
    c = [int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


class Scene:
    """Geometry accumulator: one mesh per material (fast for hundreds of product boxes)."""

    def __init__(self, seed):
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.parts = {}
        self.mats = {}
        self.r = random.Random(seed)

    def mat(self, name, col, rough=0.5, metal=0.0, emit=None, strength=0.0, noise=0.0, alpha=1.0):
        if name in self.mats:
            return name
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        nt = m.node_tree
        b = nt.nodes["Principled BSDF"]
        b.inputs["Base Color"].default_value = (*col, 1)
        b.inputs["Roughness"].default_value = rough
        b.inputs["Metallic"].default_value = metal
        if emit is not None:
            b.inputs["Emission Color"].default_value = (*emit, 1)
            b.inputs["Emission Strength"].default_value = strength
        if noise > 0:
            tx = nt.nodes.new("ShaderNodeTexNoise")
            tx.inputs["Scale"].default_value = 6.0
            tx.inputs["Detail"].default_value = 8.0
            mix = nt.nodes.new("ShaderNodeMix")
            mix.data_type = "RGBA"
            mix.blend_type = "MULTIPLY"
            mix.inputs["Factor"].default_value = noise
            mix.inputs["A"].default_value = (*col, 1)
            nt.links.new(tx.outputs["Color"], mix.inputs["B"])
            nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
        if alpha < 1:
            b.inputs["Alpha"].default_value = alpha
        self.mats[name] = m
        return name

    def box(self, mat, x0, y0, z0, x1, y1, z1):
        v, f = self.parts.setdefault(mat, ([], []))
        o = len(v)
        v += [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0), (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
        f += [(o, o + 3, o + 2, o + 1), (o + 4, o + 5, o + 6, o + 7), (o, o + 1, o + 5, o + 4), (o + 1, o + 2, o + 6, o + 5),
              (o + 2, o + 3, o + 7, o + 6), (o + 3, o, o + 4, o + 7)]

    def boxc(self, mat, cx, cy, cz, sx, sy, sz):
        self.box(mat, cx - sx / 2, cy - sy / 2, cz - sz / 2, cx + sx / 2, cy + sy / 2, cz + sz / 2)

    def cyl(self, mat, cx, cy, z0, r, h, n=16):
        v, f = self.parts.setdefault(mat, ([], []))
        o = len(v)
        for i in range(n):
            a = i / n * math.tau
            v.append((cx + r * math.cos(a), cy + r * math.sin(a), z0))
            v.append((cx + r * math.cos(a), cy + r * math.sin(a), z0 + h))
        for i in range(n):
            j = (i + 1) % n
            f.append((o + 2 * i, o + 2 * j, o + 2 * j + 1, o + 2 * i + 1))
        f.append(tuple(o + 2 * i for i in reversed(range(n))))
        f.append(tuple(o + 2 * i + 1 for i in range(n)))

    def room(self, wall, floor, ceil, w=W_ROOM, d=D_ROOM, h=H_ROOM):
        self.box(floor, -w / 2, 0, -0.1, w / 2, d, 0)
        self.box(ceil, -w / 2, 0, h, w / 2, d, h + 0.1)
        self.box(wall, -w / 2 - 0.1, 0, 0, -w / 2, d, h)
        self.box(wall, w / 2, 0, 0, w / 2 + 0.1, d, h)
        self.box(wall, -w / 2, d, 0, w / 2, d + 0.1, h)

    def light_panel(self, cx, cy, sx, sy, col, strength, z=H_ROOM - 0.02):
        name = self.mat(f"lp_{col}_{strength}", (0.9, 0.9, 0.9), emit=col, strength=strength)
        self.boxc(name, cx, cy, z, sx, sy, 0.03)

    def area(self, cx, cy, cz, size, col, energy):
        ld = bpy.data.lights.new("a", "AREA")
        ld.size = size
        ld.color = col
        ld.energy = energy
        ob = bpy.data.objects.new("a", ld)
        ob.location = (cx, cy, cz)
        bpy.context.scene.collection.objects.link(ob)

    def point(self, cx, cy, cz, col, energy, r=0.1):
        ld = bpy.data.lights.new("p", "POINT")
        ld.color = col
        ld.energy = energy
        ld.shadow_soft_size = r
        ob = bpy.data.objects.new("p", ld)
        ob.location = (cx, cy, cz)
        bpy.context.scene.collection.objects.link(ob)

    def finish(self):
        for mat, (v, f) in self.parts.items():
            me = bpy.data.meshes.new(mat)
            me.from_pydata(v, [], f)
            me.update()
            me.materials.append(self.mats[mat])
            ob = bpy.data.objects.new(mat, me)
            bpy.context.scene.collection.objects.link(ob)

    # ------------------------------------------------------------------ furniture
    def shelves(self, x0, x1, y, depth, z0, z1, rows, prod_mats, frame, fill=0.85, kind="box", facing=-1):
        """Shelving run along X at depth y (front edge), products facing the window."""
        for k in range(rows + 1):
            z = z0 + (z1 - z0) * k / rows
            self.box(frame, x0, y, z - 0.02, x1, y + depth, z)
        self.box(frame, x0, y + depth - 0.02, z0, x1, y + depth, z1)
        for k in range(rows):
            z = z0 + (z1 - z0) * k / rows
            hmax = (z1 - z0) / rows - 0.06
            x = x0 + 0.02
            while x < x1 - 0.06:
                pw = self.r.uniform(0.05, 0.16) if kind == "box" else self.r.uniform(0.06, 0.09)
                ph = self.r.uniform(0.35, 0.95) * hmax
                if self.r.random() < fill:
                    m = self.r.choice(prod_mats)
                    if kind == "box":
                        self.box(m, x, y + 0.03, z, x + pw * 0.92, y + depth * 0.8, z + ph)
                    else:
                        self.cyl(m, x + pw / 2, y + depth * 0.4, z, pw * 0.42, ph, 8)
                x += pw


def products(s, palette, n=10, emit=0.0):
    out = []
    for i in range(n):
        c = lin(s.r.choice(palette))
        c = tuple(min(1, x * s.r.uniform(0.7, 1.15)) for x in c)
        out.append(s.mat(f"prod{i}_{palette[0]}", c, rough=s.r.uniform(0.2, 0.6), emit=c if emit else None, strength=emit))
    return out


# ============================================================================================== rooms
def noodle(s):
    wall = s.mat("wall", lin("#5a4636"), 0.7, noise=0.3)
    s.room(wall, s.mat("floor", lin("#2a2420"), 0.35, noise=0.4), s.mat("ceil", lin("#2a2420"), 0.8))
    steel = s.mat("steel", lin("#9aa0a4"), 0.3, 0.9)
    wood = s.mat("wood", lin("#6a4426"), 0.5, noise=0.4)
    # counter along the window, stools, back kitchen line with pots and steam hood
    s.box(wood, -2.8, 0.3, 0, 2.8, 0.9, 1.05)
    s.box(wood, -2.9, 0.25, 1.05, 2.9, 0.95, 1.1)
    for i in range(6):
        x = -2.4 + i * 0.95
        s.cyl(s.mat("stool", lin("#8a1c18"), 0.4), x, 0.15, 0.7, 0.18, 0.06)
        s.cyl(steel, x, 0.15, 0, 0.03, 0.7, 8)
        for k in range(s.r.randint(0, 2)):
            s.cyl(s.mat("bowl", lin("#e8e0d0"), 0.3), x + s.r.uniform(-0.25, 0.25), 0.6, 1.1, 0.09, 0.07, 12)
    s.box(steel, -2.9, 3.2, 0, 2.9, 3.9, 0.95)
    for i in range(5):
        s.cyl(steel, -2.2 + i * 1.1, 3.55, 0.95, 0.22, 0.35, 16)
    s.box(steel, -2.9, 3.3, 2.0, 2.9, 4.2, 2.6)
    s.light_panel(0, 3.8, 5.5, 0.2, lin("#ffd9a8"), 6, z=1.98)
    # menu boards (warm lightboxes) and hanging lanterns
    for i in range(4):
        s.boxc(s.mat(f"menu{i}", lin("#f4e0b8"), 0.4, emit=lin(["#ffe6b8", "#ffd090", "#fff0d0", "#ffc070"][i]), strength=3), -2.25 + i * 1.5, 4.15, 2.75, 1.2, 0.04, 0.4)
    for i in range(3):
        s.cyl(s.mat("lantern", lin("#d02a18"), 0.5, emit=lin("#ff4a20"), strength=8), -1.8 + i * 1.8, 1.8, 2.2, 0.18, 0.4, 16)
    s.area(0, 2.0, 2.9, 3.0, lin("#ffcc90"), 900)
    s.point(0, 3.6, 1.6, lin("#ff9a50"), 120)


def pharmacy(s):
    wall = s.mat("wall", lin("#b8c0bc"), 0.6)
    s.room(wall, s.mat("floor", lin("#8a9490"), 0.25, noise=0.15), s.mat("ceil", lin("#c8ccca"), 0.8))
    frame = s.mat("shelf", lin("#f4f6f6"), 0.4)
    prods = products(s, ["#e8f0f4", "#3dbf6a", "#2a7ad0", "#f0f0f0", "#e04a3a", "#f4c03a", "#9ad0e8", "#ffffff"], 12)
    s.shelves(-2.9, -0.4, 3.75, 0.4, 0.2, 2.4, 6, prods, frame)
    s.shelves(0.4, 2.9, 3.75, 0.4, 0.2, 2.4, 6, prods, frame)
    s.shelves(-2.0, 2.0, 1.6, 0.5, 0.1, 1.4, 3, prods, frame)
    s.box(s.mat("counter", lin("#2a8a5a"), 0.35), -0.6, 3.0, 0, 0.6, 3.5, 1.05)
    s.boxc(s.mat("cross", lin("#20ff80"), 0.3, emit=lin("#3dff90"), strength=6), 0, 4.15, 2.65, 0.6, 0.04, 0.6)
    for x in (-2, 0, 2):
        for y in (1.0, 2.6):
            s.light_panel(x, y, 1.2, 0.6, lin("#f0f6ff"), 2.5)
    s.area(0, 2, 2.9, 4, lin("#f4f8ff"), 260)


def clinic(s):
    wall = s.mat("wall", lin("#1c2a32"), 0.4)
    s.room(wall, s.mat("floor", lin("#2a3a40"), 0.15, noise=0.2), s.mat("ceil", lin("#141c22"), 0.6))
    white = s.mat("white", lin("#d8e4e8"), 0.25)
    steel = s.mat("steel", lin("#8a969c"), 0.25, 0.9)
    # surgical recliner, overhead robot arm, wall screens, privacy band handled by the glass
    s.box(white, -0.9, 2.0, 0.5, 0.9, 2.7, 0.75)
    s.box(white, 0.6, 2.0, 0.75, 1.0, 2.7, 1.45)
    s.cyl(steel, 0, 2.35, 0, 0.12, 0.5, 12)
    s.cyl(steel, -1.4, 2.3, 1.2, 0.08, 1.8, 10)
    s.box(steel, -1.45, 2.25, 2.85, 0.2, 2.4, 2.95)
    s.box(steel, 0.1, 2.2, 1.9, 0.25, 2.45, 2.9)
    s.cyl(s.mat("tool", lin("#00e5ff"), 0.2, emit=lin("#00e5ff"), strength=10), 0.18, 2.32, 1.75, 0.05, 0.15, 10)
    for i in range(3):
        s.boxc(s.mat(f"scr{i}", lin("#062028"), 0.2, emit=lin(["#00b8d8", "#20e0ff", "#3d7bff"][i]), strength=4), -2.0 + i * 2.0, 4.15, 1.8, 1.3, 0.04, 0.8)
    for x in (-2.0, 2.0):
        s.shelves(x - 0.7, x + 0.7, 3.6, 0.45, 0.2, 1.4, 3, products(s, ["#c0c8cc", "#7a8a90", "#00a8c8"], 5), steel, fill=0.6)
    s.light_panel(0, 2.3, 2.0, 0.4, lin("#c8f4ff"), 10)
    for x in (-2.95, 2.9):
        s.box(s.mat("strip", lin("#00e5ff"), 0.2, emit=lin("#00e5ff"), strength=8), x, 0.2, 0.02, x + 0.05, 4.2, 0.06)
    s.light_panel(0, 1.0, 3.0, 0.3, lin("#f4fbff"), 6)
    s.area(0, 2.2, 2.9, 2.0, lin("#a8ecff"), 700)


def pawn(s):
    wall = s.mat("wall", lin("#3a3a32"), 0.7, noise=0.4)
    s.room(wall, s.mat("floor", lin("#2a2824"), 0.5, noise=0.5), s.mat("ceil", lin("#222220"), 0.8))
    frame = s.mat("rack", lin("#5a5a58"), 0.5, 0.6)
    prods = products(s, ["#1a1a1a", "#3a3a3a", "#8a8a8a", "#c0b080", "#2a2a40", "#602020"], 8)
    s.shelves(-2.9, 2.9, 3.7, 0.45, 0.1, 2.7, 6, prods, frame, fill=0.9)
    # screens (TVs / monitors) stacked and lit
    for i in range(14):
        x, z = s.r.uniform(-2.6, 2.6), s.r.uniform(0.3, 2.4)
        w = s.r.uniform(0.3, 0.7)
        c = lin(s.r.choice(["#3d7bff", "#00e5ff", "#ff2bd6", "#ffe14d", "#40ff90", "#ffffff"]))
        s.boxc(s.mat(f"tv{i}", (0.02, 0.02, 0.02), 0.2, emit=c, strength=s.r.uniform(1.5, 4)), x, 3.62, z, w, 0.06, w * 0.62)
    # glass display counter
    s.box(s.mat("case", lin("#101010"), 0.3), -2.5, 1.2, 0, 2.5, 1.7, 0.9)
    for i in range(20):
        s.boxc(s.r.choice(prods), s.r.uniform(-2.3, 2.3), 1.45, 0.95, 0.12, 0.12, 0.08)
    for i in range(6):
        s.cyl(s.mat("cable", lin("#0a0a0a"), 0.6), s.r.uniform(-2.8, 2.8), s.r.uniform(1, 3.5), 2.2, 0.015, 0.8, 6)
    s.light_panel(-1.5, 2.0, 1.2, 0.15, lin("#fff0c0"), 10)
    s.light_panel(1.5, 2.6, 1.2, 0.15, lin("#fff0c0"), 10)
    s.area(0, 2, 2.9, 3, lin("#ffe8b0"), 450)


def capsule(s):
    wall = s.mat("wall", lin("#8a929a"), 0.4)
    s.room(wall, s.mat("floor", lin("#3a4048"), 0.2, noise=0.2), s.mat("ceil", lin("#7a828a"), 0.6))
    shell = s.mat("shell", lin("#b8c0c8"), 0.3)
    glow = s.mat("cap_glow", lin("#c8e0ff"), 0.3, emit=lin("#a8ccff"), strength=4)
    glow2 = s.mat("cap_glow2", lin("#ffd0a0"), 0.3, emit=lin("#ffc890"), strength=3)
    # two walls of capsules (2 high) receding to the back, a central aisle and a reception desk
    for side in (-1, 1):
        for i in range(4):
            y = 1.2 + i * 0.75
            for k in range(2):
                z = 0.1 + k * 1.15
                x0 = side * 1.0
                x1 = side * 2.9
                s.box(shell, min(x0, x1), y, z, max(x0, x1), y + 0.7, z + 1.05)
                if s.r.random() < 0.7:
                    gx = x0 + side * 0.02
                    s.box(s.r.choice([glow, glow, glow2]), min(gx, gx + side * 0.02), y + 0.12, z + 0.12, max(gx, gx + side * 0.02), y + 0.58, z + 0.92)
    s.box(s.mat("desk", lin("#3a4a6a"), 0.3), -0.9, 0.6, 0, 0.9, 1.0, 1.05)
    s.boxc(s.mat("deskglow", lin("#7fb8ff"), 0.3, emit=lin("#7fb8ff"), strength=6), 0, 0.58, 0.9, 1.7, 0.02, 0.05)
    for y in (1.0, 2.0, 3.0, 4.0):
        s.light_panel(0, y, 1.6, 0.25, lin("#e8f0ff"), 2.5)
    s.area(0, 2, 2.9, 2.5, lin("#e0ecff"), 110)


def arcade(s):
    wall = s.mat("wall", lin("#14101c"), 0.6)
    s.room(wall, s.mat("floor", lin("#1a1420"), 0.3, noise=0.5), s.mat("ceil", lin("#100c14"), 0.8))
    body = s.mat("cab", lin("#141418"), 0.4)
    for row in range(2):
        y = 1.4 + row * 1.6
        for i in range(6):
            x = -2.5 + i * 1.0
            s.box(body, x - 0.38, y, 0, x + 0.38, y + 0.8, 1.85)
            c = lin(s.r.choice(["#ff2bd6", "#00e5ff", "#ffe14d", "#9b5cff", "#ff4f9a", "#3d7bff"]))
            s.box(s.mat(f"screen{row}{i}", (0.02, 0.02, 0.02), 0.2, emit=c, strength=s.r.uniform(3, 6)), x - 0.3, y - 0.02, 1.05, x + 0.3, y, 1.5)
            s.box(s.mat(f"marq{row}{i}", c, 0.3, emit=c, strength=5), x - 0.36, y - 0.02, 1.62, x + 0.36, y, 1.8)
    for k in range(3):
        c = lin(["#ff2bd6", "#9b5cff", "#00e5ff"][k])
        s.box(s.mat(f"neon{k}", c, 0.3, emit=c, strength=12), -3.0, 0.5 + k * 1.3, 2.9, 3.0, 0.56 + k * 1.3, 2.95)
    s.area(0, 2.5, 2.9, 3, lin("#c080ff"), 220)


def kitchen_dark(s):
    wall = s.mat("wall", lin("#30302c"), 0.6, noise=0.4)
    s.room(wall, s.mat("floor", lin("#1a1a18"), 0.4), s.mat("ceil", lin("#1a1a1a"), 0.8))
    steel = s.mat("steel", lin("#7a8084"), 0.35, 0.9)
    s.box(steel, -2.8, 2.6, 0, 2.8, 3.4, 0.9)
    for i in range(6):
        s.boxc(s.mat("crate", lin("#3a3024"), 0.7), s.r.uniform(-2.5, 2.5), s.r.uniform(1.0, 2.2), 0.25, 0.5, 0.4, 0.5)
    s.light_panel(1.5, 3.0, 0.8, 0.12, lin("#d0e8d0"), 5)
    s.area(1.5, 3.0, 2.8, 1.0, lin("#c8e0c8"), 120)


def storeroom(s):
    wall = s.mat("wall", lin("#3a3630"), 0.7, noise=0.5)
    s.room(wall, s.mat("floor", lin("#22201c"), 0.5), s.mat("ceil", lin("#1a1816"), 0.8))
    prods = products(s, ["#6a5038", "#5a4030", "#7a6048", "#3a3a3a"], 6)
    frame = s.mat("rack", lin("#4a4a48"), 0.5, 0.6)
    s.shelves(-2.9, 2.9, 3.6, 0.55, 0.1, 2.6, 4, prods, frame, fill=0.95)
    for i in range(10):
        x, y = s.r.uniform(-2.6, 2.6), s.r.uniform(0.8, 3.0)
        h = s.r.uniform(0.3, 1.2)
        s.box(s.r.choice(prods), x - 0.3, y - 0.25, 0, x + 0.3, y + 0.25, h)
    s.point(0.5, 2.0, 2.7, lin("#ffd8a0"), 60)


ROOMS = {"noodle": noodle, "pharmacy": pharmacy, "clinic": clinic, "pawn": pawn, "capsule": capsule, "arcade": arcade,
         "kitchen_dark": kitchen_dark, "storeroom": storeroom}


def render(name, samples):
    s = Scene(sum(map(ord, name)) * 13)
    ROOMS[name](s)
    s.finish()
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    try:
        prefs.compute_device_type = "METAL"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        sc.cycles.device = "GPU"
    except Exception:
        sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, sc.render.resolution_y = 1024, 512
    sc.view_settings.view_transform = "Standard"
    sc.view_settings.exposure = 0.0
    sc.world = bpy.data.worlds.new("w")
    sc.world.color = (0.0, 0.0, 0.0)
    # camera straight in front of the window opening (y = 0 plane), frame = 6 m x 3 m
    cam = bpy.data.cameras.new("cam")
    cam.sensor_fit = "HORIZONTAL"
    cam.sensor_width = 36
    d = 3.2
    cam.lens = 18.0 / (W_ROOM / 2 / d)
    cam.clip_start = 0.1
    ob = bpy.data.objects.new("cam", cam)
    ob.location = (0, -d, H_ROOM / 2)
    ob.rotation_euler = (math.radians(90), 0, 0)
    sc.collection.objects.link(ob)
    sc.camera = ob
    path = os.path.join(stpaths.OUT, f"interior_{name}.png")
    sc.render.filepath = path
    sc.render.image_settings.file_format = "PNG"
    bpy.ops.render.render(write_still=True)
    img = bpy.data.images.load(path)
    a = np.array(img.pixels[:], np.float32).reshape(512, 1024, 4)[:, :, :3]   # bottom row first, sRGB-encoded values
    return a


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    samples = 96
    if "--samples" in argv:
        i = argv.index("--samples")
        samples = int(argv[i + 1])
        del argv[i:i + 2]
    names = argv or list(ROOMS)
    atlas_path = os.path.join(stpaths.OUT, "interiors_atlas.npy")
    atlas = np.load(atlas_path) if os.path.exists(atlas_path) else np.zeros((L.INTERIORS_H, L.INTERIORS_W, 3), np.float32)
    for n in names:
        a = render(n, samples)
        x, y, w, h = L.INTERIOR_RECTS[n]
        atlas[y:y + h, x:x + w] = a
        print("[interior]", n)
    np.save(atlas_path, atlas)
    emi = np.clip(atlas, 0, 1)                                      # already sRGB-encoded (Standard view transform)
    lin_e = pngio.srgb_to_linear(emi)
    out = os.path.join(stpaths.TEXTURES, "emit_st_interiors")
    os.makedirs(out, exist_ok=True)
    pngio.write_png(os.path.join(out, "emit_st_interiors_Emission.png"), pngio.to_u8(emi[::-1]))
    pngio.write_png(os.path.join(out, "emit_st_interiors_BaseColor.png"), pngio.to_u8(pngio.linear_to_srgb(lin_e * 0.25)[::-1]))
    pngio.write_png(os.path.join(stpaths.PREVIEWS, "interiors_atlas.png"), pngio.to_u8(emi[::-1]))
    st = os.path.join(stpaths.OUT, "materials_baked.json")
    state = json.load(open(st)) if os.path.exists(st) else {}
    state["emit_st_interiors"] = {"name": "emit_st_interiors", "res": 2048, "textures": {
        "BaseColor": "Textures/emit_st_interiors/emit_st_interiors_BaseColor.png",
        "Emission": "Textures/emit_st_interiors/emit_st_interiors_Emission.png"}}
    json.dump(state, open(st, "w"), indent=1)


main()
