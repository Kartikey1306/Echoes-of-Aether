#!/bin/zsh
# City FX tour (CityFxTourRunner) under the Unity lock; captures into blender/fx/previews/cityfx_<tag>.
G=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
OUT=$G/blender/fx/previews/cityfx_${1:-run}
mkdir -p $OUT
until mkdir $G/.unity_lock 2>/dev/null; do sleep 30; done
trap 'rmdir $G/.unity_lock 2>/dev/null' EXIT
cd $G
echo "[fx-city] lock acquired $(date)"
$U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.CityFxTourRunner.Run -cityfxOut $OUT -logFile $G/blender/fx/out/unity_city_${1:-run}.log
echo "[fx-city] exit $? $(date)"
