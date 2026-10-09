#!/bin/zsh
# Unity verification for the landmarks kit (respects the shared lock): CityFx tour + full smoke zone tour.
#   blender/city_landmarks/run_unity_verify.sh <tag>
cd /Users/kartikey/Desktop/Game
TAG=${1:-final}
until mkdir /Users/kartikey/Desktop/Game/.unity_lock 2>/dev/null; do sleep 30; done
echo "landmarks $(date)" > .unity_lock/owner
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
L=$PWD/blender/city_landmarks/logs
$U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.CityFxTourRunner.Run -cityfxOut $PWD/Captures/landmarks_tour_$TAG -logFile $L/unity_tour_$TAG.log
echo "tour exit $?"
$U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.Run -logFile $L/unity_smoke_$TAG.log
echo "smoke exit $?"
mkdir -p Captures/landmarks_smoke_$TAG && cp Captures/smoke/* Captures/landmarks_smoke_$TAG/
rm -f .unity_lock/owner; rmdir .unity_lock
echo released
python3 -c "import json; r=json.load(open('Captures/landmarks_tour_$TAG/report.json')); print('tour errors', r['errors'])"
python3 -c "import json; r=json.load(open('Captures/landmarks_smoke_$TAG/report.json')); print('smoke errors', r.get('errors')); print([ (z['zone'], z['fps'], z['errors']) for z in r['zones']])"
grep -h "\[landmarks\]\|open district built" $L/unity_tour_$TAG.log $L/unity_smoke_$TAG.log | cut -c1-150
