#!/bin/zsh
# Re-render every 2D art deliverable from the scripted Blender scenes (Blender 5.2, Cycles, Metal GPU).
#   ./render_all.sh            all jobs
#   ./render_all.sh logo items specific jobs: plaza metro facility vault rooftops core logo portraits items marketing sheet
B=/Applications/Blender.app/Contents/MacOS/Blender
cd "$(dirname "$0")"
LOG=../previews/logs
mkdir -p $LOG
jobs=(${@:-plaza metro facility vault rooftops core logo portraits items marketing sheet})
for j in $jobs; do
  case $j in
    plaza|metro|facility|vault|rooftops|core) script=scene_$j.py ;;
    logo) script=logo.py ;;
    portraits) script=portraits.py ;;
    items) script=items.py ;;
    marketing) script=marketing.py ;;
    sheet) script=contact_sheet.py ;;
    *) echo "unknown job $j"; continue ;;
  esac
  echo "[queue] $j start $(date +%T)"
  $B -b --factory-startup --python $script > $LOG/$j.log 2>&1
  echo "[queue] $j exit $? $(date +%T) $(grep -cE 'Traceback|Error:' $LOG/$j.log) errors"
done
