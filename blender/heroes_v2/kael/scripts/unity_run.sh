#!/bin/zsh
# Kael v2 Unity verification under the shared lock.
#   unity_run.sh <tag> [build] [heroes] [combat] [story]
setopt +o nomatch
G=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
TAG=$1; shift
OUT=$G/Captures/kael_v2/$TAG
mkdir -p $OUT
until mkdir $G/.unity_lock 2>/dev/null; do sleep 30; done
trap 'rmdir $G/.unity_lock 2>/dev/null' EXIT INT TERM
echo "LOCKED $(date)"
cd $G
for step in "$@"; do
  case $step in
    build) $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.CharacterBuilder.BuildAll -quit -logFile $OUT/build.log
           echo "build exit $?"; grep -E "\[characters\]|Rig Error|error CS|Exception|mis-match" $OUT/build.log | grep -v "^UnityEngine" | head -40 ;;
    probe) $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.KaelRigProbe.Run -quit -logFile $OUT/probe.log
           echo "probe exit $?"; grep -E "\[probe\]|Exception" $OUT/probe.log | head -20 ;;
    heroes) rm -f $G/Captures/smoke/h_*.png
           $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunHeroes -logFile $OUT/heroes.log
           echo "heroes exit $?"; cp $G/Captures/smoke/h_* $OUT/ 2>/dev/null; cp $G/Captures/smoke/report.json $OUT/heroes_report.json 2>/dev/null
           grep -E "\[smoke\] finished|Exception|error" $OUT/heroes.log | head -10 ;;
    combat) $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunCombat -logFile $OUT/combat.log -combatFeel -correctiveLog
           echo "combat exit $?"; mkdir -p $OUT/combat; cp $G/Captures/smoke/feel_* $G/Captures/smoke/report.json $OUT/combat/ 2>/dev/null
           grep -E "\[smoke\] finished|Exception" $OUT/combat.log | head -10 ;;
    posture) rm -f $G/Captures/smoke/p_*.png
           $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunPosture -logFile $OUT/posture.log
           echo "posture exit $?"; mkdir -p $OUT/posture; cp $G/Captures/smoke/p_*.png $OUT/posture/ 2>/dev/null
           grep -E "\[smoke\] finished|Exception" $OUT/posture.log | head -10 ;;
    concept) $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.HeroConceptCapture.Run -hero kael -logFile $OUT/concept.log
           echo "concept exit $?"; mkdir -p $OUT/concept; cp $G/Captures/hero_concept/kael_*.png $OUT/concept/ 2>/dev/null
           grep -E "\[concept\]|Exception|error CS" $OUT/concept.log | head -10 ;;
    story) $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunStory -logFile $OUT/story.log
           echo "story exit $?"; cp $G/Captures/smoke/report.json $OUT/story_report.json 2>/dev/null
           grep -E "\[smoke\] finished|PASS|FAIL" $OUT/story.log | tail -10 ;;
  esac
done
echo "DONE $(date)"
