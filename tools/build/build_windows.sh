#!/bin/zsh
# Windows x64 release: compile gate, Unity build (under the shared Unity lock), shader-error scan, then a zip ready to
# upload: Builds/EchoesOfAether_Windows_x64.zip (game folder + README.txt, without Unity's debug-symbol folders).
# Usage: tools/build/build_windows.sh
set -u
cd "$(dirname "$0")/../.."
ROOT=$PWD
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
LOG=$ROOT/Builds/windows_build.log
OUT=$ROOT/Builds/Windows
ZIP=$ROOT/Builds/EchoesOfAether_Windows_x64.zip
mkdir -p Builds

[ -d /Applications/Unity/Hub/Editor/6000.3.25f1/PlaybackEngines/WindowsStandaloneSupport ] || { echo "Windows Build Support (Mono) is not installed"; exit 1; }

echo "== compile gate"
UNITYCHECK_OUT=$ROOT/Builds/.unitycheck python3 tools/unitycheck/check.py --player 2>&1 | grep -E "\] Assembly-CSharp" | tee /dev/stderr | grep -q "0 errors" || { echo "compile errors: not building"; exit 1; }

echo "== waiting for the Unity lock"
until mkdir "$ROOT/.unity_lock" 2>/dev/null; do sleep 30; done
trap 'rmdir "$ROOT/.unity_lock" 2>/dev/null' EXIT
rm -rf "$OUT"
echo "== building ($(date +%T))"
"$U" -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.BuildScripts.Windows -logFile "$LOG" >/dev/null 2>&1
code=$?
rmdir "$ROOT/.unity_lock" 2>/dev/null; trap - EXIT
grep -E "\[build\] StandaloneWindows64:" "$LOG"
[ $code -eq 0 ] && [ -f "$OUT/EchoesOfAether.exe" ] || { echo "build FAILED (exit $code), see $LOG"; exit 1; }

echo "== shader errors"
if grep -E "Shader error in|Shader warning in '.*': .*error" "$LOG" | sort -u | head -20 | grep -q .; then
    grep -E "Shader error in" "$LOG" | sort -u | head -20
    echo "shader errors found: see $LOG"
    exit 1
fi
echo "none"

echo "== packaging"
STAGE=$ROOT/Builds/.win_stage/EchoesOfAether
rm -rf "$ROOT/Builds/.win_stage" "$ZIP"
mkdir -p "$STAGE"
rsync -a --exclude '*_BurstDebugInformation_DoNotShip' --exclude '*_BackUpThisFolder_ButDontShipItWithYourGame' "$OUT/" "$STAGE/"
cp tools/build/windows_README.txt "$STAGE/README.txt"
(cd "$ROOT/Builds/.win_stage" && zip -qr -9 "$ZIP" EchoesOfAether)
rm -rf "$ROOT/Builds/.win_stage"
ls -lh "$ZIP"
echo "== done"
