#!/bin/zsh
# Echoes of Aether auto-builder: keeps importing, building and testing unattended.
# Every INTERVAL seconds:
#   1. if new files appeared in incoming/mixamo (animations / characters): rebuild characters (CharacterBuilder.BuildAll)
#   2. if the project changed since the last good build and it compiles: build macOS (Builds/macOS) and run the
#      story test; results go to Builds/STATUS.txt and tools/autobuild/logs/.
# Shares /Users/kartikey/Desktop/Game/.unity_lock with the agents (one Unity at a time). Safe to run repeatedly.
# Start:  nohup tools/autobuild/autobuild.sh >/dev/null 2>&1 &      Stop: touch tools/autobuild/STOP
ROOT=/Users/kartikey/Desktop/Game
U=/Applications/Unity/Hub/Editor/6000.3.25f1/Unity.app/Contents/MacOS/Unity
DIR=$ROOT/tools/autobuild
LOGS=$DIR/logs
STATUS=$ROOT/Builds/STATUS.txt
INTERVAL=${INTERVAL:-1800}
mkdir -p $LOGS $ROOT/Builds
cd $ROOT || exit 1
echo $$ > $DIR/autobuild.pid
rm -f $DIR/STOP

stamp() { date "+%Y-%m-%d %H:%M:%S"; }
log() { echo "[$(stamp)] $*" >> $LOGS/autobuild.log; }
status() { { echo "Echoes of Aether - auto-builder status"; echo "updated: $(stamp)"; echo; cat $DIR/state.txt 2>/dev/null; } > $STATUS; }
setstate() { touch $DIR/state.txt; grep -v "^$1:" $DIR/state.txt > $DIR/state.tmp 2>/dev/null; echo "$1: $2" >> $DIR/state.tmp; mv $DIR/state.tmp $DIR/state.txt; status; }

lock() { local n=0; until mkdir $ROOT/.unity_lock 2>/dev/null; do sleep 30; n=$((n+1)); [ $n -gt 240 ] && return 1; done; return 0; }
unlock() { rmdir $ROOT/.unity_lock 2>/dev/null; }

unity() { # method logname [extra args]
  local m=$1 l=$LOGS/$2.log; shift 2
  $U -batchmode -projectPath unity/EchoesOfAether -executeMethod $m "$@" -logFile $l >/dev/null 2>&1
  if grep -q "Scripts have compiler errors" $l; then return 2; fi
  return 0
}

fingerprint() { # changes in the project (git HEAD + working tree of the Unity project) and incoming files
  { git rev-parse HEAD; git status --porcelain unity/EchoesOfAether/Assets unity/EchoesOfAether/ProjectSettings | md5; } | md5
}
incoming_fp() { find incoming -type f \( -name "*.fbx" -o -name "*.FBX" \) -exec stat -f "%m %N" {} \; 2>/dev/null | sort | md5; }

log "auto-builder started (pid $$, interval ${INTERVAL}s)"
setstate "auto-builder" "running (pid $$, every $((INTERVAL/60)) min)"
while [ ! -f $DIR/STOP ]; do
  inc=$(incoming_fp); last_inc=$(cat $DIR/last_incoming 2>/dev/null)
  fp=$(fingerprint); last_fp=$(cat $DIR/last_build 2>/dev/null)
  # Build only when the project has been quiet for a full interval (agents finished or paused), so the
  # auto-builder never competes with active work for Unity.
  prev_seen=$(cat $DIR/prev_seen 2>/dev/null); echo "$fp$inc" > $DIR/prev_seen
  if [ "$fp$inc" != "$prev_seen" ]; then log "project still changing; waiting for a quiet period"; setstate "waiting" "changes in progress at $(stamp)"; sleep $INTERVAL; continue; fi
  if [ "$inc" != "$last_inc" ] || [ "$fp" != "$last_fp" ]; then
    # Compile gate (no Unity needed).
    if UNITYCHECK_OUT=$ROOT/tools/unitycheck/out_autobuild python3 tools/unitycheck/check.py --player > $LOGS/compile.log 2>&1 && ! grep -q "Assembly-CSharp: FAILED" $LOGS/compile.log; then
      if lock; then
        log "change detected; building"
        setstate "last attempt" "$(stamp)"
        ok=1
        if [ "$inc" != "$last_inc" ]; then
          unity EOA.EditorTools.CharacterBuilder.BuildAll characters -quit || ok=0
          [ $ok = 1 ] && echo "$inc" > $DIR/last_incoming && setstate "incoming import" "done $(stamp) ($(find incoming -name '*.fbx' | wc -l | tr -d ' ') files)"
        fi
        if [ $ok = 1 ]; then
          unity EOA.EditorTools.BuildScripts.MacOS mac -quit
          if grep -q "Result: Success" $LOGS/mac.log; then
            rm -rf "$ROOT/Builds/macOS/Echoes of Aether_BurstDebugInformation_DoNotShip"
            setstate "macOS build" "OK $(stamp)  ->  Builds/macOS/EchoesOfAether.app"
            unity EOA.EditorTools.SmokeTest.RunStory story
            if grep -q "main story complete" $LOGS/story.log; then setstate "story test" "PASS $(stamp)"; else setstate "story test" "FAIL $(stamp) (see tools/autobuild/logs/story.log)"; fi
            echo "$fp" > $DIR/last_build
          else
            setstate "macOS build" "FAILED $(stamp) (see tools/autobuild/logs/mac.log)"
          fi
        fi
        unlock
      fi
    else
      log "project does not compile right now (an edit in progress?); retrying later"
      setstate "compile" "waiting: project does not compile at $(stamp)"
    fi
  fi
  sleep $INTERVAL
done
log "auto-builder stopped"
setstate "auto-builder" "stopped $(stamp)"
rm -f $DIR/autobuild.pid
