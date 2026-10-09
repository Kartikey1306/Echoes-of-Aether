"""Compatibility check of rebuilt assets against the pre-upgrade baseline (out/baseline/assets.json).

  python3 check_regression.py [names or globs...]

The game's zone code places props by name and relies on: size (manifest), pivot, colliders, material slot names
(code swaps 'emit_*', 'emit_violet', 'aether' slots at runtime) and some documented feature positions. For every
baseline asset that was rebuilt this reports:
  ERROR  size differs by > 0.02 m on any axis, pivot changed, collider list changed, asset missing
  WARN   a baseline material slot disappeared, boundsCenter moved > 0.05 m, extra metadata keys dropped
Exit code 1 when any ERROR.
"""
import fnmatch
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import envpaths  # noqa: E402


def colliders_equal(a, b, tol=0.011):
    if isinstance(a, str) or isinstance(b, str):
        return a == b
    if a is None or b is None:
        return a == b
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if isinstance(x, str) or isinstance(y, str):
            if x != y:
                return False
            continue
        if x.get("type") != y.get("type"):
            return False
        for k in set(x) | set(y):
            vx, vy = x.get(k), y.get(k)
            if isinstance(vx, list) and isinstance(vy, list):
                if len(vx) != len(vy) or any(abs(p - q) > tol for p, q in zip(vx, vy) if isinstance(p, (int, float)) and isinstance(q, (int, float))):
                    return False
            elif isinstance(vx, (int, float)) and isinstance(vy, (int, float)):
                if abs(vx - vy) > tol:
                    return False
            elif k != "note" and vx != vy:
                return False
    return True


def main():
    pats = sys.argv[1:]
    base = json.load(open(os.path.join(envpaths.STATE, "baseline", "assets.json")))
    cur = json.load(open(os.path.join(envpaths.STATE, "assets.json")))
    errs = warns = 0
    for name, b in sorted(base.items()):
        if pats and not any(fnmatch.fnmatch(name, p) for p in pats):
            continue
        c = cur.get(name)
        if c is None:
            print(f"ERROR {name}: missing"); errs += 1
            continue
        msgs = []
        ds = [abs(x - y) for x, y in zip(b["size"], c["size"])]
        if max(ds) > 0.02:
            msgs.append(("ERROR", f"size {c['size']} != baseline {b['size']}"))
        if b.get("pivot") != c.get("pivot"):
            msgs.append(("ERROR", f"pivot {c.get('pivot')} != {b.get('pivot')}"))
        if not colliders_equal(b.get("colliders"), c.get("colliders")):
            msgs.append(("ERROR", f"colliders changed: {c.get('colliders')} != {b.get('colliders')}"))
        lost = [m for m in b["materials"] if m not in c["materials"]]
        if lost:
            msgs.append(("WARN", f"material slots removed: {lost}"))
        dc = max(abs(x - y) for x, y in zip(b["boundsCenter"], c["boundsCenter"]))
        if dc > 0.05:
            msgs.append(("WARN", f"boundsCenter moved {dc:.3f} m ({c['boundsCenter']} vs {b['boundsCenter']})"))
        skip = {"tris", "meshes", "materials", "size", "boundsCenter", "colliders", "notes", "lodTransitions", "fbxCheck"}
        dropped = [k for k in b if k not in c and k not in skip]
        if dropped:
            msgs.append(("WARN", f"metadata keys dropped: {dropped}"))
        t0b, t0c = b["tris"]["LOD0"], c["tris"]["LOD0"]
        for lvl, m in msgs:
            print(f"{lvl} {name}: {m}")
            if lvl == "ERROR":
                errs += 1
            else:
                warns += 1
        if not msgs and pats:
            print(f"ok    {name}: tris {t0b} -> {t0c}")
    print(f"[regression] {errs} errors, {warns} warnings")
    sys.exit(1 if errs else 0)


if __name__ == "__main__":
    main()
