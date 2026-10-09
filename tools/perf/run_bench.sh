#!/bin/bash
# Run the benchmark in the development player and print a summary.
# usage: tools/perf/run_bench.sh <outdir> [extra player args...]
ROOT=/Users/kartikey/Desktop/Game
APP="$ROOT/Builds/macOS_dev/EchoesOfAether.app/Contents/MacOS/Echoes of Aether"
OUT=$1; shift
mkdir -p "$OUT"
# Shared machine: note memory pressure and competing heavy processes (swap-outs during a run invalidate it).
SW0=$(vm_stat | awk '/Swapouts/ {gsub(/\./,"",$2); print $2}')
{ date; sysctl vm.swapusage; pgrep -fl "Unity.app/Contents/MacOS/Unity|[Bb]lender" | cut -c1-120; } > "$OUT/conditions.txt"
rm -rf "$OUT/bench_data"
caffeinate -dimsu "$APP" -benchmark "$OUT/bench.json" -logFile "$OUT/player.log" -screen-fullscreen 1 -screen-width 1920 -screen-height 1080 "$@" &
PID=$!
# Watchdog: 20 minutes.
for i in $(seq 1 1200); do kill -0 $PID 2>/dev/null || break; sleep 1; done
kill -9 $PID 2>/dev/null
wait $PID
echo "player exit $?"
SW1=$(vm_stat | awk '/Swapouts/ {gsub(/\./,"",$2); print $2}')
echo "swapouts during run: $((SW1-SW0)) pages" | tee -a "$OUT/conditions.txt"
python3 "$ROOT/tools/perf/summarize.py" "$OUT/bench.json"
