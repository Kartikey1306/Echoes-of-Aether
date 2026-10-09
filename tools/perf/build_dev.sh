#!/bin/bash
# Build the development macOS player (Builds/macOS_dev) under the shared Unity lock.
# usage: tools/perf/build_dev.sh <logfile> [executeMethod]
ROOT=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
LOG=${1:-/tmp/eoa_build_dev.log}
METHOD=${2:-EOA.EditorTools.BuildScripts.MacOSDev}
until mkdir "$ROOT/.unity_lock" 2>/dev/null; do sleep 30; done
trap 'rmdir "$ROOT/.unity_lock" 2>/dev/null' EXIT
echo "lock acquired $(date)"
"$U" -batchmode -quit -projectPath "$ROOT/unity/EchoesOfAether" -executeMethod "$METHOD" -logFile "$LOG"
code=$?
echo "unity exit $code $(date)"
exit $code
