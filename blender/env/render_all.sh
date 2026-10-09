#!/bin/zsh
# Render preview contact sheets for every category (re-imports and checks every FBX).
cd "$(dirname "$0")"
B=/Applications/Blender.app/Contents/MacOS/Blender
for cat in $(python3 -c "import json;print(' '.join(sorted({r['category'] for r in json.load(open('out/assets.json')).values()})))"); do
  names=($(python3 -c "import json,sys;print(' '.join(n for n,r in sorted(json.load(open('out/assets.json')).items()) if r['category']=='$cat'))"))
  $B -b --factory-startup --python render_assets.py -- --sheet "assets_$cat" --cols 4 --size 440x330 "${names[@]}" 2>&1 | grep -E "\[check\]|\[render\]|Error|Traceback" | grep -v ": OK"
done
$B -b --factory-startup --python render_materials.py -- --cols 5 --size 380x285 2>&1 | grep -E "sheet|Error"
