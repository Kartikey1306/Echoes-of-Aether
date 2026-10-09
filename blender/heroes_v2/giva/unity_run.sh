#!/bin/zsh
# Giva Unity verification under the shared lock (STYLE.md):
#   ./unity_run.sh <tag> [export] [build] [heroes] [combat] [story]
# export: s8_export.py into Assets/Art/Characters/Lyra (only while holding the lock)
# Captures are copied to blender/heroes_v2/giva/out/unity/<tag>/ right away.
cd "$(dirname "$0")"
GIVA=$PWD
ROOT=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
B=/Applications/Blender.app/Contents/MacOS/Blender
TAG=$1; shift
OUTD=$GIVA/out/unity/$TAG
mkdir -p $OUTD
echo "waiting for the Unity lock..."
until mkdir $ROOT/.unity_lock 2>/dev/null; do sleep 30; done
echo "lock acquired $(date)"
trap 'rmdir $ROOT/.unity_lock 2>/dev/null; echo "lock released $(date)"' EXIT INT TERM
for step in "$@"; do
  case $step in
    export)
      $B -b out/giva_hair.blend --python-exit-code 1 --python s8_export.py > out/logs/s8_export.log 2>&1 || { tail -20 out/logs/s8_export.log; exit 1; }
      grep -E "EXPORTED" out/logs/s8_export.log ;;
    build)
      (cd $ROOT/unity/EchoesOfAether && $U -batchmode -projectPath . -executeMethod EOA.EditorTools.CharacterBuilder.BuildAll -quit -logFile $OUTD/build.log)
      grep -E "\[characters\]|Rig Error|error CS|Exception|is not a valid|mis-match" $OUTD/build.log | head -40 ;;
    heroes)
      (cd $ROOT && $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunHeroes -logFile $OUTD/heroes.log)
      cp $ROOT/Captures/smoke/*.png $ROOT/Captures/smoke/report.json $OUTD/ 2>/dev/null
      grep -E "\[smoke\] finished|\[autopilot\] done" $OUTD/heroes.log | tail -3 ;;
    heroes_nossao)
      # diagnostic only: SSAO renderer feature switched off for one capture, file restored byte-for-byte afterwards
      R=$ROOT/unity/EchoesOfAether/Assets/Settings/EOA_URP_Renderer.asset
      cp $R $OUTD/EOA_URP_Renderer.asset.bak
      python3 - "$R" <<'PY'
import sys
p = sys.argv[1]; s = open(p).read()
i = s.index("m_Name: SSAO"); j = s.index("m_Active: 1", i)
open(p, "w").write(s[:j] + "m_Active: 0" + s[j + len("m_Active: 1"):])
PY
      mkdir -p $OUTD/nossao
      (cd $ROOT && $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunHeroes -logFile $OUTD/heroes_nossao.log)
      cp $OUTD/EOA_URP_Renderer.asset.bak $R
      cp $ROOT/Captures/smoke/*.png $OUTD/nossao/ 2>/dev/null
      cmp -s $R $OUTD/EOA_URP_Renderer.asset.bak && echo "renderer asset restored" ;;
    heroes_ssao0)
      # diagnostic only: SSAO intensity 0 for one capture (the game re-enables the SSAO feature at runtime, so m_Active
      # alone does not switch it off); the one line is reverted afterwards
      R=$ROOT/unity/EchoesOfAether/Assets/Settings/EOA_URP_Renderer.asset
      python3 - "$R" "    Intensity: 1.1" "    Intensity: 0" <<'PY'
import sys
p, a, b = sys.argv[1:4]; s = open(p).read(); i = s.index("m_Name: SSAO"); j = s.index(a, i)
open(p, "w").write(s[:j] + b + s[j + len(a):])
PY
      mkdir -p $OUTD/ssao0
      (cd $ROOT && $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunHeroes -logFile $OUTD/heroes_ssao0.log)
      python3 - "$R" "    Intensity: 0" "    Intensity: 1.1" <<'PY'
import sys
p, a, b = sys.argv[1:4]; s = open(p).read(); i = s.index("m_Name: SSAO"); j = s.index(a, i)
open(p, "w").write(s[:j] + b + s[j + len(a):])
PY
      cp $ROOT/Captures/smoke/*.png $OUTD/ssao0/ 2>/dev/null
      grep -A12 "m_Name: SSAO" $R | grep "Intensity: 1.1" > /dev/null && echo "SSAO intensity restored" ;;
    combat)
      mkdir -p $OUTD/combat
      (cd $ROOT && $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunCombat -logFile $OUTD/combat.log -combatFeel)
      cp -R $ROOT/Captures/smoke/. $OUTD/combat/ 2>/dev/null
      grep -E "\[smoke\] finished|\[autopilot\] done" $OUTD/combat.log | tail -3 ;;
    posture)
      mkdir -p $OUTD/posture
      (cd $ROOT && $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunPosture -logFile $OUTD/posture.log)
      cp -R $ROOT/Captures/smoke/. $OUTD/posture/ 2>/dev/null
      grep -E "\[smoke\] finished|\[autopilot\] done" $OUTD/posture.log | tail -3 ;;
    story)
      mkdir -p $OUTD/story
      (cd $ROOT && $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunStory -logFile $OUTD/story.log)
      cp -R $ROOT/Captures/smoke/. $OUTD/story/ 2>/dev/null
      grep -E "\[smoke\] finished|\[autopilot\] done" $OUTD/story.log | tail -3 ;;
  esac
done
