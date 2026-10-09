# Mixamo animations: download guide

Mixamo (by Adobe) gives free, professionally cleaned motion capture. Its licence allows royalty-free use inside
games. You only need a free Adobe account. The game picks the files up automatically; any clip you skip falls back
to the current animation, so you can do the **Priority** list first and the rest later.

## One-time setup

1. Open <https://www.mixamo.com> and sign in with a free Adobe account.
2. For the animation downloads below, select the character **Y Bot** first. Use the same character for every
   animation so all clips share one skeleton.
3. Create the folder `/Users/kartikey/Desktop/Game/incoming/mixamo/`.

## Also download the Y Bot itself (once)

With **Y Bot** selected and no animation applied, click **Download**: FBX for Unity, **Pose: T-pose**, With Skin.
Save it as `incoming/mixamo/ybot.fbx`. The importer uses it as the neutral pose, so the animations stand upright.

## For each clip

1. Go to **Animations** and type the search term from the table below.
2. Click the animation that best matches the "Look for" note.
3. If the clip moves the character forward (walk, run, sprint), tick **In Place** on the right.
4. Click **Download** and set:
   - **Format:** FBX for Unity (.fbx)
   - **Skin:** Without Skin
   - **Frames per second:** 30
   - **Keyframe reduction:** none
5. Rename the downloaded file to the **Save as** name and move it into `incoming/mixamo/`.

## Characters (new 3D models for Kael and Giva)

1. Go to **Characters** and browse for a male and a female character that fit the game: grounded
   sci-fi or cyberpunk soldier/adventurer outfits, realistic proportions. Useful searches: `soldier`, `sci-fi`,
   `vanguard`, `swat`, `combat`, `adventurer`. Pick what you like best.
2. With the character selected, click **Download** and set:
   - **Format:** FBX for Unity (.fbx)
   - **Pose:** T-pose
3. Save the male as `incoming/mixamo/characters/kael.fbx` and the female as `incoming/mixamo/characters/giva.fbx`.

The import pipeline converts them automatically: materials, lighting, weapons, glasses, voices and animations. The old models stay
as a fallback.

## Priority (fixes the bent walking, running, standing and talking)

| Save as | Search for | Look for |
|---|---|---|
| `idle.fbx` | Breathing Idle | relaxed upright standing breath |
| `walk.fbx` | Walking | normal confident walk (**In Place**) |
| `run.fbx` | Running | natural jog/run (**In Place**) |
| `sprint.fbx` | Fast Run | full sprint (**In Place**) |
| `combat_idle.fbx` | Fighting Idle | ready stance, fists up |
| `talk.fbx` | Talking | standing conversation with hand gestures |
| `jump.fbx` | Jump | jump take-off |
| `fall.fbx` | Falling Idle | falling loop |
| `land.fbx` | Falling To Landing | landing |
| `hit.fbx` | Hit Reaction | small flinch |
| `death.fbx` | Dying | fall down |

## Combat

| Save as | Search for | Look for |
|---|---|---|
| `k_light1.fbx` | Sword And Shield Slash | fast one-handed slash |
| `k_light2.fbx` | Sword And Shield Slash | a different slash (backhand) |
| `k_light3.fbx` | Sword And Shield Attack | third combo strike |
| `k_heavy.fbx` | Great Sword Slash | big overhead finisher |
| `k_pulse.fbx` | Standing 2H Magic Area Attack | both hands slam / shockwave |
| `k_ult.fbx` | Jump Attack | leap and strike the ground |
| `l_quick1.fbx` | Cross Punch | quick strike |
| `l_quick2.fbx` | Hook Punch | second quick strike |
| `l_heavy.fbx` | Roundhouse Kick | big kick finisher |
| `l_echo.fbx` | Standing 1H Magic Attack | one-hand cast |
| `l_ult.fbx` | Standing 2H Magic Attack | two-hand big cast |
| `dash.fbx` | Standing Dodge Forward | forward dodge / dash |
| `phase_step.fbx` | Standing Dodge Backward | quick evade |
| `fire_r.fbx` | Standing 1H Cast Spell | throw a bolt from the right hand |
| `stagger.fbx` | Big Hit To Head | heavy stagger |

## World and NPCs

| Save as | Search for | Look for |
|---|---|---|
| `interact.fbx` | Button Pushing | press a panel |
| `pickup.fbx` | Picking Up | pick something off the ground |
| `climb.fbx` | Climbing Ladder | climb loop |
| `npc_crossed.fbx` | Standing Arms Crossed | arms folded idle |
| `npc_look.fbx` | Looking Around | glance around |
| `npc_react.fbx` | Surprised | startled reaction |
| `npc_work.fbx` | Typing | work at a console |
| `wave.fbx` | Waving | friendly wave |
| `sit.fbx` | Sitting Idle | seated idle |
| `kneel_work.fbx` | Kneeling | kneel and work |
| `lie.fbx` | Laying Idle | lying down |
| `wake.fbx` | Getting Up | get up from the ground |

Optional: for female-specific versions of any clip, put them in `incoming/mixamo/female/` with the same names.

## When you're done

Run the character import (`EOA.EditorTools.CharacterBuilder.BuildAll`), which imports them and rebuilds the characters,
then re-run the posture, combat and story tests and make a new build.
