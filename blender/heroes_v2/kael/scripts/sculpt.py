"""Procedural face/body sculpt on top of the MPFB targets (Kael v2).

All operations are smooth displacement fields defined in head-local coordinates (metres, relative to the
`mixamorig:Head` bone head: +X character left, -Y forward, +Z up), so they apply identically to the body and to every
fitted attachment (brows, lashes, teeth). Fields are sums of anisotropic Gaussian "pushes".
"""
import numpy as np

# (center xyz, radii xyz, displacement xyz, mirror)   -- head-local metres
HEAD_OPS = [
    # chin: a touch more forward/down, squarer
    ((0.0, -0.108, -0.066), (0.020, 0.016, 0.014), (0.0, -0.0025, -0.0018), False),
    ((0.014, -0.104, -0.068), (0.012, 0.014, 0.012), (0.0018, -0.0012, -0.001), True),
    # jaw angle (gonion): wider, lower, crisper
    ((0.056, 0.004, -0.052), (0.016, 0.02, 0.017), (0.0058, 0.001, -0.003), True),
    # mandible body between angle and chin: fill out laterally -> straighter jaw line
    ((0.044, -0.05, -0.064), (0.014, 0.022, 0.012), (0.0028, -0.0008, -0.001), True),
    # tighten the under-chin / jaw-neck transition (no soft double chin)
    ((0.0, -0.06, -0.09), (0.042, 0.03, 0.012), (0.0, -0.003, 0.0045), False),
    ((0.03, -0.035, -0.085), (0.02, 0.03, 0.012), (-0.001, 0.0, 0.0035), True),
    # cheekbones: higher and more lateral / forward
    ((0.052, -0.07, 0.024), (0.016, 0.016, 0.011), (0.0034, -0.0022, 0.0008), True),
    # buccal hollow under the cheekbone
    ((0.047, -0.07, -0.012), (0.014, 0.016, 0.014), (-0.0012, 0.0012, 0.0), True),
    # brow ridge forward, glabella a little
    ((0.027, -0.104, 0.064), (0.02, 0.012, 0.009), (0.0, -0.0055, -0.0012), True),
    ((0.0, -0.111, 0.058), (0.012, 0.01, 0.01), (0.0, -0.0024, 0.0), False),
    # nose bridge: straighter, slightly higher between the eyes
    ((0.0, -0.107, 0.03), (0.008, 0.01, 0.012), (0.0, -0.0014, 0.0), False),
    # lower lip slightly fuller, upper lip vermilion forward
    ((0.0, -0.116, -0.039), (0.013, 0.008, 0.005), (0.0, -0.0012, -0.0004), False),
    ((0.0, -0.118, -0.024), (0.012, 0.007, 0.004), (0.0, -0.0008, 0.0002), False),
    # deep-set eyes: soft push of the upper lid/socket under the heavier brow
    ((0.031, -0.098, 0.044), (0.012, 0.008, 0.007), (0.0, 0.0012, -0.0006), True),
    # subtle asymmetry (natural face): his left brow a touch higher, right mouth corner slightly up
    ((0.03, -0.103, 0.066), (0.016, 0.012, 0.008), (0.0, 0.0, 0.0012), False),
    ((-0.024, -0.106, -0.031), (0.008, 0.008, 0.006), (0.0, 0.0, 0.0008), False),
    # lip seal: relaxed closed mouth (the MakeHuman neutral parts the lips)
    ((0.0, -0.114, -0.0305), (0.022, 0.013, 0.0035), (0.0, 0.0, -0.003), False),
    ((0.0, -0.112, -0.0375), (0.022, 0.013, 0.0035), (0.0, 0.0, 0.003), False),
]


def field(P, ops=HEAD_OPS, scale=1.0):
    """Displacement for head-local points P (N,3)."""
    D = np.zeros_like(P, dtype=np.float64)
    for c, r, d, mirror in ops:
        c = np.asarray(c, np.float64); r = np.asarray(r, np.float64); d = np.asarray(d, np.float64)
        sides = (1, -1) if mirror else (1,)
        for s in sides:
            cc = c * np.array((s, 1, 1)); dd = d * np.array((s, 1, 1))
            q = (P - cc) / r
            w = np.exp(-np.sum(q * q, axis=1))
            D += w[:, None] * dd[None]
    return D * scale


def apply_head(points_world, head_world, scale=1.0, eye_guard=None):
    """World points -> displaced world points. eye_guard: [(center, radius)] spheres left untouched (eyeballs)."""
    P = np.asarray(points_world, np.float64) - np.asarray(head_world)
    D = field(P, scale=scale)
    if eye_guard:
        for c, rad in eye_guard:
            dd = np.linalg.norm(points_world - np.asarray(c), axis=1)
            D *= np.clip((dd - rad * 0.8) / (rad * 0.4), 0, 1)[:, None]
    return np.asarray(points_world) + D


def mix_co(o):
    if not o.data.shape_keys:
        a = np.empty(len(o.data.vertices) * 3, np.float32); o.data.vertices.foreach_get("co", a)
        return a.reshape(-1, 3).astype(np.float64)
    k = o.shape_key_add(name="__mix", from_mix=True)
    a = np.empty(len(o.data.vertices) * 3, np.float32); k.data.foreach_get("co", a)
    o.shape_key_remove(k)
    return a.reshape(-1, 3).astype(np.float64)


def apply_to_objects(objs, head_world, scale=1.0, eye_guard=None, name="k_sculpt"):
    """Add the sculpt as a shape key (value 1) on meshes with keys, or move the vertices directly."""
    import numpy as _np
    for o in objs:
        M = _np.array(o.matrix_world); Mi = _np.linalg.inv(M)
        co = mix_co(o)
        w = co @ M[:3, :3].T + M[:3, 3]
        w2 = apply_head(w, head_world, scale, eye_guard)
        l2 = w2 @ Mi[:3, :3].T + Mi[:3, 3]
        if _np.abs(l2 - co).max() < 1e-7:
            continue
        if o.data.shape_keys:
            k = o.shape_key_add(name=name, from_mix=False)
            base = _np.empty(len(o.data.vertices) * 3, _np.float32); k.data.foreach_get("co", base)
            base = base.reshape(-1, 3) + (l2 - co)
            k.data.foreach_set("co", base.astype(_np.float32).ravel())
            k.value = 1.0
        else:
            o.data.vertices.foreach_set("co", l2.astype(_np.float32).ravel())
            o.data.update()
