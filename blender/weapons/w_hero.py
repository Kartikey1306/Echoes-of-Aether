"""Hero weapons: Kael's Aether pistol "Lancet", its thigh holster, Kael's forearm blade emitter, Giva's gauntlet
(left hand; the right one is mirrored at export) and the spent energy-cell casing.

All coordinates are Unity local space of the weapon (x right, y up, z forward), metres. See wkit.py.
"""
import math

import numpy as np

import wkit as W
from wkit import Part, chamfer_rect, rounded_rect, circle, resample, resample_corners, basis_from_z, rot_x, rot_y, rot_z

# material slot names (palette entries in build_weapons.py)
GUN, POLY, ALLOY, ACCENT, STRAP, GLOW, CAVITY, ARMOR, VIOLET = (
    "gunmetal", "polymer", "alloy", "accent_teal", "strap", "glow", "cavity", "armor_graphite", "accent_violet")

BORE_Y = 0.062


# ============================================================================ Kael: Aether pistol
def pistol():
    p = Part("kael_pistol")
    # --- slide (lofted, chamfered top, tapered nose)
    def sec(z, hw, yb, yt, cb, ct):
        return (z, chamfer_rect(hw, yb, yt, cb, ct))
    p.loft([sec(-0.060, 0.0136, 0.0458, 0.0752, 0.0018, 0.0065),
            sec(-0.0555, 0.0152, 0.0442, 0.0800, 0.0020, 0.0080),
            sec(0.098, 0.0152, 0.0442, 0.0800, 0.0020, 0.0080),
            sec(0.118, 0.0148, 0.0450, 0.0778, 0.0020, 0.0100),
            sec(0.133, 0.0132, 0.0470, 0.0735, 0.0020, 0.0095)], GUN)
    # rear / front serrations and the ejection port (high-poly detail)
    for sx in (-1, 1):
        p.ridges((sx * 0.0156, 0.0615, -0.051), (sx * 0.0156, 0.0615, -0.022), 8, (0.0012, 0.026, 0.0016), GUN)
        p.ridges((sx * 0.0156, 0.0615, 0.074), (sx * 0.0156, 0.0615, 0.094), 5, (0.0012, 0.024, 0.0016), GUN)
        # Aether conduit strip along the lower slide
        p.box((sx * 0.0156, 0.0482, 0.044), (0.0016, 0.0030, 0.090), GLOW, "both")
        # takedown pins / screws
        p.rivet((sx * 0.0137, 0.034, -0.030), (sx, 0, 0), 0.0018, 0.0010, ALLOY)
        p.rivet((sx * 0.0137, 0.034, 0.045), (sx, 0, 0), 0.0016, 0.0010, ALLOY)
    p.box((0.0156, 0.0675, 0.022), (0.0010, 0.0150, 0.036), ALLOY, "hi")       # ejection port (right side)
    p.box((0.0164, 0.0675, 0.022), (0.0006, 0.0110, 0.031), CAVITY, "hi")
    # top rail with cross slots, sights
    p.box((0, 0.0815, 0.030), (0.0085, 0.0034, 0.112), ACCENT, chamfer=0.0008)
    p.ridges((0, 0.0835, -0.018), (0, 0.0835, 0.078), 13, (0.0090, 0.0012, 0.0022), ACCENT)
    for sx in (-1, 1):
        p.box((sx * 0.0074, 0.0845, -0.051), (0.0060, 0.0080, 0.0070), GUN, chamfer=0.0012)
    p.box((0, 0.0820, -0.0555), (0.020, 0.0035, 0.0055), GUN, chamfer=0.0008)
    p.box((0, 0.0820, 0.110), (0.0042, 0.0080, 0.0070), GUN, chamfer=0.0010)
    p.box((0, 0.0848, 0.1085), (0.0018, 0.0020, 0.0016), GLOW, "both")        # front sight tritium dot
    for sx in (-1, 1):
        p.box((sx * 0.0074, 0.0868, -0.0548), (0.0016, 0.0018, 0.0010), GLOW, "both")
    # rear charge indicator (three cells on the back of the slide -- what the camera sees)
    for i, x in enumerate((-0.0065, 0.0, 0.0065)):
        p.box((x, 0.0650, -0.0603), (0.0040, 0.0035, 0.0012), GLOW, "both")
    # --- frame (lower receiver), side profile with beavertail
    frame = [(-0.052, 0.0465), (-0.054, 0.0350), (-0.046, 0.0262), (-0.018, 0.0300), (0.012, 0.0250),
             (0.066, 0.0250), (0.066, 0.0465)]
    p.side_profile(frame, 0.0136, GUN, chamfer=0.0016)
    # dust cover cage around the Aether chamber
    p.box((0, 0.0270, 0.095), (0.0262, 0.0055, 0.060), GUN, chamfer=0.0012)
    p.box((0, 0.0435, 0.095), (0.0270, 0.0050, 0.060), GUN, chamfer=0.0010)
    p.box((0, 0.0352, 0.1215), (0.0262, 0.0215, 0.0070), GUN, chamfer=0.0016)
    for z in (0.078, 0.092, 0.106):
        for sx in (-1, 1):
            p.box((sx * 0.0122, 0.0352, z), (0.0026, 0.0130, 0.0032), ALLOY, chamfer=0.0005)
    p.cyl(0.0060, 0.066, 0.118, 16, GLOW, t=(0, 0.0352, 0))                    # Aether chamber
    for z in (0.071, 0.085, 0.099, 0.113):
        p.tube_ring(0.0066, 0.0012, 16, 6, ALLOY, t=(0, 0.0352, z))
    # rail slots under the dust cover (hi)
    p.ridges((0, 0.0238, 0.072), (0, 0.0238, 0.118), 6, (0.020, 0.0012, 0.0030), GUN)
    # --- barrel / emitter
    p.cyl(0.0102, 0.118, 0.170, 20, ALLOY, t=(0, BORE_Y, 0), chamfer=0.0008)
    for z in (0.137, 0.148, 0.159):
        p.tube_ring(0.0104, 0.0016, 20, 6, GLOW, t=(0, BORE_Y, z))
    for k in range(3):
        a = math.radians(90 + 120 * k)
        c = (0.0127 * math.cos(a), BORE_Y + 0.0127 * math.sin(a), 0.150)
        p.box(c, (0.0042, 0.0042, 0.036), GUN, chamfer=0.0008, M=rot_z(a))
    p.cyl(0.0128, 0.166, 0.178, 22, GUN, t=(0, BORE_Y, 0), chamfer=0.0016)       # muzzle crown
    p.cyl(0.0080, 0.1772, 0.1790, 18, GLOW, t=(0, BORE_Y, 0))                     # emitter lens
    p.tube_ring(0.0095, 0.0011, 20, 6, ALLOY, t=(0, BORE_Y, 0.1786))
    for k in range(6):                                                              # compensator ports (hi)
        a = math.radians(60 * k + 30)
        p.box((0.0127 * math.cos(a), BORE_Y + 0.0127 * math.sin(a), 0.172), (0.0016, 0.0016, 0.0060), CAVITY, "hi", M=rot_z(a))
    # --- grip (tilted 15 deg, butt to the rear) with the energy-cell magazine
    tilt = math.radians(15)
    up = np.array([0, math.cos(tilt), math.sin(tilt)])
    fwd = np.array([0, -math.sin(tilt), math.cos(tilt)])
    g0 = up * -0.070
    grip_secs = []
    for s, hw, hh, r in ((0.000, 0.0150, 0.0240, 0.0085), (0.010, 0.0146, 0.0236, 0.0085), (0.060, 0.0142, 0.0232, 0.0090),
                         (0.098, 0.0140, 0.0245, 0.0090), (0.112, 0.0138, 0.0262, 0.0080)):
        grip_secs.append((s, rounded_rect(hw, hh, r, 3)))
    p.loft_axis(grip_secs, POLY, g0, up, yhint=fwd)
    # finger grooves on the front strap and side texture ribs (hi)
    Rg = basis_from_z(fwd, up)
    for i in range(3):
        s = 0.030 + i * 0.020
        c = g0 + up * s + fwd * 0.0236
        p.box(tuple(c), (0.022, 0.0040, 0.0020), POLY, "hi", M=Rg)
    Rs = basis_from_z(fwd, up)
    for sx in (-1, 1):
        for i in range(11):
            s = 0.018 + i * 0.0075
            c = g0 + up * s + np.array([sx * 0.0147, 0, 0])
            p.box(tuple(c), (0.0012, 0.0024, 0.034), POLY, "hi", M=Rs)
    # magazine base: alloy plate + glowing cell window
    Rm = basis_from_z(up, fwd)
    p.loft_axis([(-0.006, rounded_rect(0.0158, 0.0265, 0.0085, 3)), (0.004, rounded_rect(0.0160, 0.0268, 0.0088, 3))],
                ALLOY, g0, up, yhint=fwd)
    p.loft_axis([(0.004, rounded_rect(0.0152, 0.0246, 0.0082, 3)), (0.0075, rounded_rect(0.0152, 0.0246, 0.0082, 3))],
                GLOW, g0, up, yhint=fwd)
    p.rivet(tuple(g0 - up * 0.006), tuple(-up), 0.004, 0.0012, ALLOY)
    # magazine release, slide stop
    p.box((-0.0140, 0.0300, 0.0090), (0.0024, 0.0060, 0.0080), ALLOY, chamfer=0.0008)
    p.box((-0.0145, 0.0420, 0.0300), (0.0020, 0.0040, 0.0160), GUN, chamfer=0.0006)
    # --- trigger guard and trigger
    guard = [(0, 0.0280, 0.0640), (0, 0.0150, 0.0665), (0, 0.0040, 0.0620), (0, -0.0010, 0.0480), (0, -0.0020, 0.0350),
             (0, 0.0010, 0.0255), (0, 0.0080, 0.0210)]
    p.sweep(guard, rounded_rect(0.0020, 0.0046, 0.0014, 2), GUN, yhint=(1, 0, 0), smooth=3)
    trig = [(0, 0.0255, 0.0450), (0, 0.0180, 0.0462), (0, 0.0110, 0.0440), (0, 0.0060, 0.0400)]
    p.sweep(trig, rounded_rect(0.0016, 0.0033, 0.0010, 2), ALLOY, yhint=(1, 0, 0), smooth=3)
    # anchors
    p.empty("muzzle", (0, BORE_Y, 0.182))
    p.empty("eject", (0.017, 0.072, 0.022))
    p.empty("grip", (0, 0, 0))
    return p


# ============================================================================ Kael: thigh holster (pistol space)
def holster():
    p = Part("kael_holster")
    N = 28
    slide_only = rounded_rect(0.0195, 0.0230, 0.0080, 3, 0, 0.0625)
    full = rounded_rect(0.0195, 0.0420, 0.0085, 3, 0, 0.0450)
    nose = rounded_rect(0.0175, 0.0300, 0.0075, 3, 0, 0.0580)
    A, B, C = resample(slide_only, N), resample(full, N), resample(nose, N)
    cav = resample(W.offset_poly(W.ccw(slide_only), -0.0035), N)
    secs = [(-0.012, cav), (-0.026, cav), (-0.026, W.offset_poly(A, -0.0012)), (-0.0245, A), (0.010, A), (0.036, B),
            (0.150, B), (0.188, C), (0.195, W.offset_poly(C, -0.004))]
    # mouth: the first ring goes *into* the shell (dark cavity cap)
    p.loft(secs[1:], ARMOR, cap0=False)
    p.loft(secs[:2], CAVITY, cap1=False)
    # moulded ridges / retention hood
    for sx in (-1, 1):
        p.box((sx * 0.0202, 0.0560, 0.090), (0.0016, 0.020, 0.090), ARMOR, "hi", chamfer=0.0006)
    p.box((0.0208, 0.0700, 0.000), (0.0040, 0.0150, 0.024), GUN, chamfer=0.0012)      # hood lever
    p.box((0.0230, 0.0700, 0.006), (0.0010, 0.0045, 0.0045), GLOW)                    # lock LED
    p.rivet((0.0198, 0.024, 0.060), (1, 0, 0), 0.0028, 0.0011, ALLOY)
    p.rivet((0.0198, 0.024, 0.140), (1, 0, 0), 0.0028, 0.0011, ALLOY)
    # slim back plate against the thigh (-x side) and one thin leg strap; the leg itself fills the rest
    C0 = np.array([-0.104, 0.050])
    def arc_ring(r0, r1, a0, a1, n):
        outer = [(C0[0] + r1 * math.cos(math.radians(a)), C0[1] + r1 * math.sin(math.radians(a))) for a in np.linspace(a0, a1, n)]
        inner = [(C0[0] + r0 * math.cos(math.radians(a)), C0[1] + r0 * math.sin(math.radians(a))) for a in np.linspace(a1, a0, n)]
        return W.ccw(outer + inner)
    ring = arc_ring(0.078, 0.082, -24, 24, 8)
    ring_in = arc_ring(0.0788, 0.0812, -21, 21, 8)
    p.loft([(-0.030, ring_in), (-0.027, ring), (0.120, ring), (0.123, ring_in)], ARMOR)
    p.box((-0.0235, 0.050, 0.045), (0.006, 0.020, 0.090), GUN, chamfer=0.0015)          # bridge
    sring = arc_ring(0.0795, 0.0820, -95, 95, 26)
    p.loft([(0.080, sring), (0.098, sring)], STRAP)
    c = (C0[0] + 0.0835 * math.cos(math.radians(70)), C0[1] + 0.0835 * math.sin(math.radians(70)), 0.089)
    p.box(c, (0.004, 0.012, 0.022), ALLOY, chamfer=0.001, M=rot_z(math.radians(70)))
    return p


# ============================================================================ Kael: wrist emitter ring (glove cuff)
def emitter():
    """Flush emitter ring for the glove cuff. Origin = forearm axis at the wrist, +z towards the hand, +y = back of the
    wrist, x lateral. Authored for a 34 x 28 mm (half-axis) wrist; the runtime scales x / y to the measured cuff.
    At rest it is a thin dark band with a faint cyan line; the blade forms out of the slot on the back of the wrist."""
    p = Part("kael_emitter")
    TAU = math.tau
    RX, RY = 0.034, 0.028

    def ellipse(rx, ry, z, n=40):
        return [(rx * math.cos(TAU * k / n), ry * math.sin(TAU * k / n), z) for k in range(n)]
    # band (black, glove-like) with a raised rim each side
    p.sweep(ellipse(RX + 0.0016, RY + 0.0016, 0.0), rounded_rect(0.0018, 0.0055, 0.0010, 2), GUN, yhint=(0, 0, 1), closed=True)
    for z in (-0.0055, 0.0055):
        p.sweep(ellipse(RX + 0.0028, RY + 0.0028, z), rounded_rect(0.0010, 0.0010, 0.0005, 1), ALLOY, yhint=(0, 0, 1), closed=True)
    # faint cyan line
    p.sweep(ellipse(RX + 0.0035, RY + 0.0035, 0.0), rounded_rect(0.0005, 0.0009, 0.0003, 1), GLOW, yhint=(0, 0, 1), closed=True)
    # emitter slot on the back of the wrist: low alloy bezel with a glowing slit, flush with the band
    top = RY + 0.0034
    p.box((0, top, 0.0), (0.016, 0.0024, 0.0110), GUN, chamfer=0.0008)
    p.box((0, top + 0.0013, 0.0), (0.0110, 0.0006, 0.0018), GLOW)
    for sx in (-1, 1):
        p.box((sx * 0.0068, top + 0.0013, 0.0), (0.0016, 0.0008, 0.0080), ALLOY, chamfer=0.0003)
    p.empty("blade_root", (0, top + 0.0016, 0.002))
    return p


# ============================================================================ Giva: energy gauntlet (left hand)
def gauntlet():
    """Hand space: origin at the wrist joint, +z to the knuckles (MCP at ~0.080), +y back of the hand, +x thumb side
    (LEFT hand). Mirrored in x for the right hand."""
    p = Part("giva_gauntlet")
    def arch(R, r, a, cy, n=14):
        outer = [(R * math.sin(math.radians(t)), cy + R * math.cos(math.radians(t))) for t in np.linspace(a, -a, n)]
        inner = [(r * math.sin(math.radians(t)), cy + r * math.cos(math.radians(t))) for t in np.linspace(-a, a, n)]
        return W.ccw(outer + inner)
    # proximal (violet) and distal (graphite) dorsal plates, layered
    pr = arch(0.0465, 0.0420, 40, -0.0275)
    pr_in = arch(0.0460, 0.0425, 37, -0.0275)
    p.loft([(0.006, pr_in), (0.010, pr), (0.042, pr), (0.046, pr_in)], VIOLET)
    ds = arch(0.0490, 0.0445, 42, -0.0280)
    ds_in = arch(0.0485, 0.0450, 39, -0.0280)
    p.loft([(0.036, ds_in), (0.040, ds), (0.068, ds), (0.072, ds_in)], ARMOR)
    # knuckle guard with three claw sockets
    kn = arch(0.0520, 0.0430, 46, -0.0300, 16)
    kn_in = arch(0.0512, 0.0438, 43, -0.0300, 16)
    p.loft([(0.066, kn_in), (0.070, kn), (0.086, kn), (0.090, kn_in)], ALLOY)
    for i, a in enumerate((20.0, 0.0, -20.0)):           # index, middle, ring (thumb at +x)
        x = 0.0525 * math.sin(math.radians(a))
        y = -0.0300 + 0.0525 * math.cos(math.radians(a))
        p.cyl(0.0062, 0.074, 0.093, 16, GUN, t=(x, y, 0), chamfer=0.0010)
        p.cyl(0.0040, 0.0930, 0.0950, 14, GLOW, t=(x, y, 0))
        p.tube_ring(0.0052, 0.0010, 16, 6, ALLOY, t=(x, y, 0.0932))
        p.empty("claw_%d" % i, (x, y, 0.095))
    # chevron inlays and plate rivets
    for sx in (-1, 1):
        p.box((sx * 0.0085, 0.0215, 0.056), (0.0024, 0.0012, 0.022), GLOW, M=rot_y(math.radians(sx * 28)))
        p.rivet((sx * 0.0285, 0.0055, 0.024), (sx * 0.6, 0.8, 0), 0.0022, 0.0010, ALLOY)
        p.rivet((sx * 0.0305, 0.0060, 0.055), (sx * 0.6, 0.8, 0), 0.0022, 0.0010, ALLOY)
    p.ridges((-0.012, 0.0215, 0.016), (0.012, 0.0215, 0.016), 5, (0.0016, 0.0010, 0.012), VIOLET, "hi")
    # wrist cuff (closed sweep around an ellipse) + glow line
    def ellipse(rx, ry, cy, z, n=36):
        return [(rx * math.cos(TAU * k / n), cy + ry * math.sin(TAU * k / n), z) for k in range(n)]
    TAU = math.tau
    p.sweep(ellipse(0.0405, 0.0315, -0.002, -0.008), rounded_rect(0.0040, 0.0160, 0.0022, 2), ARMOR, yhint=(0, 0, 1), closed=True)
    p.sweep(ellipse(0.0448, 0.0358, -0.002, -0.008), rounded_rect(0.0009, 0.0024, 0.0006, 1), GLOW, yhint=(0, 0, 1), closed=True)
    p.sweep(ellipse(0.0436, 0.0346, -0.002, -0.019), rounded_rect(0.0010, 0.0016, 0.0006, 1), ALLOY, yhint=(0, 0, 1), closed=True)
    p.sweep(ellipse(0.0436, 0.0346, -0.002, 0.003), rounded_rect(0.0010, 0.0016, 0.0006, 1), ALLOY, yhint=(0, 0, 1), closed=True)
    # metacarpal strap holding the palm emitter
    p.sweep(ellipse(0.0400, 0.0190, -0.002, 0.030), rounded_rect(0.0016, 0.0070, 0.0010, 1), STRAP, yhint=(0, 0, 1), closed=True)
    # palm emitter
    Mp = basis_from_z((0, -1, 0), (0, 0, 1))
    p.cyl(0.0175, 0.0, 0.0050, 22, GUN, M=Mp, t=(0, -0.0170, 0.044), chamfer=0.0012)
    p.cyl(0.0120, 0.0050, 0.0062, 20, GLOW, M=Mp, t=(0, -0.0170, 0.044))
    p.tube_ring(0.0140, 0.0012, 22, 6, ALLOY, M=Mp, t=(0, -0.0222, 0.044))
    p.empty("palm", (0, -0.026, 0.044))
    return p


# ============================================================================ spent energy cell
def casing():
    p = Part("energy_cell")
    p.cyl(0.0052, -0.013, -0.006, 16, ALLOY, chamfer=0.0010)
    p.cyl(0.0052, 0.006, 0.013, 16, ALLOY, chamfer=0.0010)
    p.cyl(0.0046, -0.0062, 0.0062, 16, GLOW)
    for z in (-0.003, 0.003):
        p.tube_ring(0.0049, 0.0007, 16, 4, GUN, t=(0, 0, z))
    return p
