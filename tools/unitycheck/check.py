#!/usr/bin/env python3
"""Offline C# compile check for the Unity project, using the editor's bundled Roslyn and reference DLLs.

Re-implements enough of Unity's script compilation pipeline (asmdef discovery, GUID references, define
constraints, version defines, precompiled references, Editor folders) to compile packages and the project
without opening the editor (useful before the editor licence is activated, and much faster).

usage: [UNITYCHECK_OUT=/private/dir] python3 tools/unitycheck/check.py [--player] [--only Assembly-CSharp]
  --player   also compile project runtime code without UNITY_EDITOR (catches editor-only API in player code)
"""
import json, os, re, subprocess, sys, hashlib, glob

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PROJ = os.path.join(ROOT, "unity", "EchoesOfAether")
EDITOR = "/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents"
SCRIPTING = os.path.join(EDITOR, "Resources", "Scripting")
DOTNET = os.path.join(SCRIPTING, "NetCoreRuntime", "dotnet")
CSC = os.path.join(SCRIPTING, "DotNetSdkRoslyn", "csc.dll")
BUILTIN = os.path.join(EDITOR, "Resources", "PackageManager", "BuiltInPackages")
PKGS = os.path.join(os.path.dirname(__file__), "pkgs")
# Set UNITYCHECK_OUT to a private directory when several people/agents run the checker at the same time.
OUT = os.environ.get("UNITYCHECK_OUT") or os.path.join(os.path.dirname(__file__), "out")
os.makedirs(OUT, exist_ok=True)

UNITY_VERSION = (6000, 3, 25)


def unity_defines(editor=True):
    d = ["UNITY_6000_3_25", "UNITY_6000_3", "UNITY_6000", "UNITY_64", "UNITY_STANDALONE_OSX", "UNITY_STANDALONE",
         "PLATFORM_STANDALONE_OSX", "PLATFORM_STANDALONE", "ENABLE_MONO", "ENABLE_INPUT_SYSTEM", "ENABLE_LEGACY_INPUT_MANAGER",
         "NET_STANDARD_2_0", "NET_STANDARD_2_1", "NET_STANDARD", "NETSTANDARD2_1", "NETSTANDARD", "CSHARP_7_3_OR_NEWER",
         "ENABLE_UNITYWEBREQUEST", "ENABLE_PHYSICS", "ENABLE_AUDIO", "ENABLE_PROFILER", "UNITY_ASSERTIONS", "ENABLE_CLOUD_SERVICES",
         "ENABLE_MANAGED_JOBS", "ENABLE_MANAGED_TRANSFORM_JOBS", "ENABLE_MANAGED_ANIMATION_JOBS", "ENABLE_BURST_AOT", "UNITY_PHYSICS"]
    for y in range(5, 7):
        for m in range(0, 7):
            d.append(f"UNITY_{y}_{m}_OR_NEWER")
    for y in range(2017, 2024):
        for m in range(1, 5):
            d.append(f"UNITY_{y}_{m}_OR_NEWER")
    for m in range(0, 4):
        d.append(f"UNITY_6000_{m}_OR_NEWER")
    if editor:
        d += ["UNITY_EDITOR", "UNITY_EDITOR_64", "UNITY_EDITOR_OSX", "UNITY_INCLUDE_TESTS", "DEBUG", "TRACE"]
    # We compile against the editor's engine DLLs, whose NativeArray API carries AtomicSafetyHandle
    # (as in a development player), so collections safety checks stay on in both configurations.
    d.append("ENABLE_UNITY_COLLECTIONS_CHECKS")
    return d


def load_json(p):
    with open(p, encoding="utf-8-sig") as f:
        txt = f.read()
    txt = re.sub(r",(\s*[}\]])", r"\1", txt)
    return json.loads(txt)


def guid_of(path):
    meta = path + ".meta"
    if os.path.isfile(meta):
        m = re.search(r"guid:\s*([0-9a-f]+)", open(meta).read())
        if m:
            return m.group(1)
    return None


def parse_version(v):
    m = re.match(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", v.strip())
    return tuple(int(x or 0) for x in m.groups()) if m else (0, 0, 0)


def version_matches(expr, have):
    expr = expr.strip()
    if not expr:
        return True
    h = parse_version(have)
    if expr[0] in "[(":
        lo_inc, hi_inc = expr[0] == "[", expr[-1] == "]"
        lo, hi = (x.strip() for x in expr[1:-1].split(","))
        if lo and (h < parse_version(lo) if lo_inc else h <= parse_version(lo)):
            return False
        if hi and (h > parse_version(hi) if hi_inc else h >= parse_version(hi)):
            return False
        return True
    return h >= parse_version(expr)


class Asm:
    def __init__(self, name, root, data, path, package=None):
        self.name, self.root, self.data, self.path, self.package = name, root, data, path, package
        self.files = []
        self.refs = []


def package_roots():
    roots = {}
    man = load_json(os.path.join(PROJ, "Packages", "manifest.json"))["dependencies"]
    wanted = set(man.keys())
    # Transitive deps.
    def pkg_dir(n):
        for base in (PKGS, BUILTIN):
            d = os.path.join(base, n)
            if os.path.isfile(os.path.join(d, "package.json")):
                return d
        return None
    todo = list(wanted)
    while todo:
        n = todo.pop()
        d = pkg_dir(n)
        if not d or n in roots:
            continue
        roots[n] = d
        for dep in load_json(os.path.join(d, "package.json")).get("dependencies", {}):
            if dep not in roots:
                todo.append(dep)
    return roots


def discover():
    pkgs = package_roots()
    versions = {n: load_json(os.path.join(d, "package.json"))["version"] for n, d in pkgs.items()}
    versions["Unity"] = "6000.3.25"
    asms, by_guid = {}, {}
    precompiled = {}
    analyzers = []
    for n, d in list(pkgs.items()) + [("__project__", os.path.join(PROJ, "Assets"))]:
        for dp, dns, fns in os.walk(d):
            dns[:] = [x for x in dns if not x.startswith(".") and not x.endswith("~") and x not in ("Samples", "Documentation~")]
            for f in fns:
                p = os.path.join(dp, f)
                if f.endswith(".asmdef"):
                    data = load_json(p)
                    a = Asm(data["name"], dp, data, p, n)
                    asms[a.name] = a
                    g = guid_of(p)
                    if g:
                        by_guid[g] = a.name
                elif f.endswith(".dll"):
                    meta = p + ".meta"
                    mt = open(meta).read() if os.path.isfile(meta) else ""
                    if "RoslynAnalyzer" in mt:
                        analyzers.append(p)
                    else:
                        auto = "isExplicitlyReferenced: 1" not in mt
                        excluded_editor_only = "Exclude Editor: 1" in mt
                        precompiled[f] = (p, auto, n)
    return pkgs, versions, asms, by_guid, precompiled, analyzers


def assign_files(asms):
    roots = sorted(asms.values(), key=lambda a: -len(a.root))
    proj_assets = os.path.join(PROJ, "Assets")
    runtime, editor = Asm("Assembly-CSharp", proj_assets, {}, None, "__project__"), Asm("Assembly-CSharp-Editor", proj_assets, {}, None, "__project__")
    dirs = set()
    for a in asms.values():
        dirs.add(a.root)
    for base in set([a.root for a in asms.values()] + [proj_assets]):
        pass
    all_roots = [a.root for a in roots]
    for dp, dns, fns in os.walk(os.path.dirname(PKGS)):
        break
    for a in asms.values():
        pass
    # Walk each candidate tree once.
    scan = [os.path.join(PKGS)] + [BUILTIN] + [proj_assets]
    seen = set()
    for top in [a.root for a in asms.values()] + [proj_assets]:
        for dp, dns, fns in os.walk(top):
            dns[:] = [x for x in dns if not x.startswith(".") and not x.endswith("~")]
            for f in fns:
                if not f.endswith(".cs"):
                    continue
                p = os.path.join(dp, f)
                if p in seen:
                    continue
                seen.add(p)
                owner = None
                for a in roots:
                    if p.startswith(a.root + os.sep):
                        owner = a
                        break
                if owner is None:
                    if not p.startswith(proj_assets):
                        continue
                    parts = os.path.relpath(p, proj_assets).split(os.sep)
                    (editor if "Editor" in parts[:-1] else runtime).files.append(p)
                else:
                    owner.files.append(p)
    return runtime, editor


def enabled(a, defines, versions, editor_cfg):
    d = a.data
    inc = d.get("includePlatforms", [])
    exc = d.get("excludePlatforms", [])
    if inc and "Editor" not in inc and editor_cfg:
        pass
    if inc and inc == ["Editor"] and not editor_cfg:
        return False
    if "Editor" in exc and editor_cfg:
        return False
    vd = version_defines(a, versions)
    for c in d.get("defineConstraints", []):
        neg = c.startswith("!")
        sym = c[1:] if neg else c
        have = sym in defines or sym in vd
        if neg == have:
            return False
    return True


def version_defines(a, versions):
    out = []
    for v in a.data.get("versionDefines", []):
        n = v.get("name")
        if n in versions and version_matches(v.get("expression", ""), versions[n]):
            out.append(v["define"])
    return out


def engine_refs(editor_cfg):
    refs = glob.glob(os.path.join(SCRIPTING, "Managed", "UnityEngine", "UnityEngine*.dll")) + [os.path.join(SCRIPTING, "Managed", "UnityEngine.dll")]
    if editor_cfg:
        refs += glob.glob(os.path.join(SCRIPTING, "Managed", "UnityEngine", "UnityEditor*.dll"))
        refs += [os.path.join(SCRIPTING, "Managed", "UnityEditor.Graphs.dll"), os.path.join(SCRIPTING, "Managed", "UnityEditor.dll")]
    refs += [os.path.join(SCRIPTING, "NetStandard", "ref", "2.1.0", "netstandard.dll")]
    refs += glob.glob(os.path.join(SCRIPTING, "NetStandard", "compat", "2.1.0", "shims", "netfx", "*.dll"))
    refs += glob.glob(os.path.join(SCRIPTING, "NetStandard", "compat", "2.1.0", "shims", "netstandard", "*.dll"))
    refs += glob.glob(os.path.join(SCRIPTING, "NetStandard", "Extensions", "2.0.0", "*.dll"))
    seen, out = set(), []
    for r in refs:
        b = os.path.basename(r)
        if b not in seen:
            seen.add(b); out.append(r)
    return out
    return refs


def compile_asm(a, refs, defines, analyzers, unsafe, label):
    out = os.path.join(OUT, label, a.name + ".dll")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if not a.files:
        return out, True, ""
    rsp = os.path.join(OUT, label, a.name + ".rsp")
    with open(rsp, "w") as f:
        f.write("-nologo\n-target:library\n-nostdlib\n-noconfig\n-langversion:9.0\n-deterministic\n-debug-\n-optimize-\n")
        f.write("-nowarn:0169,0649,0414,0618,1701,1702,0067,0219,0168,8632,0105,0108,0114,1998,0162,0414,0612,0436\n")
        if unsafe:
            f.write("-unsafe\n")
        f.write(f'-out:"{out}"\n')
        for r in refs:
            f.write(f'-r:"{r}"\n')
        for an in analyzers:
            f.write(f'-analyzer:"{an}"\n')
        f.write("-define:" + ";".join(sorted(set(defines))) + "\n")
        for src in sorted(a.files):
            f.write(f'"{src}"\n')
    r = subprocess.run([DOTNET, CSC, "@" + rsp], capture_output=True, text=True)
    ok = r.returncode == 0
    return out, ok, r.stdout + r.stderr


def main():
    editor_cfg = True
    player = "--player" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    quiet_pkgs = "--verbose" not in sys.argv
    pkgs, versions, asms, by_guid, precompiled, analyzers = discover()
    runtime, editor = assign_files(asms)
    configs = [("editor", True)] + ([("player", False)] if player else [])
    total_err = 0
    for label, ed in configs:
        defines_base = unity_defines(ed)
        built = {}
        status = {}
        pending = {n: a for n, a in asms.items() if enabled(a, defines_base, versions, ed) and a.files and ("Tests" not in n or n.startswith("EOA"))}
        project = [runtime] + ([editor] if ed else [])
        def ref_names(a):
            # "Unity.ugui" maps to the runtime uGUI/TMP assemblies; editor variants only for editor-only assemblies
            # (otherwise runtime packages pick up cycles through TMP.Editor and build in the wrong order).
            editor_only = a.data.get("includePlatforms") == ["Editor"]
            alias = ["UnityEngine.UI", "Unity.TextMeshPro"] + (["UnityEditor.UI", "Unity.TextMeshPro.Editor"] if ed and editor_only else [])
            names = []
            for r in a.data.get("references", []):
                n = by_guid.get(r[5:], r) if r.startswith("GUID:") else r
                names += alias if n == "Unity.ugui" else [n]
            return names
        def precompiled_refs(a):
            out = []
            explicit = a.data.get("precompiledReferences", [])
            override = a.data.get("overrideReferences", False)
            for f, (p, auto, pkg) in precompiled.items():
                if f in explicit or (not override and auto):
                    if "Test" in f and "nunit" not in f.lower():
                        continue
                    out.append(p)
            return out
        order = []
        visiting = set()
        def visit(n):
            if n in built or n in visiting or n not in pending:
                return
            visiting.add(n)
            for r in ref_names(pending[n]):
                visit(r)
            order.append(n)
            built[n] = None
        for first in ("UnityEngine.UI", "UnityEditor.UI"):
            visit(first)
        for n in list(pending):
            visit(n)
        dlls = {}
        for n in order:
            a = pending[n]
            refs = engine_refs(ed or a.data.get("includePlatforms") == ["Editor"]) + precompiled_refs(a)
            refs += [dlls[r] for r in ref_names(a) if r in dlls]
            # Unity 6.3 treats uGUI as an engine-level reference for every assembly.
            for implicit in ("UnityEngine.UI", "UnityEditor.UI"):
                if implicit in dlls and implicit != n and (implicit == "UnityEngine.UI" or ed):
                    refs.append(dlls[implicit])
            defs = defines_base + version_defines(a, versions)
            path, ok, log = compile_asm(a, refs, defs, analyzers if "Unity.Collections" in n else [], a.data.get("allowUnsafeCode", False), label)
            status[n] = ok
            if ok:
                dlls[n] = path
            elif not quiet_pkgs or a.package == "__project__":
                print(f"[{label}] FAILED {n}\n" + "\n".join(log.splitlines()[:40]))
            else:
                errs = [l for l in log.splitlines() if "error" in l][:5]
                print(f"[{label}] package assembly failed: {n} ({len(errs)}+ errors) e.g. {errs[:2]}")
        # Project assemblies (no asmdef): reference everything that compiled and is auto-referenced.
        all_pkg = [p for n, p in dlls.items() if pending[n].data.get("autoReferenced", True) and pending[n].package != "__project__" or pending[n].package == "__project__"]
        for a in project:
            if only and a.name != only:
                continue
            refs = engine_refs(ed or a is editor) + [p for f, (p, auto, pkg) in precompiled.items() if auto and "nunit" not in f.lower() and "Mono.Cecil" not in f]
            refs += all_pkg
            if a is editor:
                refs.append(os.path.join(OUT, label, "Assembly-CSharp.dll"))
            path, ok, log = compile_asm(a, refs, defines_base, [], True, label)
            errs = [l for l in log.splitlines() if ": error " in l]
            warns = [l for l in log.splitlines() if ": warning " in l]
            print(f"[{label}] {a.name}: {'OK' if ok else 'FAILED'} ({len(a.files)} files, {len(errs)} errors, {len(warns)} warnings)")
            for l in errs[:200]:
                print("  " + l.replace(PROJ + "/", ""))
            total_err += len(errs)
        failed_pkgs = [n for n, ok in status.items() if not ok]
        if failed_pkgs:
            print(f"[{label}] package assemblies that failed (stubbed out): {failed_pkgs}")
    sys.exit(1 if total_err else 0)


if __name__ == "__main__":
    main()
