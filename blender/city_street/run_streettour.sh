#!/bin/zsh
# City street-level tour (CityFxTour) under the Unity lock -> blender/city_street/captures/<tag>
TAG=$1
G=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
OUT=$G/blender/city_street/captures/$TAG
LOG=$G/blender/city_street/logs/$TAG.log
until mkdir $G/.unity_lock 2>/dev/null; do sleep 30; done
trap 'rmdir $G/.unity_lock 2>/dev/null' EXIT INT TERM
T0=$(date +%s)
$U -batchmode -projectPath $G/unity/EchoesOfAether -executeMethod EOA.CityStreetTourRunner.Run -streetOut $OUT -logFile $LOG
RC=$?
rmdir $G/.unity_lock 2>/dev/null
echo "[run] done rc=$RC in $(( $(date +%s) - T0 ))s"
