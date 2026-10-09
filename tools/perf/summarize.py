#!/usr/bin/env python3
"""Print a compact table from a benchmark report (and optionally compare two)."""
import json, sys
def load(p): return json.load(open(p))
def row(s):
    if not s: return "-"
    return (f"{s['name'][:34]:34} {s['frames']:6} {s['avgFps']:7.1f} {s['low1Fps']:6.1f} {s['low01Fps']:6.1f} {s['p99Ms']:6.1f} {s['maxMs']:7.1f} "
            f"{s['spikes33']:4} {s['spikes50']:4} {s['cpuMainMs']:6.2f} {s['renderThreadMs']:6.2f} {s['gpuMs']:6.2f} {s['gcBytesPerFrame']:8.0f} {s['gcFramesPct']:5.1f} "
            f"{s['drawCalls']:6.0f} {s['setPass']:5.0f} {s['batches']:6.0f} {s['triangles']/1e6:6.2f}")
hdr = (f"{'scenario':34} {'frames':>6} {'avgFps':>7} {'1%low':>6} {'.1%low':>6} {'p99ms':>6} {'maxMs':>7} {'>33':>4} {'>50':>4} {'cpuMs':>6} {'rtMs':>6} {'gpuMs':>6} {'gcB/f':>8} {'gc%':>5} {'draws':>6} {'setP':>5} {'batch':>6} {'Mtris':>6}")
for p in [a for a in sys.argv[1:] if not a.startswith('-')]:
    r = load(p)
    print(f"== {p}: ok={r['ok']} screen={r['screen']} camera={r['camera']} preset={r['preset']} frames={r['frames']} {r['seconds']}s gpuTiming={r['gpuTiming']} recorders={r['recorders']}")
    print(hdr)
    for s in r['scenarios']: print(row(s))
    print("-- summary")
    for k, s in r['summary'].items(): print(row(s))
    print("-- spike causes", r['spikeCauses'])
    print("-- loads")
    for l in r['loads']:
        secs = sorted(l['sections'], key=lambda x: -x['ms'])[:6]
        print(f"  {l['zone']:9} {l['seconds']:6.2f}s  " + ", ".join(f"{x['section']} {x['ms']:.0f}" for x in secs))
    if r['errors']: print("-- errors", len(r['errors']), r['errors'][:3])
    if r.get('sweep'):
        print("-- settings sweep (avg over 2.5 s at a fixed view)")
        base = {}
        for s in r['sweep']:
            if s['config'] == 'high': base[s['view']] = s
            b = base.get(s['view'])
            d = f" Δcpu {s['cpuMainMs']-b['cpuMainMs']:+6.2f} Δgpu {s['gpuMs']-b['gpuMs']:+6.2f}" if b and s is not b else ""
            print(f"  {s['view'][:22]:22} {s['config']:15} fps {s['avgFps']:6.1f} ms {s['avgMs']:6.2f} cpu {s['cpuMainMs']:6.2f} gpu {s['gpuMs']:6.2f} draws {s['drawCalls']:6.0f} setp {s['setPass']:4.0f}{d}")
    if r.get('census') and '-v' in sys.argv:
        for c in r['census']:
            print(f"-- census {c['label']}: enabled {c['enabledRenderers']} visible {c['visibleRenderers']} submeshes {c['visibleSubmeshes']} casters {c['visibleShadowCasterSubmeshes']} skinned {c['visibleSkinned']}")
            for g in c['groups'][:18]: print("    " + g)
