#!/bin/zsh
# Re-render with the remade heroes, the city landmark/street kits and the FX storm sky.
B=/Applications/Blender.app/Contents/MacOS/Blender
cd "$(dirname "$0")"
L=../previews/logs; mkdir -p $L
./render_all.sh plaza rooftops
echo "[finish2] marketing start $(date +%T)"
$B -b --factory-startup --python marketing.py -- key social itch banner title_bg > $L/marketing_v2.log 2>&1
echo "[finish2] marketing exit $? $(date +%T)"
$B -b --factory-startup --python portraits.py -- kael lyra > $L/portraits_v2.log 2>&1
./render_all.sh metro facility vault core sheet
echo "[finish2] all done $(date +%T)"
