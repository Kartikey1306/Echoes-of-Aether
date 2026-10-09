"""Build the shared building atlases (plain Python 3 + numpy/scipy/PIL):

  building_trim_atlas  (2048^2, opaque)    trim sheet: full-width bands that tile along U (painted / bare / rusted
                                            metals, wood, tarp, tiles, glossy paints, rubber) + flat-colour cells
  emit_building_atlas  (2048^2, emissive)  LED ad screens, light boxes, window interiors (residential + office panes,
                                            vary per floor), lightbox signs, LED strip bands, neon / lamp flat cells

They replace ~40 small materials per complete building (env kit Building_*) with two, and the landmark kit shares
them. Band/cell content for existing env materials is resampled from the env kit's own baked textures, so the
remapped buildings keep their look; window / office / sign cells are new procedural art (cells.py).

Writes Assets/Art/Environment/Textures/<atlas>/<atlas>_{BaseColor,Normal,MaskMap[,Emission]}.png and
blender/city_landmarks/out/atlas_layout.json (UV rects, metre spans; read by atlas_remap.py / the landmark builders).

  python3 atlas_build.py [--preview]
"""
import json
import os
import sys
import time

import numpy as np

import cells as C
import lmpaths
import ptex as P

WIN_GAIN, OFFICE_GAIN = 3.2, 2.6   # interiors match EOA_CityLights window brightness (warm 1.6/1.0/0.55 HDR)
EMIT_MAX = 6.0          # emissionIntensity of emit_building_atlas; emission texels are scaled by I_src / EMIT_MAX
S = 2048
ENV_MANIFEST = os.path.join(lmpaths.ENV_KIT, "manifest.json")

# ---------------------------------------------------------------------------------------------- trim sheet
# (name, band px height, nominal metres per 2048 px along U). Bands run full width -> tile along U.
TRIM_BANDS = [
    ("metal_dark", 384), ("metal_painted", 192), ("metal_painted_white", 192), ("metal_rusted", 192), ("wood", 192),
    ("paint_glossy_dark", 128), ("tile_grimy", 128), ("tarp", 128), ("tarp_blue", 64), ("metal_painted_yellow", 64),
    ("metal_painted_red", 64), ("metal_bare", 64), ("chrome_scratched", 64), ("paint_glossy_red", 64), ("rubber", 32),
]
TRIM_U_M = 4.0
# flat colour cells: name -> (sRGB base, metallic, smoothness)
TRIM_FLAT = {
    "plastic_dark": ((0.06, 0.065, 0.07), 0.0, 0.45), "plastic_orange": ((0.75, 0.2, 0.03), 0.0, 0.45),
    "black": ((0.02, 0.02, 0.02), 0.0, 0.1), "terracotta": ((0.46, 0.25, 0.17), 0.0, 0.28),
    "brass": ((0.78, 0.6, 0.3), 1.0, 0.62), "copper_patina": ((0.29, 0.52, 0.45), 0.2, 0.35),
    "lacquer_red": ((0.55, 0.06, 0.05), 0.0, 0.72), "lacquer_green": ((0.07, 0.24, 0.17), 0.0, 0.68),
    "foliage_dark": ((0.06, 0.12, 0.06), 0.0, 0.32), "foliage_mid": ((0.13, 0.25, 0.1), 0.0, 0.35),
    "cloth_red": ((0.55, 0.12, 0.1), 0.0, 0.15), "cloth_white": ((0.72, 0.72, 0.68), 0.0, 0.12),
    "cloth_blue": ((0.12, 0.25, 0.5), 0.0, 0.14), "cloth_yellow": ((0.75, 0.6, 0.18), 0.0, 0.14),
    "cloth_pink": ((0.7, 0.3, 0.45), 0.0, 0.14), "paint_white": ((0.78, 0.79, 0.78), 0.0, 0.5),
    "titanium": ((0.62, 0.64, 0.66), 1.0, 0.7), "steel_galv": ((0.5, 0.52, 0.53), 1.0, 0.48),
    "soil": ((0.12, 0.095, 0.075), 0.0, 0.3), "bark": ((0.18, 0.13, 0.09), 0.0, 0.25),
    "stone_light": ((0.6, 0.58, 0.54), 0.0, 0.55), "stone_dark": ((0.1, 0.1, 0.11), 0.0, 0.75),
    "tile_white": ((0.82, 0.83, 0.8), 0.0, 0.7), "tile_green": ((0.25, 0.5, 0.42), 0.0, 0.7),
    "rope": ((0.45, 0.38, 0.28), 0.0, 0.12), "hazard_yellow": ((0.85, 0.65, 0.05), 0.2, 0.5),
}

# ---------------------------------------------------------------------------------------------- emissive atlas
EMIT_FLAT = {  # name -> (sRGB base, metallic, smoothness, sRGB emission or None, intensity)
    **{f"emit_neon_{k}": None for k in ("magenta", "pink", "cyan", "blue", "yellow", "violet")},
    **{k: None for k in ("emit_red", "emit_green", "emit_amber", "emit_white", "emit_cyan", "emit_violet", "glass_dark")},
    "lantern_red": ((0.6, 0.08, 0.05), 0.0, 0.4, (1.0, 0.22, 0.12), 3.0),
    "lantern_warm": ((0.7, 0.45, 0.2), 0.0, 0.4, (1.0, 0.7, 0.35), 3.0),
    "led_white": ((0.85, 0.85, 0.88), 0.0, 0.6, (0.92, 0.96, 1.0), 4.5),
    "beacon_red": ((0.3, 0.02, 0.02), 0.0, 0.6, (1.0, 0.1, 0.06), 6.0),
    "furnace": ((0.3, 0.1, 0.02), 0.0, 0.3, (1.0, 0.45, 0.1), 5.0),
    "holo_cyan_solid": ((0.0, 0.3, 0.35), 0.0, 0.9, (0.0, 0.9, 1.0), 4.0),
    "holo_magenta_solid": ((0.3, 0.02, 0.25), 0.0, 0.9, (1.0, 0.17, 0.84), 4.0),
    "dark_glass_blue": ((0.03, 0.05, 0.08), 0.7, 0.95, None, 0.0),
    "dark_glass_warm": ((0.06, 0.045, 0.03), 0.6, 0.93, None, 0.0),
}
STRIPS = ["emit_strip_cyan", "emit_strip_violet", "emit_strip_warm", "emit_strip_magenta", "emit_strip_pink", "emit_strip_blue",
          "emit_strip_yellow"]
PANELS = ["emit_panel_cyan", "emit_panel_violet", "emit_panel_white", "emit_panel_warm"]
SMALL_PANELS = ["emit_panel_magenta", "emit_panel_yellow"]


def rect_uv(x0, y0, x1, y1, w=S, h=S):
    """Pixel rect (row 0 = top) -> UV rect [u0, v0, u1, v1] with v up."""
    return [x0 / w, 1 - y1 / h, x1 / w, 1 - y0 / h]


class Atlas:
    def __init__(self, name, emissive):
        self.name = name
        self.base = np.zeros((S, S, 3), np.float32)       # sRGB
        self.nrm = np.zeros((S, S, 3), np.float32) + np.array([0.5, 0.5, 1.0], np.float32)
        self.mask = np.zeros((S, S, 4), np.float32) + np.array([0.0, 1.0, 0.5, 0.5], np.float32)
        self.emit = np.zeros((S, S, 3), np.float32) if emissive else None   # linear, normalised by EMIT_MAX
        self.entries = {}

    def put(self, x0, y0, block):
        h, w = block["base"].shape[:2]
        self.base[y0:y0 + h, x0:x0 + w] = block["base"]
        self.nrm[y0:y0 + h, x0:x0 + w] = block["normal"]
        self.mask[y0:y0 + h, x0:x0 + w] = block["mask"]
        if self.emit is not None and block.get("emit") is not None:
            self.emit[y0:y0 + h, x0:x0 + w] = block["emit"]

    def save(self, preview=False):
        d = os.path.join(lmpaths.ENV_TEXTURES, self.name)
        os.makedirs(d, exist_ok=True)
        P.save_rgb(os.path.join(d, f"{self.name}_BaseColor.png"), srgb=self.base)
        P.save_rgb(os.path.join(d, f"{self.name}_Normal.png"), srgb=P.renorm(self.nrm))
        P.save_rgba(os.path.join(d, f"{self.name}_MaskMap.png"), self.mask)
        tex = {"BaseColor": f"Textures/{self.name}/{self.name}_BaseColor.png", "Normal": f"Textures/{self.name}/{self.name}_Normal.png",
               "MaskMap": f"Textures/{self.name}/{self.name}_MaskMap.png", "Occlusion": f"Textures/{self.name}/{self.name}_MaskMap.png"}
        if self.emit is not None:
            P.save_rgb(os.path.join(d, f"{self.name}_Emission.png"), lin_rgb=self.emit)
            tex["Emission"] = f"Textures/{self.name}/{self.name}_Emission.png"
        return tex


# ---------------------------------------------------------------------------------------------- source access
def env_materials():
    return json.load(open(ENV_MANIFEST))["materials"]


def src_maps(mats, name):
    m = mats[name]
    t = m.get("textures") or {}
    out = {}
    for k in ("BaseColor", "Normal", "MaskMap", "Emission"):
        if k in t:
            out[k] = P.load(os.path.join(lmpaths.ENV_KIT, t[k]), "RGBA" if k == "MaskMap" else "RGB")
    return m, out


def flat_block(h, w, base_srgb, metal, smooth, emit_lin=None):
    b = {"base": np.zeros((h, w, 3), np.float32) + np.asarray(base_srgb, np.float32),
         "normal": np.zeros((h, w, 3), np.float32) + np.array([0.5, 0.5, 1.0], np.float32),
         "mask": np.zeros((h, w, 4), np.float32) + np.array([metal, 1.0, 0.5, smooth], np.float32)}
    if emit_lin is not None:
        b["emit"] = np.zeros((h, w, 3), np.float32) + np.asarray(emit_lin, np.float32)
    return b


def param_flat(mats, name, h, w):
    m = mats[name]
    bc = m.get("baseColor", [0.5, 0.5, 0.5, 1])[:3]
    e = None
    if m.get("emission") is not None and m.get("emissionIntensity", 0) > 0:
        e = P.srgb_to_linear(np.array(m["emission"], np.float32)) * m["emissionIntensity"] / EMIT_MAX
    return flat_block(h, w, bc, m.get("metallic", 0.0), m.get("smoothness", 0.5), e)


def tex_block(mats, name, w, h, span_w_m=None, span_h_m=None, fit=False, strip=False):
    """Resample an env baked material into a w x h block (world: metre spans; fit: whole texture; strip: U metres x V 0..1)."""
    m, mp = src_maps(mats, name)
    tile = m.get("tileSizeMeters") or 1.0
    out = {}
    for k, img in mp.items():
        if fit:
            out[k] = P.resize(img, w, h)
        elif strip:
            # U: metres along with the material's tile; V: the whole texture height across the strip
            sh, sw = img.shape[:2]
            reps = int(round(span_w_m / tile))
            row = np.concatenate([img] * reps, axis=1)
            out[k] = P.resize(row, w, h)
        else:
            out[k] = P.resample_tile(img, tile, w, h, span_w_m, span_h_m)
    b = {"base": out["BaseColor"][..., :3], "normal": P.renorm(out["Normal"][..., :3]), "mask": out["MaskMap"]}
    if "Emission" in out:
        I = m.get("emissionIntensity", 1.0)
        b["emit"] = P.srgb_to_linear(out["Emission"][..., :3]) * I / EMIT_MAX
    return b


def cell_block(c, w, h, emit_scale=1.0, px_m=0.006):
    n = P.normal_from_height(c["height"], px_m, 1.0, wrap=False)
    return {"base": P.linear_to_srgb(c["base"]), "normal": n, "mask": c["mask"], "emit": c["emit"] * emit_scale / EMIT_MAX}


# ---------------------------------------------------------------------------------------------- build
def build_trim(mats):
    A = Atlas("building_trim_atlas", emissive=False)
    y = 0
    for name, hpx in TRIM_BANDS:
        tile = mats[name].get("tileSizeMeters") or 1.0
        span_w = max(tile, round(TRIM_U_M / tile) * tile)
        span_h = hpx * span_w / S
        A.put(0, y, tex_block(mats, name, S, hpx, span_w, span_h))
        pad = 6 if hpx >= 128 else (4 if hpx >= 64 else 2)
        A.entries[name] = {"kind": "band", "rect": rect_uv(0, y, S, y + hpx), "span_u_m": round(span_w, 4), "span_v_m": round(span_h, 4),
                           "pad_v": pad / S}
        y += hpx
    # flat cells: remaining rows, 64 x (S - y) each
    fh = S - y
    names = list(TRIM_FLAT)
    cw = S // max(len(names), 32)
    for i, name in enumerate(names):
        base, metal, smooth = TRIM_FLAT[name]
        if name in mats and mats[name].get("kind") == "param":
            mm = mats[name]
            base, metal, smooth = mm["baseColor"][:3], mm.get("metallic", 0.0), mm.get("smoothness", 0.5)
        x0 = i * cw
        A.put(x0, y, flat_block(fh, cw, base, metal, smooth))
        A.entries[name] = {"kind": "flat", "uv": [(x0 + cw / 2) / S, 1 - (y + fh / 2) / S], "rect": rect_uv(x0, y, x0 + cw, S)}
    print(f"[atlas] trim: {len(TRIM_BANDS)} bands, {len(names)} flat cells, band rows used {y}/{S}")
    return A


def build_emit(mats):
    A = Atlas("emit_building_atlas", emissive=True)
    # rows 0-511: two ads; 512-1023: ad_c, screen, 4 panels
    for i, name in enumerate(("screen_ad_a", "screen_ad_b")):
        A.put(i * 1024, 0, tex_block(mats, name, 1024, 512, fit=True))
        A.entries[name] = {"kind": "cell", "rect": rect_uv(i * 1024, 0, i * 1024 + 1024, 512), "pad": [1.5 / S, 1.5 / S]}
    A.put(0, 512, tex_block(mats, "screen_ad_c", 1024, 512, fit=True))
    A.entries["screen_ad_c"] = {"kind": "cell", "rect": rect_uv(0, 512, 1024, 1024), "pad": [1.5 / S, 1.5 / S]}
    A.put(1024, 512, tex_block(mats, "screen", 256, 256, fit=True))
    A.entries["screen"] = {"kind": "cell", "rect": rect_uv(1024, 512, 1280, 768), "pad": [1.5 / S, 1.5 / S]}
    for i, name in enumerate(PANELS):
        x0, y0 = 1280 + (i % 2) * 256, 512 + (i // 2) * 256
        A.put(x0, y0, tex_block(mats, name, 256, 256, fit=True))
        A.entries[name] = {"kind": "cell", "rect": rect_uv(x0, y0, x0 + 256, y0 + 256), "pad": [1.5 / S, 1.5 / S]}
    nsign = 0
    for (x0, y0) in ((1024, 768), (1152, 768), (1792, 512), (1920, 512), (1792, 768), (1920, 768)):
        A.put(x0, y0, cell_block(C.sign_cell(256, 128, nsign, 500 + nsign), 128, 256, emit_scale=2.2))
        A.entries[f"sign_{nsign:02d}"] = {"kind": "cell", "rect": rect_uv(x0, y0, x0 + 128, y0 + 256), "pad": [1.5 / S, 1.5 / S], "group": "sign"}
        nsign += 1
    # rows 1024-1279: 8 residential windows (256^2): the env's two lit windows + new interiors
    wins = [("window_lit_warm", None), ("window_lit_cool", None)] + [(f"win_{v}", v) for v in C.WINDOW_VARIANTS[:6]]
    # rows 1280-1535: 16 office panes (128 x 256)
    # rows 1536-1791: 6 more residential windows (256 wide: 3 slots of 2 x 128) ... laid out below
    for i, (name, var) in enumerate(wins):
        x0, y0 = i * 256, 1024
        if var is None:
            blk = tex_block(mats, name, 256, 256, fit=True)
        else:
            blk = cell_block(C.window_cell(256, 256, var, 100 + i), 256, 256, emit_scale=WIN_GAIN)
        A.put(x0, y0, blk)
        A.entries[name] = {"kind": "cell", "rect": rect_uv(x0, y0, x0 + 256, y0 + 256), "pad": [1.5 / S, 1.5 / S], "group": "window"}
    for i in range(16):
        var = C.OFFICE_VARIANTS[i]
        x0, y0 = i * 128, 1280
        A.put(x0, y0, cell_block(C.office_cell(256, 128, var, 300 + i), 128, 256, emit_scale=OFFICE_GAIN))
        A.entries[f"office_{i:02d}_{var}"] = {"kind": "cell", "rect": rect_uv(x0, y0, x0 + 128, y0 + 256), "pad": [1.5 / S, 1.5 / S],
                                              "group": "office", "lit": not var.startswith("dark")}
    # rows 1536-1791: 6 residential windows (256^2) at x 0..1535, 4 signs (128x256) at x 1536..2047
    for i, var in enumerate(C.WINDOW_VARIANTS[6:]):
        x0, y0 = i * 256, 1536
        A.put(x0, y0, cell_block(C.window_cell(256, 256, var, 200 + i), 256, 256, emit_scale=WIN_GAIN))
        A.entries[f"win_{var}"] = {"kind": "cell", "rect": rect_uv(x0, y0, x0 + 256, y0 + 256), "pad": [1.5 / S, 1.5 / S], "group": "window"}
    for i in range(4):
        x0, y0 = 1536 + i * 128, 1536
        if i == 3:
            # two small panels stacked (128 x 128)
            for j, name in enumerate(SMALL_PANELS):
                A.put(x0, y0 + j * 128, tex_block(mats, name, 128, 128, fit=True))
                A.entries[name] = {"kind": "cell", "rect": rect_uv(x0, y0 + j * 128, x0 + 128, y0 + j * 128 + 128), "pad": [1.5 / S, 1.5 / S]}
            continue
        A.put(x0, y0, cell_block(C.sign_cell(256, 128, nsign, 500 + nsign), 128, 256, emit_scale=2.2))
        A.entries[f"sign_{nsign:02d}"] = {"kind": "cell", "rect": rect_uv(x0, y0, x0 + 128, y0 + 256), "pad": [1.5 / S, 1.5 / S], "group": "sign"}
        nsign += 1
    # rows 1792-1959: 7 LED strips (24 px each, 4 m along U)
    y = 1792
    for name in STRIPS:
        A.put(0, y, tex_block(mats, name, S, 24, span_w_m=4.0, strip=True))
        A.entries[name] = {"kind": "strip", "rect": rect_uv(0, y, S, y + 24), "span_u_m": 4.0, "pad_v": 1.0 / S}
        y += 24
    # rows 1960-2047 (88 px): flat cells 64 px wide
    fh = S - y
    names = list(EMIT_FLAT)
    cw = 64
    for i, name in enumerate(names):
        x0 = i * cw
        spec = EMIT_FLAT[name]
        if spec is None:
            blk = param_flat(mats, name, fh, cw)
        else:
            base, metal, smooth, e, I = spec
            el = None if e is None else P.srgb_to_linear(np.array(e, np.float32)) * I / EMIT_MAX
            blk = flat_block(fh, cw, base, metal, smooth, el)
        if "emit" not in blk:
            blk["emit"] = np.zeros((fh, cw, 3), np.float32)
        A.put(x0, y, blk)
        A.entries[name] = {"kind": "flat", "uv": [(x0 + cw / 2) / S, 1 - (y + fh / 2) / S], "rect": rect_uv(x0, y, x0 + cw, S)}
    # more sign cells re-using leftover space: none (row full). Extra sign variety comes from UV flips / rotations.
    print(f"[atlas] emit: {len(A.entries)} entries ({nsign} signs, {len(names)} flats)")
    return A


def preview_sheet(A, path):
    from PIL import Image
    img = np.concatenate([A.base, P.linear_to_srgb(np.clip(A.emit, 0, 1)) if A.emit is not None else A.mask[..., [3, 3, 3]]], axis=1)
    Image.fromarray(P.to_u8(img)).resize((2048, 1024), Image.LANCZOS).save(path)


def main():
    t0 = time.time()
    mats = env_materials()
    trim = build_trim(mats)
    emit = build_emit(mats)
    layout = {"emitMax": EMIT_MAX, "atlases": {}}
    for A in (trim, emit):
        tex = A.save()
        layout["atlases"][A.name] = {"size": [S, S], "textures": tex, "entries": A.entries}
    json.dump(layout, open(lmpaths.ATLAS_LAYOUT, "w"), indent=1)
    if "--preview" in sys.argv:
        preview_sheet(trim, os.path.join(lmpaths.PREVIEWS, "atlas_trim.png"))
        preview_sheet(emit, os.path.join(lmpaths.PREVIEWS, "atlas_emit.png"))
    print(f"[atlas] done in {time.time() - t0:.1f}s -> {lmpaths.ATLAS_LAYOUT}")


if __name__ == "__main__":
    main()
