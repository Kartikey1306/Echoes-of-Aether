#!/usr/bin/env python3
"""Before/after table of two benchmark reports: compare.py before.json after.json"""
import json, sys
a, b = (json.load(open(p)) for p in sys.argv[1:3])
def idx(r):
    d = {s['name']: s for s in r['scenarios']}
    for k, s in r['summary'].items():
        if s: d['[' + k + ']'] = s
    return d
A, B = idx(a), idx(b)
keys = ['avgFps', 'low1Fps', 'low01Fps', 'maxMs', 'spikes33', 'spikes50', 'cpuMainMs', 'gpuMs', 'gcBytesPerFrame', 'drawCalls', 'setPass']
print(f"{'scenario':30} " + " ".join(f"{k[:9]:>17}" for k in keys))
for name in list(A.keys()):
    if name not in B or name.startswith('load') or name in ('settle', 'end', 'boot'): continue
    x, y = A[name], B[name]
    print(f"{name[:30]:30} " + " ".join(f"{x[k]:>8.1f}→{y[k]:<8.1f}" for k in keys))
print("loads:")
for la, lb in zip(a['loads'], b['loads']):
    print(f"  {la['zone']:9} {la['seconds']:6.2f}s → {lb['seconds']:6.2f}s")
