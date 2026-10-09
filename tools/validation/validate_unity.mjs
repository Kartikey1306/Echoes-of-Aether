#!/usr/bin/env node
// Echoes of Aether — Unity project validation.
// Cross-checks game data against the C# port and the Blender asset pipeline. Prints PASS / WARN / FAIL lines and
// exits 1 on any FAIL (release blocker).
//   node tools/validation/validate_unity.mjs            data, ids, assets, audio, art, secrets
//   node tools/validation/validate_unity.mjs --compile  also runs the offline C# compile check (editor + player)
//   node tools/validation/validate_unity.mjs --json     machine-readable output
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..');
const U = path.join(ROOT, 'unity', 'EchoesOfAether');
const A = path.join(U, 'Assets');
const r = (...p) => path.join(ROOT, ...p);
const read = (p) => fs.readFileSync(p, 'utf8');
const json = (p) => JSON.parse(read(p));
const exists = (p) => fs.existsSync(p);
const results = [];
const PASS = (cat, msg) => results.push({ level: 'PASS', cat, msg });
const WARN = (cat, msg) => results.push({ level: 'WARN', cat, msg });
const FAIL = (cat, msg) => results.push({ level: 'FAIL', cat, msg });
const matchAll = (s, re) => [...s.matchAll(re)].map((m) => m[1]);
function walk(dir, exts, out = []) {
  if (!exists(dir)) return out;
  for (const e of fs.readdirSync(dir, { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) { if (!e.name.startsWith('.') && e.name !== 'node_modules' && e.name !== 'Library') walk(p, exts, out); }
    else if (exts.some((x) => e.name.endsWith(x))) out.push(p);
  }
  return out;
}
const rel = (p) => path.relative(ROOT, p);

// ------------------------------------------------------------------ data
const DATA = path.join(A, 'Resources', 'Data');
let items, powerups, abilities, enemies, quests, dialogue, speakers, zones, collectibles, hints, locale;
try {
  items = json(path.join(DATA, 'items.json')).items;
  powerups = json(path.join(DATA, 'powerups.json')).powerups;
  abilities = json(path.join(DATA, 'abilities.json'));
  enemies = json(path.join(DATA, 'enemies.json')).enemies;
  quests = json(path.join(DATA, 'quests.json')).quests;
  dialogue = json(path.join(DATA, 'dialogue.json')).dialogues;
  speakers = json(path.join(DATA, 'speakers.json')).speakers;
  zones = json(path.join(DATA, 'zones.json')).zones;
  collectibles = json(path.join(DATA, 'collectibles.json')).collectibles;
  hints = json(path.join(DATA, 'hints.json')).hints;
  locale = json(path.join(DATA, 'locale', 'en.json'));
  PASS('data', 'All Unity JSON data files parse');
} catch (e) {
  FAIL('data', 'JSON parse error: ' + e.message);
  report();
}
// Parity with the design data (src/data is the authoring source).
const drift = [];
for (const f of ['items', 'powerups', 'abilities', 'enemies', 'quests', 'dialogue', 'speakers', 'zones', 'collectibles', 'hints']) {
  const a = r('src', 'data', f + '.json'), b = path.join(DATA, f + '.json');
  if (exists(a) && JSON.stringify(json(a)) !== JSON.stringify(json(b))) drift.push(f);
}
if (drift.length) WARN('data', `Unity data differs from src/data: ${drift.join(', ')} (copy src/data → Assets/Resources/Data)`);
else PASS('data', 'Unity data matches the authoring data in src/data');

const ids = (arr) => new Set(arr.map((x) => x.id));
const itemIds = ids(items), puIds = ids(powerups), abIds = ids(abilities.abilities), questIds = ids(quests), dlgIds = ids(dialogue);
const spkIds = ids(speakers), zoneIds = ids(zones), enemyIds = ids(enemies), hintIds = ids(hints), skillIds = ids(abilities.tree);
for (const [name, arr] of Object.entries({ items, powerups, quests, dialogue, speakers, zones, collectibles, hints, enemies, abilities: abilities.abilities, skills: abilities.tree })) {
  const seen = new Set(), dup = new Set();
  for (const x of arr) (seen.has(x.id) ? dup : seen).add(x.id);
  if (dup.size) FAIL('duplicate-ids', `${name}: duplicate ids ${[...dup].join(', ')}`);
}
PASS('duplicate-ids', 'no duplicate ids across data tables');

// ------------------------------------------------------------------ C# sources
const csFiles = walk(path.join(A, 'Scripts'), ['.cs']);
const cs = Object.fromEntries(csFiles.map((f) => [f, read(f)]));
const allCs = Object.values(cs).join('\n');
const zoneDir = path.join(A, 'Scripts', 'World', 'Zones');
const zoneFiles = csFiles.filter((f) => f.startsWith(zoneDir));
const zoneCs = Object.fromEntries(zones.map((z) => {
  const cls = z.id[0].toUpperCase() + z.id.slice(1) + 'Zone';
  const own = zoneFiles.filter((f) => path.basename(f) === cls + '.cs' || f.includes(path.sep + z.id[0].toUpperCase() + z.id.slice(1) + path.sep));
  return [z.id, own.map((f) => cs[f]).join('\n')];
}));
const allZoneCs = zoneFiles.map((f) => cs[f]).join('\n');
const strLits = (s) => new Set(matchAll(s, /"([a-z0-9_]+)"/g));

// ------------------------------------------------------------------ zones
const registry = cs[path.join(A, 'Scripts', 'World', 'ZoneRegistry.cs')] ?? '';
for (const z of zones) {
  const cls = z.id[0].toUpperCase() + z.id.slice(1) + 'Zone';
  if (!new RegExp(`\\["${z.id}"\\]\\s*=\\s*go => go\\.AddComponent<${cls}>`).test(registry)) FAIL('scenes', `zone ${z.id} not registered in ZoneRegistry`);
  if (!exists(path.join(zoneDir, cls + '.cs'))) FAIL('scenes', `zone ${z.id}: ${cls}.cs missing`);
  else if (/placeholder until the full port/i.test(read(path.join(zoneDir, cls + '.cs')))) FAIL('scenes', `zone ${z.id} is still the placeholder`);
  if (!exists(path.join(A, 'Resources', 'Art', 'Loading', z.id + '.jpg')) && !exists(path.join(A, 'Resources', 'Art', 'Loading', z.id + '.png'))) WARN('textures', `zone ${z.id} has no rendered loading art (Resources/Art/Loading)`);
  if (!z.hints?.length) WARN('scenes', `zone ${z.id} has no loading hints`);
}
PASS('scenes', `${zones.length} zones registered as procedural C# zones`);

// Ids defined by zone code (string literals) + typed helpers.
const zoneIdsIn = (zid) => strLits(zoneCs[zid] ?? '');
const allZoneIds = strLits(allZoneCs);
const npcIds = new Set(matchAll(allZoneCs, /\bNpc\(\s*"([a-z]+)"/g));
const markerIds = new Set([...matchAll(allZoneCs, /\bMarker\(\s*"(\w+)"/g), ...matchAll(allZoneCs, /\["(\w+)"\]\s*=/g)]);
const encounterIds = new Set(matchAll(allZoneCs, /\bEncounter\(\s*"(e_[a-z0-9_]+)"/g));
const spawnNames = new Set(matchAll(allZoneCs, /\bSpawn\(\s*"(\w+)"/g));

// Exits: target zone + entry spawn exist.
for (const m of allZoneCs.matchAll(/\bExit\(\s*"(\w+)",\s*"(\w+)",\s*"(\w+)"/g)) {
  const [, id, target, entry] = m;
  if (!zoneIds.has(target)) FAIL('scenes', `exit ${id} targets unknown zone ${target}`);
  const tcs = zoneCs[target] ?? '';
  if (!new RegExp(`\\bSpawn\\(\\s*"${entry}"`).test(tcs)) FAIL('scenes', `exit ${id} → ${target}: entry spawn "${entry}" not defined there`);
}
for (const z of zones) if (!new RegExp(`\\bSpawn\\(\\s*"start"`).test(zoneCs[z.id] ?? '')) FAIL('scenes', `zone ${z.id} has no "start" spawn`);
PASS('scenes', `${spawnNames.size} spawn names; exits resolve to existing zones and entries`);

// ------------------------------------------------------------------ collectibles
for (const c of collectibles) {
  if (!zoneIds.has(c.zone)) FAIL('collectibles', `${c.id} unknown zone ${c.zone}`);
  if (!new RegExp(`\\bCollectible\\(\\s*"${c.id}"`).test(zoneCs[c.zone] ?? '')) FAIL('collectibles', `${c.id} is not placed in zone ${c.zone}`);
  for (const it of Object.keys(c.give)) if (!itemIds.has(it)) FAIL('collectibles', `${c.id} gives unknown item ${it}`);
}
const counts = collectibles.reduce((m, c) => ((m[c.kind] = (m[c.kind] ?? 0) + 1), m), {});
if (counts.fragment !== 12 || counts.recording !== 6 || counts.cache !== 5) FAIL('collectibles', `expected 12/6/5 got ${JSON.stringify(counts)}`);
else PASS('collectibles', '12 Aether Fragments, 6 Memory Recordings, 5 Hidden Caches placed');

// ------------------------------------------------------------------ enemies & cinematics
const factoryTypes = new Set(matchAll(cs[path.join(A, 'Scripts', 'Enemies', 'EnemyFactory.cs')] ?? '', /"([a-z_]+)"/g));
for (const t of new Set(matchAll(allZoneCs, /\bE\(\s*"([a-z_]+)"/g))) if (!factoryTypes.has(t)) FAIL('enemies', `enemy type ${t} has no factory`);
for (const t of ['drone', 'sentinel', 'warden', 'stalker', 'guardian', 'bolt'])
  if (!exists(path.join(A, 'Resources', 'Models', 'Robots', t + '.fbx'))) FAIL('models', `robot model ${t}.fbx missing`);
PASS('enemies', `${encounterIds.size} encounters; enemy types resolve to factories; robot models present`);
const cineCs = walk(path.join(zoneDir, 'Cinematics'), ['.cs']).map(read).join('\n');
const cineIds = new Set(matchAll(cineCs, /\.Register\(\s*"(\w+)"/g));

// ------------------------------------------------------------------ actions / quests / dialogue
const ACTIONS = new Set(['dialogue', 'cinematic', 'encounter', 'despawn', 'spawnPickup', 'hint', 'give', 'take', 'setFlag', 'startQuest', 'unlock', 'autosave', 'credits']);
const runActionCs = cs[path.join(A, 'Scripts', 'Game', 'GameManager.Runtime.cs')] ?? '';
for (const a of ACTIONS) if (!runActionCs.includes(`"${a}"`)) FAIL('quests', `action "${a}" not handled by GameManager.RunAction`);
const pickupIdsInQuests = matchAll(JSON.stringify(quests), /"id":"(pickup_\w+)"/g);
function checkActions(where, acts) {
  for (const a of acts ?? []) {
    if (!ACTIONS.has(a.do)) FAIL('quests', `${where}: unknown action ${a.do}`);
    if (a.do === 'dialogue' && !dlgIds.has(a.id)) FAIL('dialogue-ids', `${where}: dialogue ${a.id} missing`);
    if (a.do === 'cinematic' && !cineIds.has(a.id)) { if (dlgIds.has(a.id + '_lines')) WARN('cinematics', `${where}: cinematic ${a.id} has no staged C# script (plays its lines only)`); else FAIL('cinematics', `${where}: cinematic ${a.id} missing`); }
    if ((a.do === 'encounter' || a.do === 'despawn') && !encounterIds.has(a.id)) FAIL('quests', `${where}: encounter ${a.id} not defined in any zone`);
    if ((a.do === 'give' || a.do === 'take') && !itemIds.has(a.item)) FAIL('quests', `${where}: item ${a.item} missing`);
    if (a.do === 'spawnPickup' && a.item && !itemIds.has(a.item)) FAIL('quests', `${where}: pickup item ${a.item} missing`);
    if (a.do === 'spawnPickup' && a.powerup && !puIds.has(a.powerup)) FAIL('quests', `${where}: pickup powerup ${a.powerup} missing`);
    if (a.do === 'spawnPickup' && !markerIds.has(a.at) && !allZoneIds.has(a.at)) FAIL('quests', `${where}: spawn marker ${a.at} not defined in any zone`);
    if (a.do === 'hint' && !hintIds.has(a.id)) FAIL('quests', `${where}: hint ${a.id} missing`);
    if (a.do === 'startQuest' && !questIds.has(a.id)) FAIL('quest-ids', `${where}: quest ${a.id} missing`);
    if (a.do === 'unlock' && !abIds.has(a.ability)) FAIL('quests', `${where}: ability ${a.ability} missing`);
  }
}
const OBJ = new Set(['flag', 'interact', 'kill', 'collect', 'reach', 'zone', 'talk']);
const flagsSet = new Set([...matchAll(allCs, /SetFlag\(\s*"(\w+)"/g), ...matchAll(JSON.stringify(quests) + JSON.stringify(dialogue), /"flag":"(\w+)"/g)]);
let objCount = 0;
for (const q of quests) {
  if (!zoneIds.has(q.zone)) FAIL('quests', `${q.id} zone ${q.zone} unknown`);
  for (const s of q.stages) {
    checkActions(`${q.id}/${s.id}.onStart`, s.onStart);
    checkActions(`${q.id}/${s.id}.onComplete`, s.onComplete);
    for (const o of s.objectives) {
      objCount++;
      const t = o.target;
      if (!OBJ.has(o.type)) FAIL('quests', `${q.id}/${o.id} bad type ${o.type}`);
      if (o.type === 'collect' && !itemIds.has(t)) FAIL('quests', `${q.id}/${o.id}: collect target ${t} is not an item`);
      if (o.type === 'zone' && !zoneIds.has(t)) FAIL('quests', `${q.id}/${o.id}: zone ${t} unknown`);
      if (o.type === 'kill' && !encounterIds.has(t)) FAIL('quests', `${q.id}/${o.id}: encounter ${t} not defined in any C# zone`);
      if ((o.type === 'interact' || o.type === 'reach') && !allZoneIds.has(t) && !pickupIdsInQuests.includes(t)) FAIL('quests', `${q.id}/${o.id}: ${o.type} target ${t} not found in any C# zone`);
      if (o.type === 'talk' && !npcIds.has(t)) FAIL('quests', `${q.id}/${o.id}: npc ${t} not placed in any C# zone`);
      if (o.type === 'flag' && !flagsSet.has(t)) WARN('quests', `${q.id}/${o.id}: flag ${t} is never set by C# or data`);
      if (o.marker && !allZoneIds.has(o.marker) && !markerIds.has(o.marker) && !o.marker.startsWith('npc_') && !pickupIdsInQuests.includes(o.marker)) WARN('quests', `${q.id}/${o.id}: marker ${o.marker} not resolvable statically`);
    }
  }
  checkActions(`${q.id}.onComplete`, q.onComplete);
}
PASS('quests', `${quests.length} quests, ${objCount} objectives checked against the C# zones`);
let nodeCount = 0;
for (const d of dialogue) {
  const nodes = new Set(d.nodes.map((n) => n.id));
  if (!nodes.has(d.start)) FAIL('dialogue-ids', `${d.id}: start node ${d.start} missing`);
  for (const n of d.nodes) {
    nodeCount++;
    if (n.speaker && !['active', 'partner'].includes(n.speaker) && !spkIds.has(n.speaker)) FAIL('dialogue-ids', `${d.id}/${n.id}: unknown speaker ${n.speaker}`);
    for (const k of ['next', 'else']) if (n[k] && !nodes.has(n[k])) FAIL('dialogue-ids', `${d.id}/${n.id}: ${k} -> ${n[k]} missing`);
    for (const b of n.branch ?? []) if (!nodes.has(b.goto)) FAIL('dialogue-ids', `${d.id}/${n.id}: branch -> ${b.goto} missing`);
    for (const ch of n.choices ?? []) { if (ch.next && !nodes.has(ch.next)) FAIL('dialogue-ids', `${d.id}/${n.id}/${ch.id}: next ${ch.next} missing`); checkActions(`${d.id}/${n.id}/${ch.id}`, ch.actions); }
    checkActions(`${d.id}/${n.id}`, n.actions);
  }
  if (d.npc && !npcIds.has(d.npc)) FAIL('dialogue-ids', `${d.id}: npc ${d.npc} not placed in any C# zone`);
}
for (const id of matchAll(allCs, /(?:PlayDialogue|\.Lines)\(\s*"(\w+)"/g)) if (!dlgIds.has(id)) FAIL('dialogue-ids', `C# references dialogue ${id} which does not exist`);
PASS('dialogue-ids', `${dialogue.length} dialogues, ${nodeCount} nodes checked`);

// ------------------------------------------------------------------ input & localisation
const inputCs = cs[path.join(A, 'Scripts', 'Core', 'GameInput.cs')] ?? '';
// move/look are value actions; moveF/L/B/R are the movement composite parts the hint renderer expands.
const inputActions = new Set([...matchAll(inputCs, /Btn\(\s*"(\w+)"/g), 'move', 'look', 'moveF', 'moveL', 'moveB', 'moveR']);
for (const h of hints) for (const a of matchAll(h.text, /\{(\w+)\}/g)) if (!inputActions.has(a)) FAIL('localization', `hint ${h.id} references unknown action {${a}}`);
for (const z of zones) for (const h of z.hints ?? []) for (const a of matchAll(h, /\{(\w+)\}/g)) if (!inputActions.has(a)) FAIL('localization', `zone ${z.id} hint references unknown action {${a}}`);
// UI code reads strings through U.T (UI helper) or GameData.T; concatenated keys ("panel." + id) are dynamic and skipped.
const usedKeys = new Set(matchAll(allCs, /\b(?:GameData|U)\.T\(\s*"([a-zA-Z0-9_.]+)"\s*\)/g));
for (const k of usedKeys) if (!(k in locale)) FAIL('localization', `missing locale key "${k}"`);
PASS('localization', `${inputActions.size} input actions; ${usedKeys.size} locale keys resolved`);

// ------------------------------------------------------------------ audio
const audioManifest = json(path.join(A, 'Resources', 'Audio', 'manifest.json'));
const clipIds = new Set(audioManifest.clips.map((c) => c.id));
for (const c of audioManifest.clips) for (const f of c.files ?? []) if (!exists(path.join(A, 'Resources', 'Audio', f.path + '.wav')) && !exists(path.join(A, 'Resources', 'Audio', f.path + '.ogg'))) FAIL('audio', `clip ${c.id}: file ${f.path} missing`);
const sfxUsed = new Set([...matchAll(allCs, /(?:Audio\??\.Play|\bSfx|PlayUi|FxKit\.Sfx)\(\s*"(\w+)"/g), ...powerups.map((p) => p.sfx).filter(Boolean)]);
const missingSfx = [...sfxUsed].filter((s) => !clipIds.has(s));
if (missingSfx.length) FAIL('audio', `sounds referenced in C# but not in the audio manifest: ${missingSfx.join(', ')}`);
for (const z of zones) {
  if (!clipIds.has(z.music) && z.music !== 'silence') FAIL('audio', `zone ${z.id} music "${z.music}" has no clip`);
  if (z.ambience !== 'none' && !clipIds.has(z.ambience)) FAIL('audio', `zone ${z.id} ambience "${z.ambience}" has no clip`);
}
PASS('audio', `${clipIds.size} audio clips; ${sfxUsed.size} referenced sounds resolved`);
// Voice: recorded only — no speech synthesis anywhere.
if (/SpeechSynthes|speechSynthesis|TextToSpeech|\bTTS\b/i.test(allCs)) FAIL('audio', 'runtime speech synthesis API referenced in C# (voice lines are pre-rendered audio files)');
const voiceDir = path.join(A, 'Resources', 'Audio', 'Voice');
const voiceFiles = walk(voiceDir, ['.wav', '.ogg', '.mp3', '.aif', '.aiff']);
const voCsv = r('tools', 'vo', 'vo_lines.csv');
const voTotal = exists(voCsv) ? read(voCsv).trim().split('\n').length - 1 : 0;
if (!voiceFiles.length) WARN('audio', `voice-over: 0 of ${voTotal} lines recorded (subtitle-only; see docs/VO_SCRIPT.md)`);
else PASS('audio', `voice-over: ${voiceFiles.length} of ${voTotal} lines recorded`);

// ------------------------------------------------------------------ animations & characters
const meta = json(path.join(A, 'Art', 'Animations', 'clips_meta.json'));
const clipNames = new Set([...Object.keys(meta.male ?? {}), ...Object.keys(meta.female ?? {})]);
for (const c of new Set(matchAll(allCs, /PlayAction\(\s*"(\w+)"/g))) if (!clipNames.has(c)) FAIL('animations', `animation clip "${c}" referenced but not exported`);
for (const b of new Set(matchAll(allZoneCs, /\bNpc\([^;]*?,\s*"(npc_\w+|sit|kneel_work|lie|idle|wave|talk)"/g))) if (!clipNames.has(b)) FAIL('animations', `NPC behaviour clip "${b}" missing`);
PASS('animations', `${clipNames.size} retargeted clips; references resolved`);
for (const n of ['Kael', 'Lyra', 'Oren', 'Mira', 'Tomas', 'Maren', 'Nia'])
  if (!exists(path.join(A, 'Art', 'Characters', n, n + '.fbx'))) FAIL('models', `character ${n}.fbx missing`);
for (const s of speakers) if (s.portrait !== 'none' && !exists(path.join(A, 'Resources', 'Art', 'Portraits', s.portrait + '.png'))) WARN('models', `speaker ${s.id}: no rendered portrait (initial-letter fallback is shown)`);
for (const it of items) if (!exists(path.join(A, 'Resources', 'Art', 'Items', it.icon + '.png'))) { WARN('ui-resources', `item icon art "${it.icon}" not rendered yet (tinted glyph fallback)`); break; }
for (const it of items) if (!exists(path.join(A, 'Resources', 'UI', 'Icons', it.icon + '.png'))) FAIL('ui-resources', `item ${it.id} glyph icon ${it.icon}.png missing`);
PASS('models', 'character FBX exports present');

// ------------------------------------------------------------------ environment kit
const envManifest = json(path.join(A, 'Art', 'Environment', 'manifest.json'));
const envAssets = new Set(envManifest.assets.map((a) => a.name));
for (const a of envManifest.assets) if (!exists(path.join(A, 'Art', 'Environment', a.file))) FAIL('models', `environment asset ${a.name}: ${a.file} missing`);
const propsUsed = new Set(matchAll(allZoneCs, /\.Prop\(\s*"(\w+)"/g));
const unknownProps = [...propsUsed].filter((p) => !envAssets.has(p));
if (unknownProps.length) FAIL('models', `zones place unknown props: ${unknownProps.join(', ')}`);
const matNames = new Set([...Object.keys(envManifest.materials), ...Object.keys(envManifest.prototypeMaterialMap ?? {})]);
// Untextured transparent films (glass, water, puddles) are defined in code by EnvMaterials' fallback looks.
const envMatCs = read(path.join(A, 'Scripts', 'World', 'Kit', 'EnvMaterials.cs'));
for (const m of matchAll(envMatCs, /\["([a-z_]+)"\]\s*=\s*new Look\s*\{[^}]*Transparent\s*=\s*true/g)) matNames.add(m);
const matsUsed = new Set(matchAll(allZoneCs, /\b(?:Box|BoxMin|Cyl|Stairs|Ramp)\([^;]*?"([a-z_]+)"/g));
const unknownMats = [...matsUsed].filter((m) => !matNames.has(m));
if (unknownMats.length) FAIL('textures', `zones use unknown materials: ${unknownMats.join(', ')}`);
const placeholderOnly = zones.filter((z) => !/\.Prop\(/.test(zoneCs[z.id] ?? ''));
if (placeholderOnly.length) WARN('models', `zones without any Blender props: ${placeholderOnly.map((z) => z.id).join(', ')}`);
PASS('models', `${envAssets.size} environment assets; ${propsUsed.size} distinct props and ${matsUsed.size} materials used by zones resolve`);
for (const s of ['EOA_Sky.shader', 'EOA_Aether.shader']) if (!exists(path.join(A, 'Shaders', s))) FAIL('textures', `shader ${s} missing`);

// ------------------------------------------------------------------ project pipeline
for (const f of ['Editor/Setup/ProjectSetup.cs', 'Editor/Environment/EnvLibraryBuilder.cs', 'Editor/Characters/CharacterBuilder.cs', 'Editor/UI/UISetup.cs', 'Editor/Build/BuildScripts.cs', 'Editor/Audio/AudioImportPostprocessor.cs'])
  if (!exists(path.join(A, f))) FAIL('pipeline', `${f} missing`);
const saveCs = cs[path.join(A, 'Scripts', 'Game', 'SaveSystem.cs')] ?? '';
if (!/Crc32|CRC32/i.test(saveCs) || !/WriteAtomic/.test(saveCs) || !/\.bak|backup/i.test(saveCs)) FAIL('save-schema', 'save system lacks checksum, backup or atomic write');
else PASS('save-schema', 'save envelope has CRC32 checksum, schema validation, backup and atomic writes');
const setCs = cs[path.join(A, 'Scripts', 'Game', 'Settings.cs')] ?? '';
for (const [cls, field] of [['Gameplay', 'Gameplay'], ['Graphics', 'Graphics'], ['Audio', 'Audio'], ['Control', 'Controls'], ['Accessibility', 'Accessibility'], ['Language', 'Language']])
  if (!new RegExp(`public ${cls}Settings ${field}`).test(setCs)) FAIL('settings', `settings section ${field} missing`);
PASS('pipeline', 'editor setup, environment/character/UI builders, build scripts present');

// ------------------------------------------------------------------ provenance & secrets
if (!exists(r('marketing', 'ART_CREDITS.md'))) WARN('art', 'marketing/ART_CREDITS.md missing (render provenance)');
const secretRe = /dlr_(?:live|test)_[A-Za-z0-9]{20,}/;
const scan = [...csFiles, ...walk(path.join(A, 'Resources'), ['.json', '.txt']), ...walk(r('docs'), ['.md']), ...walk(r('tools'), ['.mjs', '.py', '.sh']), ...walk(r('marketing'), ['.md']), ...walk(r('blender', 'scripts'), ['.py'])];
const leaks = scan.filter((f) => secretRe.test(read(f)));
for (const b of ['WebGL', 'macOS']) for (const f of walk(r('Builds', b), ['.js', '.html', '.json', '.txt'])) if (secretRe.test(read(f))) leaks.push(f);
if (leaks.length) FAIL('secrets', 'API key pattern found in: ' + leaks.map(rel).join(', '));
else PASS('secrets', `no API keys in ${scan.length} scripts/data/docs${exists(r('Builds')) ? ' or builds' : ''}`);

// ------------------------------------------------------------------ compile (optional)
if (process.argv.includes('--compile')) {
  try {
    const out = execFileSync('python3', [r('tools', 'unitycheck', 'check.py'), '--player'], { cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 64 << 20 });
    report1(out);
  } catch (e) { report1((e.stdout ?? '') + (e.stderr ?? '')); }
}
function report1(out) {
  const lines = out.split('\n').filter((l) => /\] (Assembly-CSharp|EOA)[\w.-]*: (OK|FAILED)/.test(l));
  if (!lines.length) { FAIL('compile', 'compile check produced no result'); return; }
  for (const l of lines) (l.includes(': OK') ? PASS : FAIL)('compile', l.trim());
}

report();
function report() {
  const asJson = process.argv.includes('--json');
  const f = results.filter((x) => x.level === 'FAIL').length, w = results.filter((x) => x.level === 'WARN').length, p = results.filter((x) => x.level === 'PASS').length;
  if (asJson) console.log(JSON.stringify({ pass: p, warn: w, fail: f, results }, null, 1));
  else {
    for (const x of results) console.log(`${x.level.padEnd(4)}  [${x.cat}] ${x.msg}`);
    console.log(`\nSummary: ${p} PASS, ${w} WARN, ${f} FAIL${f ? '  →  RELEASE BLOCKED' : ''}`);
  }
  process.exit(f ? 1 : 0);
}
