#!/bin/zsh
# Giva final verification under the shared lock (STYLE.md): export + BuildAll, the concept-match capture
# (EOA.EditorTools.GivaConceptShot, built-in "waves" hair), RunHeroes, RunPosture, RunStory.
# Waits for a clean compile before and after taking the lock (other agents' half-written files).
#   ./verify.sh <tag> [noexport]
cd "$(dirname "$0")"
GIVA=$PWD
ROOT=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
B=/Applications/Blender.app/Contents/MacOS/Blender
OUTD=$GIVA/out/unity/$1
mkdir -p $OUTD
echo "waiting for the Unity lock..."
until mkdir $ROOT/.unity_lock 2>/dev/null; do sleep 20; done
echo "lock acquired $(date)"
trap 'rmdir $ROOT/.unity_lock 2>/dev/null; echo "lock released $(date)"' EXIT INT TERM
if [ "$2" = "exportonly" ]; then
  $B -b out/giva_hair.blend --python-exit-code 1 --python s8_export.py > out/logs/s8_export.log 2>&1 || { tail -20 out/logs/s8_export.log; exit 1; }
  grep -E "EXPORTED" out/logs/s8_export.log
  exit 0
fi
if [ "$2" != "conceptonly" ]; then
  if [ "$2" != "noexport" ]; then
    $B -b out/giva_hair.blend --python-exit-code 1 --python s8_export.py > out/logs/s8_export.log 2>&1 || { tail -20 out/logs/s8_export.log; exit 1; }
    grep -E "EXPORTED" out/logs/s8_export.log
  fi
  (cd $ROOT/unity/EchoesOfAether && $U -batchmode -projectPath . -executeMethod EOA.EditorTools.CharacterBuilder.BuildAll -quit -logFile $OUTD/build.log)
  echo "BuildAll: $(grep -E '\[characters\] Lyra' $OUTD/build.log | tr '\n' ' ') Rig Errors: $(grep -c 'Rig Error' $OUTD/build.log)"
fi
R=$ROOT/unity/EchoesOfAether/Assets/Settings/EOA_URP_Renderer.asset
ssao() { python3 - "$R" "$1" "$2" <<'PY'
import sys
p, a, b = sys.argv[1:4]; s = open(p).read(); i = s.index("m_Name: SSAO"); j = s.index(a, i)
open(p, "w").write(s[:j] + b + s[j + len(a):])
PY
}
if [ "$3" = "nossao" ]; then
  SSAO_I=$(grep -A12 "m_Name: SSAO" $R | grep "    Intensity:" | head -1)
  ssao "$SSAO_I" "    Intensity: 0"
fi
(cd $ROOT/unity/EchoesOfAether && $U -batchmode -projectPath . -executeMethod EOA.EditorTools.GivaConceptShot.Run -givaHair waves -givaFits -givaOut $OUTD/concept -logFile $OUTD/concept.log)
if [ "$3" = "nossao" ]; then ssao "    Intensity: 0" "$SSAO_I"; grep -A12 "m_Name: SSAO" $R | grep "    Intensity:"; fi
echo "Concept shot: $(grep -E '\[giva-concept\] (done|wrote|System)' $OUTD/concept.log | tail -2 | tr '\n' ' ')"
[ "$2" = "conceptonly" ] && exit 0
TESTS=${TESTS:-"RunHeroes RunPosture RunStory"}
for m in ${=TESTS}; do
  mkdir -p $OUTD/$m
  (cd $ROOT && $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.$m -logFile $OUTD/$m.log)
  cp -R $ROOT/Captures/smoke/. $OUTD/$m/ 2>/dev/null
  echo "$m: $(grep -E '\[smoke\] finished' $OUTD/$m.log | tail -1)"
done
