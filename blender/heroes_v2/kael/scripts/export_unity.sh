#!/bin/zsh
# Kael: export the FBX + manifest + textures AND rebuild the prefab inside ONE Unity lock hold (never leave the tree with
# a new Kael.fbx and a stale Kael.prefab), then the optional verification steps.
#   export_unity.sh <tag> [concept] [heroes] [posture] [story]
setopt +o nomatch
G=/Users/kartikey/Desktop/Game
B=/Applications/Blender.app/Contents/MacOS/Blender
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
K=$G/blender/heroes_v2/kael
TAG=$1; shift
OUT=$G/Captures/kael_v2/$TAG
mkdir -p $OUT
until mkdir $G/.unity_lock 2>/dev/null; do sleep 3; done
SETTINGS="$HOME/Library/Application Support/EchoesOfAether/Echoes of Aether/settings.json"
restore_settings() { [ -f "$SETTINGS.kael_bak" ] && mv -f "$SETTINGS.kael_bak" "$SETTINGS"; }
trap 'restore_settings; rmdir $G/.unity_lock 2>/dev/null' EXIT INT TERM
echo "LOCKED $(date)"
cd $K
$B -b blends/kael_s6_deform.blend --python scripts/build_export.py > logs/run_export.log 2>&1
if grep -q "^Traceback" logs/run_export.log || ! grep -q "EXPORTED" logs/run_export.log; then
  echo "EXPORT FAILED (Unity untouched)"; tail -20 logs/run_export.log; exit 1
fi
grep -E "MANIFEST" logs/run_export.log | cut -c1-200
# the Body UV layout may have changed: re-rasterise the catalog tattoo maps into it (same files / GUIDs)
$B -b blends/kael_s6_deform.blend --python scripts/tattoo_refit.py > logs/run_tattoo.log 2>&1
grep -q "^Traceback" logs/run_tattoo.log && { echo "TATTOO REFIT FAILED (continuing)"; tail -5 logs/run_tattoo.log; }
cd $G
$U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.CharacterBuilder.BuildAll -quit -logFile $OUT/build.log
echo "build exit $?"; grep -E "\[characters\] Kael|Rig Error|error CS|Exception|mis-match|build complete|Shader error|shader.*error" $OUT/build.log | grep -v "^UnityEngine" | head -20
for step in "$@"; do
  case $step in
    concept) rm -f $G/Captures/hero_concept/kael_*.png
             $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.HeroConceptCapture.Run -hero kael -logFile $OUT/concept.log
             echo "concept exit $?"; mkdir -p $OUT/concept; cp $G/Captures/hero_concept/kael_*.png $OUT/concept/ 2>/dev/null
             grep -E "\[concept\]|error CS" $OUT/concept.log | head -10 ;;
    story) $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunStory -logFile $OUT/story.log
           echo "story exit $?"; cp $G/Captures/smoke/report.json $OUT/story_report.json 2>/dev/null
           grep -E "\[smoke\] finished" $OUT/story.log | tail -3
           python3 -c "import json;r=json.load(open('$OUT/story_report.json'));print('STORY', r.get('story'), 'errors', r.get('errors'))" 2>/dev/null ;;
    posture) rm -f $G/Captures/smoke/p_*.png
             $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunPosture -logFile $OUT/posture.log
             echo "posture exit $?"; mkdir -p $OUT/posture; cp $G/Captures/smoke/p_*.png $OUT/posture/ 2>/dev/null
             cp $G/Captures/smoke/report.json $OUT/posture_report.json 2>/dev/null
             grep -E "\[smoke\] finished" $OUT/posture.log | tail -2 ;;
    heroes) rm -f $G/Captures/smoke/h_*.png
            $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunHeroes -logFile $OUT/heroes.log
            echo "heroes exit $?"; cp $G/Captures/smoke/h* $OUT/ 2>/dev/null; cp $G/Captures/smoke/report.json $OUT/heroes_report.json 2>/dev/null
            grep -E "\[smoke\] finished" $OUT/heroes.log | head -3 ;;
    shadercheck)
            $U -batchmode -quit -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.ShaderPlatformCheck.Run -logFile $OUT/shadercheck.log
            echo "shadercheck exit $?"; cp $G/Captures/shadercheck.txt $OUT/ 2>/dev/null
            grep -E "\[shadercheck\]" $OUT/shadercheck.log | grep -v "^UnityEngine" | head -20 ;;
    heroes_low)
            # the same hero captures on the Low preset (FXAA, no shadows, low textures, performance resolution): the
            # player's settings file is swapped for the run and restored right after (and by the exit trap)
            cp "$SETTINGS" "$SETTINGS.kael_bak"
            python3 - "$SETTINGS" <<'PY'
import json, sys
p = sys.argv[1]
d = json.load(open(p, encoding="utf-8-sig"))
d["graphics"].update({"preset": "low", "resolution": "performance", "shadows": "off", "effects": "low", "textures": "low",
                      "viewDistance": "low", "antialiasing": "fxaa"})
json.dump(d, open(p, "w"), indent=2)
PY
            rm -f $G/Captures/smoke/h_*.png $G/Captures/smoke/h0*.png
            $U -batchmode -projectPath unity/EchoesOfAether -executeMethod EOA.EditorTools.SmokeTest.RunHeroes -logFile $OUT/heroes_low.log
            echo "heroes_low exit $?"; restore_settings
            mkdir -p $OUT/low; cp $G/Captures/smoke/h* $OUT/low/ 2>/dev/null
            grep -E "\[smoke\] finished" $OUT/heroes_low.log | head -3 ;;
  esac
done
echo "DONE $(date)"
