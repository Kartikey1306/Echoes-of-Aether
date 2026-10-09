"""Speaker portraits (512 x 512 PNG) for the dialogue panel / HUD (square boxes, scale-and-crop).

  Blender -b --factory-startup --python portraits.py -- [ids...] [--size 512]

Three-quarter bust, eyes ~40 % from the top, soft neutral key + strong neon rims (magenta / cyan / acid yellow),
dark backdrop with out-of-focus neon glyph bokeh tinted per character (cyberpunk direction). Characters are the game's MPFB models posed with a frame of their talk/idle
clip; BOLT and the Guardian are the game's robot models. Maren and Nia are drawn as Aether echoes.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

import artkit as A  # noqa: E402
import cyberkit as C  # noqa: E402

OUT = os.path.join(A.RES_ART, "Portraits")

# id: (tint of backdrop/rim, rim2, turn (deg, + = character turns to camera-left), clip, frame, shapes, extra)
AMBER = A.hexlin("#ffb02e")
TEAL = (0.02, 0.42, 0.55)
BLUE = (0.06, 0.25, 0.85)
# cool teal/blue backdrops, neon rims as accents (cyan / magenta / amber), never a magenta wash
CFG = {
    "kael": dict(tint=TEAL, rim2=AMBER, rim=C.NCYAN, turn=-26, clip="idle", frame=40, shapes={"x_browsDown": 0.12}, head_up=4),
    "lyra": dict(tint=BLUE, rim2=AMBER, rim=C.NCYAN, turn=22, clip="idle", frame=40, frame_h=0.46, head_up=3, shapes={"x_smile": 0.18, "x_browsUp": 0.1}),
    "oren": dict(tint=TEAL, rim2=AMBER, turn=-24, clip="talk", frame=70, shapes={"x_smile": 0.1, "x_squint": 0.2}),
    "mira": dict(tint=BLUE, rim2=C.MAGENTA, rim=C.NCYAN, turn=24, clip="talk", frame=10, shapes={"x_smile": 0.3}),
    "tomas": dict(tint=TEAL, rim2=C.YELLOW, turn=-18, clip="talk", frame=35, shapes={"x_browsDown": 0.15}, fill=4.0, head_up=6),
    "nia": dict(tint=C.NCYAN, rim2=A.VIOLET, turn=14, clip="idle", frame=60, shapes={"x_browsUp": 0.25}, head_up=10),
    "maren": dict(tint=(0.25, 0.3, 1.0), rim2=C.NCYAN, turn=-24, clip="talk", frame=80, shapes={"x_smile": 0.08}),
    "bolt": dict(tint=TEAL, rim2=AMBER, turn=-30, robot=True),
    "guardian": dict(tint=BLUE, rim2=(1.0, 0.25, 0.2), turn=24, robot=True),
}


def bokeh(eye, d, tint, rim2, scale=1.0, seed=1):
    """Out-of-focus neon behind the subject: glyph signs and light points 3-7 m back (f/1.8 turns them to bokeh)."""
    import random
    rr = random.Random(seed)
    up = Vector((0, 0, 1))
    side = d.cross(up).normalized()
    cols = [tint, rim2, C.YELLOW, tint]
    for i in range(7):
        p = eye - d * rr.uniform(3.0, 6.5) * scale + side * rr.uniform(-2.2, 2.2) * scale + up * rr.uniform(-1.2, 1.4) * scale
        C.glyph_sign(p, math.degrees(math.atan2(d.x, -d.y)), n=rr.randint(2, 4), height=rr.uniform(0.25, 0.5) * scale,
                     color=rr.choice(cols), strength=rr.uniform(5, 9), seed=seed * 10 + i, vertical=rr.random() < 0.5, backing=False, frame=False)
    m = [C.neon_mat(c, 6.0) for c in cols]
    for i in range(26):
        p = eye - d * rr.uniform(3.0, 7.0) * scale + side * rr.uniform(-2.6, 2.6) * scale + up * rr.uniform(-1.5, 1.6) * scale
        bpy.ops.mesh.primitive_uv_sphere_add(segments=12, ring_count=8, radius=rr.uniform(0.02, 0.05) * scale, location=p)
        bpy.context.active_object.data.materials.append(rr.choice(m))


def backdrop(tint, at, normal_to):
    """Large plane behind the subject: dark radial gradient, faint tint."""
    me = bpy.data.meshes.new("Backdrop")
    s = 14.0
    me.from_pydata([(-s, 0, -s), (s, 0, -s), (s, 0, s), (-s, 0, s)], [], [(0, 1, 2, 3)])
    ob = bpy.data.objects.new("Backdrop", me)
    A.link(ob)
    ob.location = at
    d = (Vector(normal_to) - Vector(at))
    d.z = 0
    ob.rotation_euler = (0, 0, math.atan2(d.x, -d.y) + math.pi)
    m = bpy.data.materials.new("Backdrop")
    T = A.NT(m)
    tc = T.n("ShaderNodeTexCoord")
    sep = T.n("ShaderNodeSeparateXYZ")
    T.L(tc.outputs["Object"], sep.inputs[0])
    # radial falloff around a point slightly above the head
    dx = T.math("SUBTRACT", sep.outputs[0], 0.35)
    dz = T.math("SUBTRACT", sep.outputs[2], 0.25)
    r = T.math("SQRT", T.math("ADD", T.math("MULTIPLY", dx, dx), T.math("MULTIPLY", dz, dz)))
    f = T.maprange(r, 0.0, 6.0, 1.0, 0.0, smooth=True)
    base = (0.006, 0.008, 0.011)
    col = T.mix(base, tuple(min(1, c * 0.05 + b) for c, b in zip(tint, base)), f)
    # faint vertical gradient (darker at the bottom)
    g = T.maprange(sep.outputs[2], -1.2, 0.8, 0.55, 1.0)
    col = T.mix(col, (0, 0, 0), T.math("SUBTRACT", 1.0, g))
    em = T.n("ShaderNodeEmission", Strength=1.0)
    T.L(col, em.inputs["Color"])
    T.L(em.outputs[0], T.out.inputs["Surface"])
    me.materials.append(m)
    ob.visible_shadow = False
    ob.visible_diffuse = False
    ob.visible_glossy = False
    return ob


def eye_center(ch):
    eyes = ch.mesh("Eyes")
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = eyes.evaluated_get(dg)
    mw = eyes.matrix_world
    pts = [mw @ v.co for v in ev.data.vertices]
    c = sum(pts, Vector()) / len(pts)
    return c


def frame_bust(eye, facing, turn, frame_h=0.56, lens=85.0, eye_from_top=0.40):
    """Camera in front of the face (rotated by `turn` degrees around the head), eyes at eye_from_top."""
    sensor = 36.0
    dist = frame_h * lens / sensor
    a = math.radians(turn)
    f = Vector(facing).normalized()
    side = Vector((f.y, -f.x, 0))
    d = (f * math.cos(a) + side * math.sin(a)).normalized()
    loc = eye + d * dist + Vector((0, 0, 0.04))
    cam = A.camera(loc, eye + Vector((0, 0, -0.01)), lens=lens, sensor=sensor, fstop=1.8, focus=dist)
    cam.data.shift_y = -(0.5 - eye_from_top)
    return cam, d


def lights(eye, d, tint, rim2, echo=False):
    up = Vector((0, 0, 1))
    side = d.cross(up).normalized()
    # key: large soft box above camera-left; fill: dim from camera-right; rims from behind
    A.light("AREA", eye + d * 1.1 + side * 1.5 + up * 1.0, 60 if not echo else 30, (1.0, 0.97, 0.93), size=1.8, target=tuple(eye), name="Key")
    A.light("AREA", eye + d * 1.6 - side * 1.4 + up * 0.0, 10, (0.8, 0.9, 1.0), size=2.0, target=tuple(eye), name="Fill")
    A.light("AREA", eye - d * 1.0 - side * 1.0 + up * 0.6, 230 if not echo else 120, tint, size=0.6, target=tuple(eye + up * 0.05), name="Rim")
    A.light("AREA", eye - d * 0.8 + side * 1.1 + up * 0.2, 150, rim2, size=0.5, target=tuple(eye - up * 0.1), name="Rim2")


def portrait_human(cid, cfg, size):
    if cid in ("kael", "lyra"):  # remade heroes (heroes_v2): Unity FBX + manifest materials + catalog default hair
        ch = A.load_hero(cid, (0, 0, 0), 0, pose=(cfg["clip"], cfg["frame"]))
    else:
        ch = A.load_character(cid, (0, 0, 0), 0, pose=(cfg["clip"], cfg["frame"]), detail=True)
    ch.shapes(**cfg.get("shapes", {}))
    t = cfg["turn"]
    A.rot_bone(ch, "Head", x=-3 - cfg.get("head_up", 0))
    hb = ch.mesh("HeadsetBand")
    if hb is not None:  # the headset band sits above the bob hair (floating halo): leave it out of the close-up
        hb.hide_render = True
    eye = eye_center(ch)
    cam, d = frame_bust(eye, (0, -1, 0), t, frame_h=cfg.get("frame_h", 0.52 if cid != "nia" else 0.46))
    backdrop(cfg["tint"], eye - d * 8.0 + Vector((0, 0, -0.3)), eye + d)
    bokeh(eye, d, cfg["tint"], cfg["rim2"], seed=len(cid) * 7 + ord(cid[0]))
    lights(eye, d, cfg.get("rim", cfg["tint"]), cfg["rim2"], echo=bool(A.CHARS[cid].get("echo")))
    if cfg.get("fill"):
        A.light("AREA", eye + d * 1.2 + Vector((0, 0, -0.25)), 12 * cfg["fill"], (1.0, 0.92, 0.85), size=0.8, target=tuple(eye), name="FaceFill")
    if A.CHARS[cid].get("echo"):
        # faint Aether motes around the echo
        import random
        rr = random.Random(3)
        mote = A.aether_material("mote", color=cfg["tint"], color2=A.CYAN, strength=6.0, core=True)
        for i in range(26):
            p = eye + Vector((rr.uniform(-0.4, 0.4), rr.uniform(0.05, 0.35), rr.uniform(-0.45, 0.25)))
            if abs(p.x - eye.x) < 0.14 and p.z > eye.z - 0.25:
                p.x += 0.3 if p.x >= eye.x else -0.3
            bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=1, radius=rr.uniform(0.002, 0.006), location=p)
            bpy.context.active_object.data.materials.append(mote)
    return cam


def portrait_robot(cid, cfg, size):
    rb = A.load_robot(cid, (0, 0, 0), 0, pose={"head": (6, 8, 0), "neck": (0, 0, 0), "chest": (0, -6, 0)} if cid == "bolt" else
                      {"head": (-6, -10, 0), "chest": (4, 6, 0), "upperarm_L": (-10, 0, 10), "upperarm_R": (-10, 0, -10)})
    bpy.context.view_layer.update()
    head = rb.objs["head"]
    mw = head.matrix_world
    pts = [mw @ v.co for v in head.data.vertices]
    c = sum(pts, Vector()) / len(pts)
    top = max(p.z for p in pts)
    if cid == "bolt":
        eye = c + Vector((0, 0, 0.0))
        cam, d = frame_bust(eye, (0, -1, 0), cfg["turn"], frame_h=0.75, lens=70)
    else:
        eye = Vector((c.x, c.y, c.z - 0.05))
        cam, d = frame_bust(eye, (0, -1, 0), cfg["turn"], frame_h=3.6, lens=60, eye_from_top=0.36)
    rb.glow(4.0 if cid == "bolt" else 6.0)
    scale = 1.0 if cid == "bolt" else 3.2
    backdrop(cfg["tint"], eye - d * 8.0 * scale + Vector((0, 0, -0.3 * scale)), eye + d)
    bokeh(eye, d, cfg["tint"], cfg["rim2"], scale=scale, seed=len(cid) * 7 + ord(cid[0]))
    up = Vector((0, 0, 1))
    side = d.cross(up).normalized()
    A.light("AREA", eye + (d * 1.8 + side * 1.1 + up * 0.9) * scale, 130 * scale * scale, (1.0, 0.95, 0.9), size=1.2 * scale, target=tuple(eye), name="Key")
    A.light("AREA", eye + (d * 1.6 - side * 1.6) * scale, 25 * scale * scale, (0.85, 0.9, 1.0), size=1.6 * scale, target=tuple(eye), name="Fill")
    A.light("AREA", eye + (-d * 1.2 - side * 0.9 + up * 0.5) * scale, 170 * scale * scale, cfg["tint"], size=0.6 * scale, target=tuple(eye), name="Rim")
    A.light("AREA", eye + (-d * 1.0 + side * 1.0 + up * 0.2) * scale, 90 * scale * scale, cfg["rim2"], size=0.5 * scale, target=tuple(eye), name="Rim2")
    if cid == "guardian":
        bpy.data.objects["Backdrop"].scale = (4, 4, 4)
    return cam


def render_one(cid, size=512, preview=False):
    A.reset()
    A.setup_render((size, size), samples=160, look="AgX - Medium High Contrast", exposure=0.0, adaptive=0.01)
    A.world_gradient((0.004, 0.005, 0.007), (0.004, 0.005, 0.007), (0.002, 0.002, 0.003), strength=1.0)
    cfg = CFG[cid]
    if cfg.get("robot"):
        portrait_robot(cid, cfg, size)
    else:
        portrait_human(cid, cfg, size)
    A.compositor(bloom=0.25, bloom_size=0.55, threshold=1.2, dispersion=0.0, vignette=0.22)
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, f"{cid}.png") if not preview else os.path.join(A.PREVIEWS, "tests", f"portrait_{cid}.png")
    A.render(out)
    if not preview:
        A.save_scene(f"portrait_{cid}") if cid in ("kael", "maren", "guardian") else None
    return out


def main():
    a = A.args()
    size = int(a[a.index("--size") + 1]) if "--size" in a else 512
    preview = "--preview" in a
    ids = [x for x in a if x in CFG] or list(CFG)
    for cid in ids:
        render_one(cid, size, preview)


if __name__ == "__main__":
    main()
