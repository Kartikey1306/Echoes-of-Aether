#!/bin/zsh
# Diagnostic only (Giva skin mottling): RunHeroes captures with the URP asset's main-light shadows switched off, then
# with 3x shadow bias. Each patch touches one line of EOA_URP.asset and is reverted line-for-line afterwards (other
# agents' edits to the file stay intact).   ./diag_shadows.sh <tag>
cd "$(dirname "$0")"
GIVA=$PWD
ROOT=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
A=$ROOT/unity/EchoesOfAether/Assets/Settings/EOA_URP.asset
OUTD=$GIVA/out/unity/$1
mkdir -p $OUTD
echo "waiting for the Unity lock..."
until mkdir $ROOT/.unity_lock 2>/dev/null; do sleep 30; done
echo "lock acquired $(date)"
cp $A $OUTD/EOA_URP.asset.bak
sub() { python3 - "$A" "$1" "$2" <<'PY'
import sys
p, a, b = sys.argv[1:4]
s = open(p).read()
assert s.count(a) == 1, a
open(p, "w").write(s.replace(a, b))
PY
}
restore() {
  sub "  m_MainLightShadowsSupported: 0" "  m_MainLightShadowsSupported: 1" 2>/dev/null
  sub "  m_ShadowDepthBias: 3" "  m_ShadowDepthBias: 1" 2>/dev/null
  sub "  m_ShadowNormalBias: 3" "  m_ShadowNormalBias: 1" 2>/dev/null
}
trap 'restore; cmp -s $A $OUTD/EOA_URP.asset.bak && echo "URP asset restored"; rmdir $ROOT/.unity_lock 2>/dev/null; echo "lock released $(date)"' EXIT INT TERM
run() {
  mkdir -p $OUTD/$1
  (cd $ROOT && $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunHeroes -logFile $OUTD/$1.log)
  cp $ROOT/Captures/smoke/*.png $OUTD/$1/ 2>/dev/null
  grep -E "\[smoke\] finished" $OUTD/$1.log | tail -1
}
sub "  m_MainLightShadowsSupported: 1" "  m_MainLightShadowsSupported: 0"
run noshadow
restore
sub "  m_ShadowDepthBias: 1" "  m_ShadowDepthBias: 3"
sub "  m_ShadowNormalBias: 1" "  m_ShadowNormalBias: 3"
run bias3
restore
