"""Tiny DSL for building procedural shader node graphs that tile perfectly over UV [0,1)^2.

Tiling trick: UV is mapped onto a 4D torus  (Ru cos 2πu, Ru sin 2πu, Rv cos 2πv, Rv sin 2πv) and fed to the
4D Noise / Voronoi textures, so every noise is exactly periodic over one UV tile. With R = f / 2π and Scale 1,
`f` is the number of noise features per tile. Regular patterns (tiles, grids, ribs) use fract(u * n) with
integer n so they tile too.

Float sockets are wrapped in `S`, which overloads arithmetic to emit Math nodes.
"""
import math

import bpy

TAU = math.tau


class S:
    """Float socket wrapper with arithmetic operator overloading."""

    def __init__(self, nb, sock):
        self.nb = nb
        self.s = sock

    def _op(self, op, other=None, rev=False):
        return self.nb.math(op, other, self) if rev else self.nb.math(op, self, other)

    def __add__(self, o): return self._op("ADD", o)
    def __radd__(self, o): return self._op("ADD", o, True)
    def __sub__(self, o): return self._op("SUBTRACT", o)
    def __rsub__(self, o): return self._op("SUBTRACT", o, True)
    def __mul__(self, o): return self._op("MULTIPLY", o)
    def __rmul__(self, o): return self._op("MULTIPLY", o, True)
    def __truediv__(self, o): return self._op("DIVIDE", o)
    def __rtruediv__(self, o): return self._op("DIVIDE", o, True)
    def __pow__(self, o): return self._op("POWER", o)
    def __neg__(self): return self.nb.math("MULTIPLY", self, -1.0)

    def clamp(self, lo=0.0, hi=1.0):
        if lo == 0.0 and hi == 1.0:
            return self.nb.math("ADD", self, 0.0, clamp=True)
        return self.nb.math("MINIMUM", self.nb.math("MAXIMUM", self, lo), hi)


class NB:
    """Node builder bound to one material node tree."""

    def __init__(self, nt):
        self.nt = nt
        self.nodes = nt.nodes
        self.links = nt.links
        tc = self.nodes.new("ShaderNodeTexCoord")
        sep = self.nodes.new("ShaderNodeSeparateXYZ")
        self.links.new(tc.outputs["UV"], sep.inputs[0])
        self.u = S(self, sep.outputs[0])
        self.v = S(self, sep.outputs[1])
        a_u = self.u * TAU
        a_v = self.v * TAU
        self.cu, self.su = self.math("COSINE", a_u), self.math("SINE", a_u)
        self.cv, self.sv = self.math("COSINE", a_v), self.math("SINE", a_v)
        self._torus_cache = {}

    # ------------------------------------------------------------------ plumbing
    def _sock(self, x):
        return x.s if isinstance(x, S) else x

    def link_or_set(self, inp, val):
        if isinstance(val, S):
            self.links.new(val.s, inp)
        elif isinstance(val, bpy.types.NodeSocket):
            self.links.new(val, inp)
        elif val is not None:
            inp.default_value = val

    def math(self, op, a, b=None, c=None, clamp=False):
        n = self.nodes.new("ShaderNodeMath")
        n.operation = op
        n.use_clamp = clamp
        self.link_or_set(n.inputs[0], a)
        if b is not None:
            self.link_or_set(n.inputs[1], b)
        if c is not None:
            self.link_or_set(n.inputs[2], c)
        return S(self, n.outputs[0])

    def const(self, x):
        n = self.nodes.new("ShaderNodeValue")
        n.outputs[0].default_value = x
        return S(self, n.outputs[0])

    # ------------------------------------------------------------------ helpers
    def fract(self, x): return self.math("FRACT", x)
    def floor(self, x): return self.math("FLOOR", x)
    def absf(self, x): return self.math("ABSOLUTE", x)
    def minf(self, a, b): return self.math("MINIMUM", a, b)
    def maxf(self, a, b): return self.math("MAXIMUM", a, b)
    def sin(self, x): return self.math("SINE", x)
    def smin(self, a, b, k): return self.math("SMOOTH_MIN", a, b, k)
    def smax(self, a, b, k): return self.math("SMOOTH_MAX", a, b, k)
    def lt(self, a, b): return self.math("LESS_THAN", a, b)
    def gt(self, a, b): return self.math("GREATER_THAN", a, b)
    def mod(self, a, b): return self.math("FLOORED_MODULO", a, b)

    def lerp(self, a, b, t):
        return a + (b - a) * t if isinstance(a, S) else self.math("ADD", self.math("MULTIPLY", self.math("SUBTRACT", b, a), t), a)

    def maprange(self, x, a, b, c=0.0, d=1.0, clamp=True, interp="LINEAR"):
        n = self.nodes.new("ShaderNodeMapRange")
        n.data_type = "FLOAT"
        n.interpolation_type = interp
        n.clamp = clamp
        self.link_or_set(n.inputs["Value"], x)
        n.inputs["From Min"].default_value = a
        n.inputs["From Max"].default_value = b
        n.inputs["To Min"].default_value = c
        n.inputs["To Max"].default_value = d
        return S(self, n.outputs["Result"])

    def smooth(self, x, a, b):
        """smoothstep(a, b, x) (works for a > b too)."""
        if a > b:
            return 1.0 - self.maprange(x, b, a, interp="SMOOTHSTEP")
        return self.maprange(x, a, b, interp="SMOOTHSTEP")

    # ------------------------------------------------------------------ tileable noise
    def torus(self, fu, fv=None, seed=0):
        fv = fu if fv is None else fv
        key = (fu, fv, seed)
        if key in self._torus_cache:
            return self._torus_cache[key]
        ru, rv = fu / TAU, fv / TAU
        o = [((seed * 7919 + k * 104729) % 1000) * 0.137 + 3.0 * k for k in range(4)]
        x = self.cu * ru + o[0]
        y = self.su * ru + o[1]
        z = self.cv * rv + o[2]
        w = self.sv * rv + o[3]
        comb = self.nodes.new("ShaderNodeCombineXYZ")
        for i, s in enumerate((x, y, z)):
            self.links.new(s.s, comb.inputs[i])
        res = (comb.outputs[0], w)
        self._torus_cache[key] = res
        return res

    def noise(self, f, detail=4.0, rough=0.5, seed=0, fv=None, kind="FBM", lac=2.0, distortion=0.0, offset=0.0, gain=1.0):
        """Tileable 4D noise, ~[0,1] (centred 0.5 for FBM). `f` features per tile along U (and V unless fv)."""
        vec, w = self.torus(f, fv, seed)
        n = self.nodes.new("ShaderNodeTexNoise")
        n.noise_dimensions = "4D"
        n.noise_type = kind
        n.normalize = True
        self.links.new(vec, n.inputs["Vector"])
        self.links.new(w.s, n.inputs["W"])
        n.inputs["Scale"].default_value = 1.0
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        n.inputs["Lacunarity"].default_value = lac
        n.inputs["Distortion"].default_value = distortion
        if kind != "FBM":
            n.inputs["Offset"].default_value = offset
            n.inputs["Gain"].default_value = gain
        return S(self, n.outputs["Fac"])

    def voronoi(self, f, seed=0, feature="F1", out="Distance", metric="EUCLIDEAN", rand=1.0, fv=None, smooth=1.0):
        vec, w = self.torus(f, fv, seed)
        n = self.nodes.new("ShaderNodeTexVoronoi")
        n.voronoi_dimensions = "4D"
        n.feature = feature
        n.distance = metric
        self.links.new(vec, n.inputs["Vector"])
        self.links.new(w.s, n.inputs["W"])
        n.inputs["Scale"].default_value = 1.0
        n.inputs["Randomness"].default_value = rand
        if feature == "SMOOTH_F1":
            n.inputs["Smoothness"].default_value = smooth
        if out == "Color":
            sep = self.nodes.new("ShaderNodeSeparateColor")
            self.links.new(n.outputs["Color"], sep.inputs[0])
            return S(self, sep.outputs[0])
        return S(self, n.outputs[out])

    def cell_rand(self, nu, nv, seed=0, ou=None, ov=None):
        """Random value in [0,1) per integer grid cell of an nu x nv grid over the tile (tileable)."""
        cu = self.mod(self.floor(self.u * nu if ou is None else self.u * nu + ou), nu)
        cv = self.mod(self.floor(self.v * nv if ov is None else self.v * nv + ov), nv)
        comb = self.nodes.new("ShaderNodeCombineXYZ")
        self.links.new(cu.s, comb.inputs[0])
        self.links.new(cv.s, comb.inputs[1])
        comb.inputs[2].default_value = seed * 1.618 + 0.5
        wn = self.nodes.new("ShaderNodeTexWhiteNoise")
        wn.noise_dimensions = "3D"
        self.links.new(comb.outputs[0], wn.inputs["Vector"])
        return S(self, wn.outputs["Value"])

    def grid_dist(self, x, n):
        """Distance (in tile units) from coordinate x to the nearest of n evenly spaced grid lines."""
        g = self.fract(x * n)
        return self.minf(g, 1.0 - g) / n

    # ------------------------------------------------------------------ colours
    def rgb(self, c):
        n = self.nodes.new("ShaderNodeRGB")
        n.outputs[0].default_value = (c[0], c[1], c[2], 1.0)
        return n.outputs[0]

    def mixc(self, a, b, t):
        """Mix two colours (tuples or colour sockets) by float t."""
        n = self.nodes.new("ShaderNodeMix")
        n.data_type = "RGBA"
        n.blend_type = "MIX"
        fac = [i for i in n.inputs if i.identifier == "Factor_Float"][0]
        ia = [i for i in n.inputs if i.identifier == "A_Color"][0]
        ib = [i for i in n.inputs if i.identifier == "B_Color"][0]
        self.link_or_set(fac, t)
        for inp, val in ((ia, a), (ib, b)):
            if isinstance(val, tuple):
                inp.default_value = (val[0], val[1], val[2], 1.0)
            else:
                self.links.new(val, inp)
        return [o for o in n.outputs if o.identifier == "Result_Color"][0]

    def mulc(self, c, f):
        """Colour * float."""
        n = self.nodes.new("ShaderNodeMix")
        n.data_type = "RGBA"
        n.blend_type = "MULTIPLY"
        fac = [i for i in n.inputs if i.identifier == "Factor_Float"][0]
        fac.default_value = 1.0
        ia = [i for i in n.inputs if i.identifier == "A_Color"][0]
        ib = [i for i in n.inputs if i.identifier == "B_Color"][0]
        if isinstance(c, tuple):
            ia.default_value = (c[0], c[1], c[2], 1.0)
        else:
            self.links.new(c, ia)
        comb = self.nodes.new("ShaderNodeCombineColor")
        for i in range(3):
            self.link_or_set(comb.inputs[i], f)
        self.links.new(comb.outputs[0], ib)
        return [o for o in n.outputs if o.identifier == "Result_Color"][0]

    def gray(self, f):
        comb = self.nodes.new("ShaderNodeCombineColor")
        for i in range(3):
            self.link_or_set(comb.inputs[i], f)
        return comb.outputs[0]

    def pack3(self, a, b, c):
        comb = self.nodes.new("ShaderNodeCombineColor")
        for i, x in enumerate((a, b, c)):
            self.link_or_set(comb.inputs[i], x)
        return comb.outputs[0]

    def ramp(self, x, stops):
        """Colour ramp from [(pos, (r,g,b)), ...]; returns colour socket."""
        n = self.nodes.new("ShaderNodeValToRGB")
        els = n.color_ramp.elements
        while len(els) > len(stops):
            els.remove(els[-1])
        while len(els) < len(stops):
            els.new(0.5)
        for e, (p, c) in zip(els, stops):
            e.position = p
            e.color = (c[0], c[1], c[2], 1.0)
        self.link_or_set(n.inputs["Fac"], x)
        return n.outputs["Color"]
