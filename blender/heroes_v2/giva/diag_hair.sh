#!/bin/zsh
# Final Giva verification under the shared lock:
#   export + BuildAll, then RunHeroes and RunPosture with the catalog's lyra default hair TEMPORARILY pointed at the
#   built-in "waves" hair (diagnostic preview; the one line is restored afterwards, also on failure), then RunStory
#   with the catalog untouched.        ./diag_hair.sh <tag>
cd "$(dirname "$0")"
GIVA=$PWD
ROOT=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
B=/Applications/Blender.app/Contents/MacOS/Blender
CAT=$ROOT/unity/EchoesOfAether/Assets/Resources/Characters/Custom/catalog.json
OUTD=$GIVA/out/unity/$1
mkdir -p $OUTD
compiles() { (cd $ROOT && UNITYCHECK_OUT=$ROOT/tools/unitycheck/out_giva python3 tools/unitycheck/check.py --player 2>&1 | grep -c "Assembly-CSharp: OK") | grep -q "^3$"; }
echo "waiting for a clean compile and the Unity lock..."
while true; do
  until compiles; do sleep 60; done
  until mkdir $ROOT/.unity_lock 2>/dev/null; do sleep 30; done
  if compiles; then break; fi
  rmdir $ROOT/.unity_lock; echo "compile broke while waiting, retrying $(date)"; sleep 60
done
echo "lock acquired $(date)"
cp $CAT $OUTD/catalog.json.bak
swap() { python3 - "$CAT" "$1" "$2" <<'PY'
import sys
p, a, b = sys.argv[1:4]
s = open(p).read()
i = s.index('"lyra": {', s.index('"defaults"'))
j = s.index(a, i)
if j - i < 40:
    open(p, "w").write(s[:j] + b + s[j + len(a):])
PY
}
restore() { swap '"hair": "waves"' '"hair": "long_waves"'; cmp -s $CAT $OUTD/catalog.json.bak && echo "catalog restored"; }
trap 'restore; rmdir $ROOT/.unity_lock 2>/dev/null; echo "lock released $(date)"' EXIT INT TERM
$B -b out/giva_hair.blend --python-exit-code 1 --python s8_export.py > out/logs/s8_export.log 2>&1 || { tail -20 out/logs/s8_export.log; exit 1; }
grep -E "EXPORTED" out/logs/s8_export.log
(cd $ROOT/unity/EchoesOfAether && $U -batchmode -projectPath . -executeMethod EOA.EditorTools.CharacterBuilder.BuildAll -quit -logFile $OUTD/build.log)
grep -E "\[characters\] Lyra|Rig Error|error CS" $OUTD/build.log | head -10
swap '"hair": "long_waves"' '"hair": "waves"'
grep -c '"hair": "waves"' $CAT
for m in RunHeroes RunPosture; do
  mkdir -p $OUTD/$m
  (cd $ROOT && $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.$m -logFile $OUTD/$m.log)
  cp -R $ROOT/Captures/smoke/. $OUTD/$m/ 2>/dev/null
  echo "$m: $(grep -E '\[smoke\] finished' $OUTD/$m.log | tail -1)"
done
restore
mkdir -p $OUTD/RunStory
(cd $ROOT && $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunStory -logFile $OUTD/RunStory.log)
cp -R $ROOT/Captures/smoke/. $OUTD/RunStory/ 2>/dev/null
echo "RunStory: $(grep -E '\[smoke\] finished' $OUTD/RunStory.log | tail -1)"
