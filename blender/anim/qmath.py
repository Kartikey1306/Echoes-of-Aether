"""Vectorised quaternion helpers (numpy, w-x-y-z order) for the CMU retarget pipeline."""
import math

import numpy as np


def qnorm(q):
    return q / np.linalg.norm(q, axis=-1, keepdims=True)


def qmul(a, b):
    aw, ax, ay, az = np.moveaxis(a, -1, 0)
    bw, bx, by, bz = np.moveaxis(b, -1, 0)
    return np.stack([aw * bw - ax * bx - ay * by - az * bz,
                     aw * bx + ax * bw + ay * bz - az * by,
                     aw * by - ax * bz + ay * bw + az * bx,
                     aw * bz + ax * by - ay * bx + az * bw], axis=-1)


def qconj(q):
    return q * np.array([1.0, -1.0, -1.0, -1.0])


def qrot(q, v):
    """Rotate vectors v[...,3] by quaternions q[...,4] (broadcasting)."""
    q = np.asarray(q, float)
    v = np.asarray(v, float)
    shp = np.broadcast_shapes(q.shape[:-1], v.shape[:-1])
    q = np.broadcast_to(q, shp + (4,))
    v = np.broadcast_to(v, shp + (3,))
    w = q[..., :1]
    u = q[..., 1:]
    t = 2.0 * np.cross(u, v)
    return v + w * t + np.cross(u, t)


def qfrommat(m):
    m = np.asarray(m, dtype=float)
    shp = m.shape[:-2]
    m = m.reshape(-1, 3, 3)
    out = np.zeros((len(m), 4))
    for i, r in enumerate(m):
        t = r[0, 0] + r[1, 1] + r[2, 2]
        if t > 0:
            s = math.sqrt(t + 1.0) * 2
            out[i] = [0.25 * s, (r[2, 1] - r[1, 2]) / s, (r[0, 2] - r[2, 0]) / s, (r[1, 0] - r[0, 1]) / s]
        elif r[0, 0] > r[1, 1] and r[0, 0] > r[2, 2]:
            s = math.sqrt(1.0 + r[0, 0] - r[1, 1] - r[2, 2]) * 2
            out[i] = [(r[2, 1] - r[1, 2]) / s, 0.25 * s, (r[0, 1] + r[1, 0]) / s, (r[0, 2] + r[2, 0]) / s]
        elif r[1, 1] > r[2, 2]:
            s = math.sqrt(1.0 + r[1, 1] - r[0, 0] - r[2, 2]) * 2
            out[i] = [(r[0, 2] - r[2, 0]) / s, (r[0, 1] + r[1, 0]) / s, 0.25 * s, (r[1, 2] + r[2, 1]) / s]
        else:
            s = math.sqrt(1.0 + r[2, 2] - r[0, 0] - r[1, 1]) * 2
            out[i] = [(r[1, 0] - r[0, 1]) / s, (r[0, 2] + r[2, 0]) / s, (r[1, 2] + r[2, 1]) / s, 0.25 * s]
    return qnorm(out).reshape(shp + (4,))


def qtomat(q):
    w, x, y, z = np.moveaxis(q, -1, 0)
    return np.stack([np.stack([1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)], -1),
                     np.stack([2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)], -1),
                     np.stack([2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)], -1)], -2)


def qaxis(axis, ang):
    axis = np.asarray(axis, dtype=float)
    axis = axis / max(1e-12, np.linalg.norm(axis))
    ang = np.asarray(ang, dtype=float)
    s = np.sin(ang / 2)[..., None]
    return np.concatenate([np.cos(ang / 2)[..., None], axis * s], axis=-1)


def qfromto(u, v):
    """Minimal rotation taking direction u to direction v."""
    u = np.asarray(u, float) / np.linalg.norm(u, axis=-1, keepdims=True)
    v = np.asarray(v, float) / np.linalg.norm(v, axis=-1, keepdims=True)
    d = np.sum(u * v, axis=-1)
    c = np.cross(u, v)
    q = np.concatenate([(1 + d)[..., None], c], axis=-1)
    bad = d < -0.999999
    if np.any(bad):
        # 180 degrees: any axis perpendicular to u
        ub = np.atleast_2d(u)[np.atleast_1d(bad)]
        ax = np.cross(ub, [1, 0, 0])
        small = np.linalg.norm(ax, axis=-1) < 1e-6
        ax[small] = np.cross(ub[small], [0, 1, 0])
        qb = np.concatenate([np.zeros((len(ax), 1)), ax], axis=-1)
        q = np.atleast_2d(q)
        q[np.atleast_1d(bad)] = qb
        q = q.reshape(np.shape(d) + (4,))
    return qnorm(q)


def qangle(q):
    return 2 * np.arccos(np.clip(np.abs(q[..., 0]), 0, 1))


def qhemi(q, ref=None):
    """Flip signs so quaternions are continuous along axis 0 (or on the hemisphere of ref)."""
    q = np.array(q, dtype=float)
    if ref is not None:
        s = np.sign(np.sum(q * ref, axis=-1, keepdims=True))
        s[s == 0] = 1
        return q * s
    for i in range(1, len(q)):
        d = np.sum(q[i] * q[i - 1], axis=-1)
        q[i][d < 0] *= -1
    return q


def qslerp(a, b, t):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    t = np.asarray(t, float)
    d = np.sum(a * b, axis=-1, keepdims=True)
    b = np.where(d < 0, -b, b)
    d = np.abs(d)
    t = t[..., None] if t.ndim == d.ndim - 1 or t.ndim == 0 else t
    lin = d > 0.9995
    th = np.arccos(np.clip(d, -1, 1))
    st = np.sin(th)
    st = np.where(lin, 1.0, st)
    wa = np.where(lin, 1 - t, np.sin((1 - t) * th) / st)
    wb = np.where(lin, t, np.sin(t * th) / st)
    return qnorm(wa * a + wb * b)


def qpow(q, t):
    """q^t (scale the rotation angle)."""
    q = qhemi(q, np.array([1.0, 0, 0, 0]))
    ang = 2 * np.arccos(np.clip(q[..., 0], -1, 1))
    s = np.sqrt(np.maximum(1e-16, 1 - q[..., 0] ** 2))
    axis = q[..., 1:] / s[..., None]
    t = np.asarray(t, float)
    na = ang * t
    out = np.concatenate([np.cos(na / 2)[..., None], axis * np.sin(na / 2)[..., None]], axis=-1)
    small = ang < 1e-8
    if np.any(small):
        out[small] = np.array([1.0, 0, 0, 0])
    return out


def qlog(q):
    q = qhemi(q, np.array([1.0, 0, 0, 0]))
    s = np.linalg.norm(q[..., 1:], axis=-1)
    ang = np.arctan2(s, q[..., 0])
    k = np.where(s > 1e-12, ang / np.maximum(s, 1e-12), 1.0)
    return q[..., 1:] * k[..., None]


def qexp(v):
    a = np.linalg.norm(v, axis=-1)
    k = np.where(a > 1e-12, np.sin(a) / np.maximum(a, 1e-12), 1.0)
    return np.concatenate([np.cos(a)[..., None], v * k[..., None]], axis=-1)


def yaw_quat(angle):
    """Rotation about Blender's +Z (up)."""
    return qaxis([0, 0, 1], angle)


def gauss_kernel(sigma):
    if sigma <= 0.05:
        return np.array([1.0])
    r = max(1, int(math.ceil(3 * sigma)))
    x = np.arange(-r, r + 1)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    return k / k.sum()


def smooth(x, sigma, cyclic=False):
    """Gaussian smoothing along axis 0 for arrays [T, ...] (positions or hemisphere-aligned quaternions)."""
    k = gauss_kernel(sigma)
    if len(k) == 1 or len(x) < 3:
        return np.array(x, dtype=float)
    r = len(k) // 2
    if cyclic:
        xp = np.concatenate([x[-r:], x, x[:r]], axis=0)
    else:
        xp = np.concatenate([np.repeat(x[:1], r, 0), x, np.repeat(x[-1:], r, 0)], axis=0)
    out = np.zeros_like(x, dtype=float)
    for i, w in enumerate(k):
        out += w * xp[i:i + len(x)]
    return out


def qsmooth(q, sigma, cyclic=False):
    """Smooth quaternion tracks [T, ..., 4] (sign-continuous averaging, renormalised)."""
    if sigma <= 0.05 or len(q) < 3:
        return q
    q = qhemi(q)
    k = gauss_kernel(sigma)
    r = len(k) // 2
    if cyclic:
        # the wrap may change sign: flip the padding to stay on the same hemisphere
        s = np.sign(np.sum(q[-1] * q[0], axis=-1, keepdims=True))
        s[s == 0] = 1
        rr = min(r, len(q))
        xp = np.concatenate([q[-rr:] * s, q, q[:rr] * s], axis=0)
        if rr < r:
            xp = np.concatenate([np.repeat(xp[:1], r - rr, 0), xp, np.repeat(xp[-1:], r - rr, 0)], axis=0)
    else:
        xp = np.concatenate([np.repeat(q[:1], r, 0), q, np.repeat(q[-1:], r, 0)], axis=0)
    out = np.zeros_like(q, dtype=float)
    for i, w in enumerate(k):
        out += w * xp[i:i + len(q)]
    return qnorm(out)
