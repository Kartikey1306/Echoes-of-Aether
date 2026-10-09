#!/bin/zsh
# Kael v2 full rebuild: base -> rig -> outfit -> hair -> textures -> face -> deform -> export+BuildAll  (logs in logs/)
set -e
B=/Applications/Blender.app/Contents/MacOS/Blender
K=/Users/kartikey/Desktop/Game/blender/heroes_v2/kael
cd $K
FROM=${1:-base}
SIZE=${2:-}
run() { echo "== $1"; $B -b ${@:2} > logs/run_$1.log 2>&1 && ! grep -q "^Traceback" logs/run_$1.log || { echo "FAILED $1"; tail -30 logs/run_$1.log; exit 1; }; grep -E "^\[kael" logs/run_$1.log | tail -4; }
stages=(base rig outfit hair tex face deform export tattoo)
go=0
for s in $stages; do
  [[ $s == $FROM ]] && go=1
  [[ $go == 0 ]] && continue
  case $s in
    base) run base --python scripts/build_base.py ;;
    rig) run rig blends/kael_s1_base.blend --python scripts/build_rig.py ;;
    outfit) run outfit blends/kael_s2_rig.blend --python scripts/build_outfit.py -- --parts top,pants,boots,gloves,knee_pads,chest_rig,chest_plate,jacket,collar,pauldrons,forearm_r --save ;;
    hair) run hair blends/kael_s3_outfit.blend --python scripts/hair_k4.py ;;
    tex) run tex blends/kael_s3_outfit.blend --python scripts/build_tex.py -- ${=SIZE:+--size $SIZE} --save ;;
    face) run face blends/kael_s4_tex.blend --python scripts/build_face.py -- --save ;;
    deform) run deform blends/kael_s5_face.blend --python scripts/build_deform.py -- --save ;;
    export) echo "== export (+ CharacterBuilder.BuildAll in the same Unity lock hold)"; zsh scripts/export_unity.sh run_all || exit 1 ;;
    tattoo) run tattoo blends/kael_s6_deform.blend --python scripts/tattoo_refit.py ;;
  esac
done
