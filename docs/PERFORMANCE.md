# Performance

Measured 2026-10-09 with the development player's built-in benchmark (`EOA.Benchmark`: scripted open-city traversal and
a heavy plaza fight), 1920x1080, on a Mac16,13 (Apple M4, Metal), on an idle machine. The game has not yet been measured
on Windows hardware.

| Preset | City (5 routes, avg fps) | Combat (avg fps) | 1% low in combat | Main-thread CPU | GPU | Draw calls |
|---|---|---|---|---|---|---|
| Low | 113–211 | 186 | 106 | 4.7–8.8 ms | 3.5–7.7 ms | 460–1,180 |
| Medium | 93–118 | 92 | 64 | 8.5–10.8 ms | 6.3–8.1 ms | 1,460–4,240 |
| High | 52–71 | 49 | 31 | 14–20.5 ms | 11.9–14.4 ms | 2,170–6,850 |

An earlier run on 2026-10-08 had Blender bakes running alongside (system load average about 14). It measured Medium at
43–98 fps in the city and 59 in combat (1% low 13), and High at 41–56 and 42. The idle figures above replace it.

Reading the numbers:
- **Low** is GPU-light: about 5–8 ms of GPU work per frame. A GPU with a third of the M4's throughput (Intel Iris Xe,
  GTX 1050, RX 560) should still hold 60 fps at 1080p on Low.
- **Medium and High** are CPU-bound by draw calls (shadow cascades, SSAO depth-normals prepass, longer view distance).
  A desktop CPU with 6 or more fast cores should match or beat these figures; older 4-core laptop CPUs may need Low.
- **PerformanceGuard**: on any PC, if gameplay averages under 40 fps (26 with the 30 FPS cap), the game lowers the preset
  one step at a time and tells the player, unless they chose their own graphics settings.
- **First launch**: the preset is picked from the hardware (`Settings.HardwarePreset`): integrated GPUs or low VRAM/RAM
  start on Low, 2–4 GB cards on Medium, 4 GB+ cards on High.

Raw reports: `low.json`, `medium.json`, `high.json` and their per-frame CSVs were written by the benchmark to the
session scratch directory and are not kept in the repository.
