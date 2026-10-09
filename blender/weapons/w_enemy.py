"""Enemy weapons: drone twin blaster, Sentinel forearm blade, Guardian arm cannon and folding arm blade.

Unity local space (x right, y up, z forward), metres. Glow faces use the slot "enemy_glow": at runtime they get the
robot's own glow material, so they brighten with the attack telegraph and take the variant colour.
"""
import math

import numpy as np

import wkit as W
from wkit import Part, chamfer_rect, rounded_rect, circle, resample, basis_from_z, rot_x, rot_y, rot_z

STEEL, SHELL, ALLOY, HAZARD, BLADE, EGLOW, CAVITY = (
    "enemy_steel", "enemy_shell", "alloy", "hazard", "blade_steel", "enemy_glow", "cavity")


# ============================================================================ drone twin blaster
def drone_blaster():
    """Origin = mount point under the drone's chin; barrels along +z. Muzzles: muzzle_0 (left), muzzle_1 (right)."""
    p = Part("drone_blaster")
    # yoke / receiver
    p.loft([(-0.070, chamfer_rect(0.070, -0.050, 0.010, 0.012, 0.016)), (-0.060, chamfer_rect(0.085, -0.062, 0.020, 0.016, 0.020)),
            (0.050, chamfer_rect(0.085, -0.062, 0.020, 0.016, 0.020)), (0.075, chamfer_rect(0.072, -0.055, 0.012, 0.014, 0.016))], SHELL)
    p.box((0, 0.028, -0.010), (0.060, 0.020, 0.080), STEEL, chamfer=0.006)          # mount neck
    p.ridges((-0.086, -0.022, -0.040), (-0.086, -0.022, 0.030), 6, (0.003, 0.050, 0.006), STEEL)
    p.ridges((0.086, -0.022, -0.040), (0.086, -0.022, 0.030), 6, (0.003, 0.050, 0.006), STEEL)
    for sx in (-1, 1):
        p.rivet((sx * 0.0855, 0.006, 0.040), (sx, 0, 0), 0.006, 0.003, ALLOY)
        p.box((sx * 0.087, -0.040, 0.000), (0.003, 0.010, 0.050), HAZARD, "hi")
    # targeting sensor on top
    p.box((0.000, 0.018, 0.060), (0.034, 0.020, 0.030), STEEL, chamfer=0.004)
    p.cyl(0.008, 0.075, 0.079, 14, EGLOW, t=(0, 0.018, 0))
    # twin barrels
    for i, sx in enumerate((-1, 1)):
        x, y = sx * 0.050, -0.032
        p.cyl(0.026, 0.050, 0.170, 20, STEEL, t=(x, y, 0), chamfer=0.004)            # shroud
        p.cyl(0.019, 0.040, 0.360, 18, STEEL, t=(x, y, 0))                            # bore
        p.cyl(0.0205, 0.180, 0.270, 18, EGLOW, t=(x, y, 0))                           # coil (shows between fins)
        for z in (0.186, 0.208, 0.230, 0.252, 0.274):
            p.cyl(0.0270, z - 0.0045, z + 0.0045, 20, ALLOY, t=(x, y, 0), chamfer=0.0015)
        p.cyl(0.0255, 0.322, 0.370, 20, STEEL, t=(x, y, 0), chamfer=0.004)           # muzzle brake
        for k in range(4):
            a = math.radians(45 + 90 * k)
            p.box((x + 0.025 * math.cos(a), y + 0.025 * math.sin(a), 0.345), (0.004, 0.004, 0.026), CAVITY, "hi", M=rot_z(a))
        p.cyl(0.0120, 0.3695, 0.3715, 16, EGLOW, t=(x, y, 0))
        p.empty("muzzle_%d" % i, (x, y, 0.378))
    # bridge between the barrels
    p.box((0, -0.032, 0.120), (0.070, 0.022, 0.050), SHELL, chamfer=0.005)
    p.box((0, -0.032, 0.300), (0.060, 0.014, 0.022), STEEL, chamfer=0.003)
    return p


# ============================================================================ blade cross-section helper
def blade_ring(ys, ye, half_t, bevel_h, edge_t=0.0012):
    """Closed (x, y) section of a flat blade: spine at ys (top, flat, thickness 2*half_t), edge at ye (bottom)."""
    yb = ye + bevel_h
    pts = [(0.0, ye), (edge_t, ye + 0.0015), (half_t, yb), (half_t, ys - half_t * 0.4), (half_t * 0.6, ys),
           (-half_t * 0.6, ys), (-half_t, ys - half_t * 0.4), (-half_t, yb), (-edge_t, ye + 0.0015)]
    return W.ccw(pts)


def blade_loft(p, stations, mat, glow_mat, half_t, bevel_frac, glow_off, glow_h, M=None, t=(0, 0, 0), edge=0.0):
    """stations: list of (z, y_spine, y_edge). Adds the blade body, the two glowing inlays and (edge > 0) a heated
    glowing cutting edge of that half height."""
    secs, gl, gr, ed = [], [], [], []
    for z, ys, ye in stations:
        h = ys - ye
        th = half_t * (0.55 + 0.45 * min(1.0, h / 0.06))
        secs.append((z, blade_ring(ys, ye, th, h * bevel_frac)))
        yb = ye + h * bevel_frac
        gy = yb + glow_off * h
        if edge > 0:
            ed.append((z, W.ccw([(0.0, ye - edge * 0.3), (edge * 0.45, ye + edge * 0.6), (edge * 0.3, ye + edge * 1.6),
                                 (-edge * 0.3, ye + edge * 1.6), (-edge * 0.45, ye + edge * 0.6)])))
        for side, lst in ((1, gr), (-1, gl)):
            lst.append((z, [(side * th + side * 0.0004 - 0.0005, gy - glow_h), (side * th + side * 0.0004 + 0.0005, gy - glow_h),
                            (side * th + side * 0.0004 + 0.0005, gy + glow_h), (side * th + side * 0.0004 - 0.0005, gy + glow_h)]))
    p.loft(secs, mat, M=M, t=t)
    p.loft(gl, glow_mat, M=M, t=t)
    p.loft(gr, glow_mat, M=M, t=t)
    if edge > 0:
        p.loft(ed, glow_mat, M=M, t=t)


# ============================================================================ Sentinel forearm blade
def sentinel_blade():
    """Origin at the mount on the outer forearm. +z along the forearm towards the hand, -y = cutting edge side,
    +x = away from the arm."""
    p = Part("sentinel_blade")
    # mount housing with hydraulic struts
    p.loft([(-0.020, chamfer_rect(0.024, -0.050, 0.040, 0.008, 0.010)), (-0.010, chamfer_rect(0.030, -0.058, 0.048, 0.010, 0.012)),
            (0.200, chamfer_rect(0.030, -0.058, 0.048, 0.010, 0.012)), (0.215, chamfer_rect(0.024, -0.050, 0.040, 0.008, 0.010))], SHELL)
    p.ridges((0.031, -0.030, 0.020), (0.031, -0.030, 0.150), 8, (0.003, 0.030, 0.006), STEEL)
    for sx in (-1, 1):
        p.cyl_axis(0.0075, (sx * 0.020, 0.052, 0.010), (sx * 0.020, 0.052, 0.170), 12, ALLOY, chamfer=0.002)
        p.cyl_axis(0.0105, (sx * 0.020, 0.052, 0.010), (sx * 0.020, 0.052, 0.070), 12, STEEL, chamfer=0.002)
    p.box((0.031, 0.010, 0.185), (0.004, 0.016, 0.016), EGLOW)
    p.box((0.031, -0.044, 0.060), (0.003, 0.008, 0.060), HAZARD, "hi")
    # blade: spine straight, edge sweeping out then up to a clipped tip
    st = []
    for z in np.linspace(0.120, 0.840, 16):
        u = (z - 0.12) / 0.72
        ys = 0.030 - 0.010 * u
        ye = -0.060 - 0.028 * math.sin(math.pi * min(1.0, u * 1.15)) + 0.020 * u
        st.append((z, ys, ye))
    for z, f in ((0.875, 0.62), (0.905, 0.36), (0.925, 0.14)):
        ys = 0.020 - (1 - f) * 0.030
        ye = -0.050 + (1 - f) * 0.040
        st.append((z, ys, ye))
    blade_loft(p, st, BLADE, EGLOW, 0.0075, 0.30, 0.05, 0.0022, edge=0.0022)
    p.empty("tip", (0, 0.0, 0.93))
    return p


# ============================================================================ Guardian arm cannon (left forearm)
def guardian_cannon():
    """Origin = mount centre on the forearm; barrel along +z (beyond the fist). muzzle at the front."""
    p = Part("guardian_cannon")
    s = 1.0
    # power unit housing
    p.loft([(-0.360, chamfer_rect(0.200, -0.160, 0.200, 0.050, 0.080)), (-0.320, chamfer_rect(0.250, -0.200, 0.250, 0.060, 0.100)),
            (0.420, chamfer_rect(0.250, -0.200, 0.250, 0.060, 0.100)), (0.500, chamfer_rect(0.210, -0.170, 0.210, 0.050, 0.080))], SHELL)
    # vents, glowing cells, hazard plates
    for sx in (-1, 1):
        p.ridges((sx * 0.252, 0.030, -0.250), (sx * 0.252, 0.030, 0.100), 9, (0.010, 0.200, 0.018), STEEL)
        p.box((sx * 0.256, -0.120, 0.250), (0.010, 0.050, 0.220), HAZARD, "hi")
        for z in (0.180, 0.300):
            p.rivet((sx * 0.253, 0.150, z), (sx, 0, 0), 0.018, 0.010, ALLOY)
    for i, x in enumerate((-0.11, 0.0, 0.11)):
        p.cyl_axis(0.035, (x, 0.255, -0.250), (x, 0.255, 0.300), 12, EGLOW)
        p.cyl_axis(0.045, (x, 0.248, -0.270), (x, 0.248, -0.230), 12, ALLOY, chamfer=0.008)
        p.cyl_axis(0.045, (x, 0.248, 0.280), (x, 0.248, 0.320), 12, ALLOY, chamfer=0.008)
    p.box((0, 0.262, 0.025), (0.300, 0.020, 0.520), STEEL, "hi")
    # barrel cluster: three barrels around the axis, coil core, shrouds
    p.cyl(0.130, 0.480, 1.050, 24, EGLOW)                                              # coil core
    for k in range(5):
        p.cyl(0.175, 0.520 + k * 0.11, 0.560 + k * 0.11, 28, ALLOY, chamfer=0.010)      # magnetic rings
    for k in range(3):
        a = math.radians(90 + 120 * k)
        x, y = 0.105 * math.cos(a), 0.105 * math.sin(a)
        p.cyl(0.062, 0.480, 1.640, 18, STEEL, t=(x, y, 0), chamfer=0.006)
        p.cyl(0.030, 1.640, 1.660, 14, CAVITY, t=(x, y, 0))
    p.cyl(0.250, 1.100, 1.300, 30, SHELL, chamfer=0.030)                               # front shroud
    p.ridges((0, 0.250, 1.120), (0, 0.250, 1.280), 6, (0.200, 0.010, 0.012), STEEL)
    p.cyl(0.235, 1.500, 1.640, 30, STEEL, chamfer=0.025)                               # muzzle ring
    p.cyl(0.165, 1.630, 1.645, 26, EGLOW)                                              # muzzle core
    p.tube_ring(0.205, 0.018, 30, 8, ALLOY, t=(0, 0, 1.645))
    for k in range(8):
        a = math.radians(22.5 + 45 * k)
        p.box((0.236 * math.cos(a), 0.236 * math.sin(a), 1.570), (0.020, 0.020, 0.080), CAVITY, "hi", M=rot_z(a))
    # struts from the shroud to the housing
    for sx in (-1, 1):
        p.cyl_axis(0.030, (sx * 0.170, -0.120, 0.450), (sx * 0.150, -0.120, 1.150), 10, ALLOY, chamfer=0.006)
    p.empty("muzzle", (0, 0, 1.680))
    return p


# ============================================================================ Guardian folding arm blade (right forearm)
def guardian_blade_mount():
    """Static sheath block along the outer forearm. Origin = hinge (wrist end), forearm runs towards -z."""
    p = Part("guardian_blade_mount")
    p.loft([(-0.700, chamfer_rect(0.090, -0.170, 0.150, 0.030, 0.040)), (-0.660, chamfer_rect(0.110, -0.200, 0.180, 0.035, 0.050)),
            (-0.080, chamfer_rect(0.110, -0.200, 0.180, 0.035, 0.050)), (-0.030, chamfer_rect(0.090, -0.170, 0.150, 0.030, 0.040))], SHELL)
    p.ridges((0.112, 0.000, -0.600), (0.112, 0.000, -0.160), 8, (0.008, 0.200, 0.016), STEEL)
    p.box((0.114, -0.150, -0.380), (0.008, 0.040, 0.300), HAZARD, "hi")
    # hinge knuckles
    Mx = basis_from_z((1, 0, 0), (0, 1, 0))
    for sx in (-1, 1):
        p.cyl(0.085, 0.0, 0.040, 20, ALLOY, M=Mx, t=(sx * 0.050 - 0.020, 0, 0), chamfer=0.008)
    p.cyl(0.040, -0.090, 0.090, 14, STEEL, M=Mx)
    # actuator piston
    p.cyl_axis(0.030, (0, 0.140, -0.560), (0, 0.090, -0.060), 12, ALLOY, chamfer=0.006)
    p.cyl_axis(0.045, (0, 0.145, -0.600), (0, 0.130, -0.360), 12, STEEL, chamfer=0.008)
    p.box((0.112, 0.090, -0.250), (0.010, 0.030, 0.120), EGLOW)
    return p


def guardian_blade():
    """The blade itself, hinged at the origin around local x; deployed along +z (past the fist), edge towards -y."""
    p = Part("guardian_blade")
    Mx = basis_from_z((1, 0, 0), (0, 1, 0))
    p.cyl(0.075, -0.030, 0.030, 20, STEEL, M=Mx, t=(-0.030, 0, 0), chamfer=0.010)
    st = []
    for z in np.linspace(0.050, 1.400, 18):
        u = (z - 0.05) / 1.35
        ys = 0.100 - 0.020 * u
        ye = -0.300 - 0.090 * math.sin(math.pi * min(1.0, u * 1.1)) + 0.090 * u
        st.append((z, ys, ye))
    for z, f in ((1.470, 0.66), (1.530, 0.40), (1.580, 0.16)):
        ys = 0.070 - (1 - f) * 0.090
        ye = -0.150 + (1 - f) * 0.170
        st.append((z, ys, ye))
    blade_loft(p, st, BLADE, EGLOW, 0.028, 0.28, 0.06, 0.018, t=(-0.030, 0, 0), edge=0.016)
    # tang plate with bolts
    p.box((-0.030, -0.040, 0.120), (0.060, 0.200, 0.140), STEEL, chamfer=0.012)
    for z in (0.080, 0.160):
        for sy in (-0.09, 0.02):
            p.rivet((0.001, sy, z), (1, 0, 0), 0.014, 0.008, ALLOY)
            p.rivet((-0.061, sy, z), (-1, 0, 0), 0.014, 0.008, ALLOY)
    p.empty("tip", (-0.030, -0.04, 1.59))
    return p
