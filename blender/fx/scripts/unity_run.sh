#!/bin/zsh
# FX verification run: waits for the Unity lock, runs the FX shots and the zone tour, copies captures, releases the lock.
G=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
TAG=${1:-run}
OUT=$G/blender/fx/previews/unity_$TAG
mkdir -p $OUT
# never import half-written FX textures: wait for the smoke/mist render chain
until mkdir $G/.unity_lock 2>/dev/null; do sleep 30; done
trap 'rmdir $G/.unity_lock 2>/dev/null' EXIT
cd $G
echo "[fx-run] lock acquired $(date)"
$U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.FxShots.Run -logFile $G/blender/fx/out/unity_fxshots_$TAG.log
echo "[fx-run] fxshots exit $? $(date)"
cp $G/Captures/fx/*.png $G/Captures/fx/report.json $OUT/ 2>/dev/null
if [ "$2" != "nosmoke" ]; then
  $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.Run -logFile $G/blender/fx/out/unity_smoke_$TAG.log
  echo "[fx-run] smoke exit $? $(date)"
  mkdir -p $OUT/smoke
  cp $G/Captures/smoke/*.png $G/Captures/smoke/report.json $OUT/smoke/ 2>/dev/null
fi
echo "[fx-run] done $(date)"
