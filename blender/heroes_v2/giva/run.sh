#!/bin/zsh
# Giva v2 pipeline: ./run.sh [from_stage] (1 base, 2 rig, 3 suit, 4 gear, 5 boots/gloves, 6 assemble, 7 textures, 8 export)
set -e
cd "$(dirname "$0")"
B=/Applications/Blender.app/Contents/MacOS/Blender
S=${1:-1}
run() { echo "== $1"; $B -b ${2:+$2} --python-exit-code 1 --python $1 -- ${@:3} > out/logs/${1%.py}.log 2>&1 || { tail -30 out/logs/${1%.py}.log; exit 1; }; grep -E "^\[giva" out/logs/${1%.py}.log | tail -4; }
[ $S -le 1 ] && run s1_base.py ""
[ $S -le 2 ] && run s2_rig.py out/giva_base.blend
[ $S -le 3 ] && run s3_suit.py out/giva_rig.blend
[ $S -le 4 ] && run s4_gear.py out/giva_suit.blend ${GEAR_ARGS:-}
[ $S -le 5 ] && run s5_boots_gloves.py out/giva_gear.blend ${BG_ARGS:-}
[ $S -le 6 ] && run s6_assemble.py out/giva_bg.blend
[ $S -le 7 ] && [ -f s7_textures.py ] && run s7_textures.py out/giva_asm.blend
[ $S -le 7 ] && run s7b_face.py out/giva_tex.blend
[ $S -le 7 ] && run s7c_hair.py out/giva_face.blend
[ $S -le 8 ] && [ -n "$EXPORT" ] && run s8_export.py out/giva_hair.blend
echo done
