#!/bin/zsh
# Remaining deliverables after the key art: store art, interior loading screens, open-city loading screens, sheets.
B=/Applications/Blender.app/Contents/MacOS/Blender
cd "$(dirname "$0")"
L=../previews/logs; mkdir -p $L
echo "[finish] store start $(date +%T)"
$B -b --factory-startup --python marketing.py -- social itch banner > $L/marketing_store.log 2>&1
echo "[finish] store exit $? $(date +%T)"
./render_all.sh metro facility vault core plaza rooftops sheet
echo "[finish] all done $(date +%T)"
