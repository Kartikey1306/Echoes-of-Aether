#!/bin/zsh
# Run a Unity batch method under the shared project lock and copy the smoke captures out.
#   run_unity.sh <tag> <executeMethod> [quit]
TAG=$1; METHOD=$2; QUIT=$3
G=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
LOG=$G/blender/city_street/logs/$TAG.log
until mkdir $G/.unity_lock 2>/dev/null; do sleep 30; done
trap 'rmdir $G/.unity_lock 2>/dev/null' EXIT INT TERM
echo "[run] lock acquired $(date +%T)"
T0=$(date +%s)
if [ "$QUIT" = "quit" ]; then
  $U -batchmode -quit -projectPath $G/unity/EchoesOfAether -executeMethod $METHOD -logFile $LOG
else
  $U -batchmode -projectPath $G/unity/EchoesOfAether -executeMethod $METHOD -logFile $LOG
fi
RC=$?
T1=$(date +%s)
if [ "$QUIT" != "quit" ]; then
  mkdir -p $G/blender/city_street/captures/$TAG
  cp $G/Captures/smoke/*.png $G/Captures/smoke/report.json $G/blender/city_street/captures/$TAG/ 2>/dev/null
fi
rmdir $G/.unity_lock 2>/dev/null
echo "[run] done rc=$RC in $((T1-T0))s $(date +%T)"
