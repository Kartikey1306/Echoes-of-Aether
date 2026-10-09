"""Tileable skin pore / micro-texture detail normal map shared by the heroes' EOA/Skin shader (_ParallaxMap slot).

  python3 skin_pores.py [out.png]
512 x 512, seamless: ~1600 pores (soft pits, varied size/depth), fine polygonal skin micro-relief (Worley edges) and a little
noise. One tile represents ~24 mm of skin; the shader tiles it (_Parallax) over the character's UV square.
Procedural (numpy), OpenGL normal convention (+Y = up in UV).
"""
import sys, math
import numpy as np
from PIL import Image

N = 512
rng = np.random.default_rng(11)
H = np.zeros((N, N), np.float64)
yy, xx = np.mgrid[0:N, 0:N].astype(np.float64)


def wrap_d(a, c):
    d = a - c
    return (d + N / 2) % N - N / 2


# pores: soft pits, jittered grid for even spacing
cells = 40
step = N / cells
for i in range(cells):
    for j in range(cells):
        if rng.random() < 0.12:
            continue
        cx = (i + rng.uniform(0.15, 0.85)) * step
        cy = (j + rng.uniform(0.15, 0.85)) * step
        r = rng.uniform(1.3, 2.8)
        depth = rng.uniform(0.6, 1.0)
        x0, x1 = int(cx - 4 * r), int(cx + 4 * r) + 1
        y0, y1 = int(cy - 4 * r), int(cy + 4 * r) + 1
        xs = np.arange(x0, x1) % N
        ys = np.arange(y0, y1) % N
        dx = wrap_d(xx[np.ix_(ys, xs)], cx)
        dy = wrap_d(yy[np.ix_(ys, xs)], cy)
        H[np.ix_(ys, xs)] -= depth * np.exp(-(dx * dx + dy * dy) / (r * r))


def tile_noise(freq, seed):
    """Seamless value noise (bilinear on a freq x freq periodic lattice)."""
    g = np.random.default_rng(seed).random((freq, freq))
    u = xx / N * freq
    v = yy / N * freq
    i0 = np.floor(u).astype(int) % freq; j0 = np.floor(v).astype(int) % freq
    i1 = (i0 + 1) % freq; j1 = (j0 + 1) % freq
    fu = u - np.floor(u); fv = v - np.floor(v)
    fu = fu * fu * (3 - 2 * fu); fv = fv * fv * (3 - 2 * fv)
    a = g[j0, i0] * (1 - fu) + g[j0, i1] * fu
    b = g[j1, i0] * (1 - fu) + g[j1, i1] * fu
    return a * (1 - fv) + b * fv


# skin micro-relief: polygonal plateaus bounded by fine grooves (periodic Worley F2 - F1 edges), two scales, the
# grooves broken up and varied in depth so no regular hatching or line families show when tiled
def worley_edges(n_cells, seed, stretch=1.0):
    g = np.random.default_rng(seed)
    st = N / n_cells
    pts = np.array([((i + g.uniform(0.1, 0.9)) * st, (j + g.uniform(0.1, 0.9)) * st) for i in range(n_cells) for j in range(n_cells)])
    f1 = np.full((N, N), 1e9); f2 = np.full((N, N), 1e9)
    for (px, py) in pts:
        dx = wrap_d(xx, px); dy = wrap_d(yy, py) * stretch
        d = np.sqrt(dx * dx + dy * dy)
        f2 = np.where(d < f1, f1, np.minimum(f2, d))
        f1 = np.minimum(f1, d)
    return f2 - f1


e1 = worley_edges(14, 3, 1.15)
e2 = worley_edges(26, 5, 0.9)
var1 = 0.35 + 0.65 * tile_noise(8, 7)
var2 = 0.3 + 0.7 * tile_noise(16, 9)
H -= 0.2 * np.exp(-(e1 / 1.6) ** 2) * var1
H -= 0.09 * np.exp(-(e2 / 1.1) ** 2) * var2
H += 0.08 * (tile_noise(64, 21) - 0.5) + 0.05 * (tile_noise(128, 23) - 0.5)
H -= H.mean()
# normals (periodic central differences); v (up) = -row
gx = (np.roll(H, -1, 1) - np.roll(H, 1, 1)) * 0.5
gy = (np.roll(H, 1, 0) - np.roll(H, -1, 0)) * 0.5
strength = 2.2
nx, ny, nz = -gx * strength, -gy * strength, np.ones_like(H)
ln = np.sqrt(nx * nx + ny * ny + nz * nz)
rgb = np.stack([nx / ln, ny / ln, nz / ln], -1) * 0.5 + 0.5
out = sys.argv[1] if len(sys.argv) > 1 else "/Users/kartikey/Desktop/Game/unity/EchoesOfAether/Assets/Art/Characters/SkinDetail/Skin_Pores_Normal.png"
Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8), "RGB").save(out)
print("PORES", out, N)
