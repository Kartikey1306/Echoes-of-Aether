#!/usr/bin/env node
// Static content validation for Echoes of Aether.
// Usage: node tools/validation/validate.mjs [--json]
// Prints PASS / WARN / FAIL lines. Exits 1 if any FAIL (blocks release).
import fs from 'node:fs';
import path from 'node:path';

const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', '..');
const r = (...p) => path.join(ROOT, ...p);
const read = (p) => fs.readFileSync(r(p), 'utf8');
const json = (p) => JSON.parse(read(p));
const results = [];
const PASS = (cat, msg) => results.push({ level: 'PASS', cat, msg });
const WARN = (cat, msg) => results.push({ level: 'WARN', cat, msg });
const FAIL = (cat, msg) => results.push({ level: 'FAIL', cat, msg });

function walk(dir, ext) {
  const out = [];
  for (const e of fs.readdirSync(r(dir), { withFileTypes: true })) {
    const p = path.join(dir, e.name);
    if (e.isDirectory()) out.push(...walk(p, ext));
    else if (ext.some((x) => e.name.endsWith(x))) out.push(p);
  }
  return out;
}
const srcFiles = walk('src', ['.ts']);
const src = Object.fromEntries(srcFiles.map((f) => [f, read(f)]));
const allSrc = Object.values(src).join('\n');
const matchAll = (text, re) => [...text.matchAll(re)].map((m) => m[1]);

// ------------------------------------------------------------------ Load data
let items, powerups, abilities, enemies, quests, dialogue, speakers, zones, collectibles, hints, locale;
try {
  items = json('src/data/items.json').items;
  powerups = json('src/data/powerups.json').powerups;
  abilities = json('src/data/abilities.json');
  enemies = json('src/data/enemies.json').enemies;
  quests = json('src/data/quests.json').quests;
  dialogue = json('src/data/dialogue.json').dialogues;
  speakers = json('src/data/speakers.json').speakers;
  zones = json('src/data/zones.json').zones;
  collectibles = json('src/data/collectibles.json').collectibles;
  hints = json('src/data/hints.json').hints;
  locale = json('src/data/locale/en.json');
  PASS('data', 'All JSON data files parse');
} catch (e) {
  FAIL('data', 'JSON parse error: ' + e.message);
  report();
}
const ids = (arr) => new Set(arr.map((x) => x.id));
const itemIds = ids(items), questIds = ids(quests), dlgIds = ids(dialogue), spkIds = ids(speakers), zoneIds = ids(zones), colIds = ids(collectibles), puIds = ids(powerups), abIds = ids(abilities.abilities), skillIds = ids(abilities.tree), enemyIds = ids(enemies), hintIds = ids(hints);

// ------------------------------------------------------------------ Duplicate IDs
for (const [name, arr] of Object.entries({ items, powerups, abilities: abilities.abilities, skills: abilities.tree, enemies, quests, dialogue, speakers, zones, collectibles, hints })) {
  const seen = new Set(), dup = new Set();
  for (const x of arr) (seen.has(x.id) ? dup : seen).add(x.id);
  if (dup.size) FAIL('duplicate-ids', `${name}: duplicate ids ${[...dup].join(', ')}`);
  else PASS('duplicate-ids', `${name}: ${arr.length} unique ids`);
}

// ------------------------------------------------------------------ Icons
const iconNames = new Set(matchAll(read('src/ui/Icons.ts'), /^\s{2}(\w+): \(/gm));
for (const it of items) if (!iconNames.has(it.icon)) FAIL('ui-resources', `item ${it.id} icon "${it.icon}" missing from Icons.ts`);
for (const p of powerups) if (!iconNames.has(p.icon)) FAIL('ui-resources', `powerup ${p.id} icon "${p.icon}" missing`);
for (const a of abilities.abilities) if (!iconNames.has(a.icon)) FAIL('ui-resources', `ability ${a.id} icon "${a.icon}" missing`);
PASS('ui-resources', `${iconNames.size} icons defined; item/powerup/ability icons checked`);

// ------------------------------------------------------------------ Items / powerups / abilities
for (const it of items) {
  for (const f of ['id', 'name', 'category', 'description', 'icon', 'rarity', 'stack', 'effect']) if (it[f] === undefined) FAIL('items', `${it.id} missing field ${f}`);
  if (!['aether', 'powerups', 'quest', 'upgrades', 'lore'].includes(it.category)) FAIL('items', `${it.id} bad category ${it.category}`);
  if (!(it.stack > 0)) FAIL('items', `${it.id} stack must be > 0`);
  if (it.quest && !questIds.has(it.quest)) FAIL('items', `${it.id} references unknown quest ${it.quest}`);
  if (it.effect.type === 'powerup' && !puIds.has(it.effect.powerup)) FAIL('items', `${it.id} unknown powerup ${it.effect.powerup}`);
  if (it.effect.type === 'lore' && !dlgIds.has(it.effect.lore)) FAIL('items', `${it.id} lore "${it.effect.lore}" has no dialogue entry`);
}
for (const p of powerups) if (!itemIds.has(p.item)) FAIL('powerups', `${p.id} item ${p.item} missing`);
for (const a of abilities.abilities) if (a.unlock !== 'start' && !questIds.has(a.unlock) && !itemIds.has(a.unlock)) FAIL('abilities', `${a.id} unlock "${a.unlock}" unknown`);
for (const n of abilities.tree) {
  if (!abIds.has(n.ability)) FAIL('abilities', `skill ${n.id} unknown ability ${n.ability}`);
  for (const q of n.requires) if (!skillIds.has(q)) FAIL('abilities', `skill ${n.id} requires unknown ${q}`);
}
PASS('items', `${items.length} items, ${powerups.length} powerups, ${abilities.abilities.length} abilities, ${abilities.tree.length} skill nodes checked`);

// ------------------------------------------------------------------ Zones and scene registry
const worldTs = read('src/world/World.ts');
const registered = new Set(matchAll(worldTs, /^\s{2}(\w+): async \(\) => \(await import\('\.\/zones\/(\w+)'\)/gm));
for (const z of zones) {
  if (!registered.has(z.id)) FAIL('scenes', `zone ${z.id} has no registered builder in World.ts`);
  const file = `src/world/zones/${z.id[0].toUpperCase()}${z.id.slice(1)}Zone.ts`;
  if (!fs.existsSync(r(file))) FAIL('scenes', `zone ${z.id} source ${file} missing`);
  if (!fs.existsSync(r('public', z.art))) WARN('textures', `zone ${z.id} loading art public/${z.art} missing (procedural gradient fallback is used)`);
  if (!z.hints?.length) WARN('scenes', `zone ${z.id} has no loading hints`);
}
PASS('scenes', `${zones.length} zones registered`);
const zoneSrc = Object.fromEntries(zones.map((z) => [z.id, src[`src/world/zones/${z.id[0].toUpperCase()}${z.id.slice(1)}Zone.ts`] ?? '']));
// IDs defined in zone code: any quoted id-like string inside zone sources
const zoneIdsIn = (zid) => new Set(matchAll(zoneSrc[zid], /['"`]((?:i|t|e|x|c|g|npc|pickup)_[a-z0-9_]+)['"`]/g).concat(matchAll(zoneSrc[zid], /id: '([a-z0-9_]+)'/g)));
const allZoneIds = new Set(zones.flatMap((z) => [...zoneIdsIn(z.id)]));
const npcIds = new Set(matchAll(allSrc, /npcs\.push\(([\s\S]*?)\);/g).flatMap((blk) => matchAll(blk, /id: '([a-z]+)'/g)));
const markerIds = new Set(matchAll(allSrc, /markers\.(\w+)\s*=/g).concat(matchAll(allSrc, /markers\[['"](\w+)['"]\]/g)));

// ------------------------------------------------------------------ Collectibles
for (const c of collectibles) {
  if (!zoneIds.has(c.zone)) FAIL('collectibles', `${c.id} unknown zone ${c.zone}`);
  if (!zoneIdsIn(c.zone).has(c.id)) FAIL('collectibles', `${c.id} is not placed in zone ${c.zone}`);
  for (const it of Object.keys(c.give)) if (!itemIds.has(it)) FAIL('collectibles', `${c.id} gives unknown item ${it}`);
}
const counts = collectibles.reduce((m, c) => ((m[c.kind] = (m[c.kind] ?? 0) + 1), m), {});
if (counts.fragment !== 12 || counts.recording !== 6 || counts.cache !== 5) FAIL('collectibles', `expected 12/6/5 got ${JSON.stringify(counts)}`);
else PASS('collectibles', '12 Aether Fragments, 6 Memory Recordings, 5 Hidden Caches placed');

// ------------------------------------------------------------------ Cinematics / encounters / flags
const cineIds = new Set(matchAll(read('src/game/Cinematics.ts'), /register\('(\w+)'/g));
const flagsSet = new Set([...matchAll(allSrc, /setFlag\('(\w+)'/g), ...matchAll(allSrc, /flag: '(\w+)'/g)]);
const encounterIds = new Set(matchAll(allSrc, /id: '(e_[a-z0-9_]+)', spawn:/g));
const enemyTypesUsed = new Set(matchAll(allSrc, /type: '([a-z_]+)', pos:/g));
const factories = new Set(matchAll(worldTs, /^\s{2}(\w+): \(env\)/gm));
for (const t of enemyTypesUsed) if (!factories.has(t)) FAIL('enemies', `enemy type ${t} used in encounters has no factory`);
for (const f of factories) if (!enemyIds.has(f.replace('_vault', ''))) FAIL('enemies', `factory ${f} has no enemies.json entry`);
PASS('enemies', `${encounterIds.size} encounters, ${factories.size} enemy factories`);

// ------------------------------------------------------------------ Actions
const ACTIONS = new Set(['dialogue', 'cinematic', 'encounter', 'despawn', 'spawnPickup', 'hint', 'give', 'take', 'setFlag', 'startQuest', 'unlock', 'autosave', 'credits']);
function checkActions(where, acts) {
  for (const a of acts ?? []) {
    if (!ACTIONS.has(a.do)) FAIL('quests', `${where}: unknown action ${a.do}`);
    if (a.do === 'dialogue' && !dlgIds.has(a.id)) FAIL('dialogue-ids', `${where}: dialogue ${a.id} missing`);
    if (a.do === 'cinematic' && !cineIds.has(a.id)) { if (dlgIds.has(a.id + '_lines')) WARN('cinematics', `${where}: cinematic ${a.id} has no script (plays its lines only)`); else FAIL('cinematics', `${where}: cinematic ${a.id} missing`); }
    if ((a.do === 'encounter' || a.do === 'despawn') && !encounterIds.has(a.id)) FAIL('quests', `${where}: encounter ${a.id} not defined in any zone`);
    if ((a.do === 'give' || a.do === 'take') && !itemIds.has(a.item)) FAIL('quests', `${where}: item ${a.item} missing`);
    if (a.do === 'spawnPickup' && a.item && !itemIds.has(a.item)) FAIL('quests', `${where}: pickup item ${a.item} missing`);
    if (a.do === 'spawnPickup' && a.powerup && !puIds.has(a.powerup)) FAIL('quests', `${where}: pickup powerup ${a.powerup} missing`);
    if (a.do === 'spawnPickup' && !markerIds.has(a.at)) FAIL('quests', `${where}: spawn marker ${a.at} not defined in any zone`);
    if (a.do === 'hint' && !hintIds.has(a.id)) FAIL('quests', `${where}: hint ${a.id} missing`);
    if (a.do === 'startQuest' && !questIds.has(a.id)) FAIL('quest-ids', `${where}: quest ${a.id} missing`);
    if (a.do === 'unlock' && !abIds.has(a.ability)) FAIL('quests', `${where}: ability ${a.ability} missing`);
  }
}

// ------------------------------------------------------------------ Quests
const OBJ = new Set(['flag', 'interact', 'kill', 'collect', 'reach', 'zone', 'talk']);
let objCount = 0;
for (const q of quests) {
  if (!zoneIds.has(q.zone)) FAIL('quests', `${q.id} zone ${q.zone} unknown`);
  const st = new Set();
  for (const s of q.stages) {
    if (st.has(s.id)) FAIL('quests', `${q.id} duplicate stage ${s.id}`);
    st.add(s.id);
    checkActions(`${q.id}/${s.id}.onStart`, s.onStart);
    checkActions(`${q.id}/${s.id}.onComplete`, s.onComplete);
    for (const o of s.objectives) {
      objCount++;
      if (!OBJ.has(o.type)) FAIL('quests', `${q.id}/${s.id}/${o.id} bad type ${o.type}`);
      const t = o.target;
      if (o.type === 'collect' && !itemIds.has(t)) FAIL('quests', `${q.id}/${o.id}: collect target ${t} is not an item`);
      if (o.type === 'zone' && !zoneIds.has(t)) FAIL('quests', `${q.id}/${o.id}: zone ${t} unknown`);
      if (o.type === 'kill' && !encounterIds.has(t)) FAIL('quests', `${q.id}/${o.id}: encounter ${t} not defined`);
      if ((o.type === 'interact' || o.type === 'reach') && !allZoneIds.has(t) && !matchAll(JSON.stringify(quests), /"id":"(pickup_\w+)"/g).includes(t)) FAIL('quests', `${q.id}/${o.id}: ${o.type} target ${t} not found in any zone`);
      if (o.type === 'talk' && !npcIds.has(t)) FAIL('quests', `${q.id}/${o.id}: npc ${t} not placed`);
      if (o.type === 'flag' && !flagsSet.has(t)) WARN('quests', `${q.id}/${o.id}: flag ${t} is never set by code or data (only by tests?)`);
      if (o.marker && !allZoneIds.has(o.marker) && !markerIds.has(o.marker) && !o.marker.startsWith('npc_') && !matchAll(JSON.stringify(quests), /"id":"(pickup_\w+)"/g).includes(o.marker)) WARN('quests', `${q.id}/${o.id}: marker ${o.marker} not resolvable statically`);
    }
  }
  checkActions(`${q.id}.onComplete`, q.onComplete);
}
PASS('quests', `${quests.length} quests, ${objCount} objectives checked`);
const mains = quests.filter((q) => q.type === 'main').length, sides = quests.filter((q) => q.type === 'side').length;
if (mains < 5 || sides < 4) FAIL('quests', `expected >= 5 main and >= 4 side quests, got ${mains}/${sides}`);

// ------------------------------------------------------------------ Dialogue
let nodeCount = 0;
const condOk = (c) => {
  const m = c.replace(/^!/, '').split(':');
  switch (m[0]) {
    case 'flag': return true;
    case 'quest': return questIds.has(m[1]) && ['none', 'active', 'done'].includes(m[2]);
    case 'stage': return questIds.has(m[1]) && quests.find((q) => q.id === m[1]).stages.some((s) => s.id === m[2]);
    case 'item': return itemIds.has(m[1].split('>=')[0]);
    case 'char': return ['kael', 'lyra'].includes(m[1]);
    case 'ability': return abIds.has(m[1]);
    case 'revealed': case 'collected': return true;
    default: return false;
  }
};
for (const d of dialogue) {
  const nodes = new Set(d.nodes.map((n) => n.id));
  if (!nodes.has(d.start)) FAIL('dialogue-ids', `${d.id}: start node ${d.start} missing`);
  for (const n of d.nodes) {
    nodeCount++;
    if (n.speaker && !['active', 'partner'].includes(n.speaker) && !spkIds.has(n.speaker)) FAIL('dialogue-ids', `${d.id}/${n.id}: unknown speaker ${n.speaker}`);
    for (const k of ['next', 'else']) if (n[k] && !nodes.has(n[k])) FAIL('dialogue-ids', `${d.id}/${n.id}: ${k} -> ${n[k]} missing`);
    for (const b of n.branch ?? []) { if (!nodes.has(b.goto)) FAIL('dialogue-ids', `${d.id}/${n.id}: branch -> ${b.goto} missing`); for (const c of b.if ?? []) if (!condOk(c)) FAIL('dialogue-ids', `${d.id}/${n.id}: bad condition ${c}`); }
    for (const c of n.conditions ?? []) if (!condOk(c)) FAIL('dialogue-ids', `${d.id}/${n.id}: bad condition ${c}`);
    for (const ch of n.choices ?? []) { if (ch.next && !nodes.has(ch.next)) FAIL('dialogue-ids', `${d.id}/${n.id}/${ch.id}: next ${ch.next} missing`); checkActions(`${d.id}/${n.id}/${ch.id}`, ch.actions); }
    checkActions(`${d.id}/${n.id}`, n.actions);
  }
  if (d.npc && !npcIds.has(d.npc)) FAIL('dialogue-ids', `${d.id}: npc ${d.npc} not placed in any zone`);
}
for (const id of matchAll(allSrc, /(?:playDialogue|lines)\(\s*'(\w+)'/g)) if (!dlgIds.has(id)) FAIL('dialogue-ids', `code references dialogue ${id} which does not exist`);
for (const id of matchAll(allSrc, /dialogue: '(dlg_\w+)'/g)) if (!dlgIds.has(id)) FAIL('dialogue-ids', `npc dialogue ${id} missing`);
PASS('dialogue-ids', `${dialogue.length} dialogues, ${nodeCount} nodes checked`);

// ------------------------------------------------------------------ Hints & input actions
const inputActions = new Set(matchAll(read('src/core/Input.ts'), /^\s{4}(\w+): \{ kb:/gm));
for (const h of hints) for (const a of matchAll(h.text, /\{(\w+)\}/g)) if (!inputActions.has(a)) FAIL('localization', `hint ${h.id} references unknown action {${a}}`);
for (const z of zones) for (const h of z.hints) for (const a of matchAll(h, /\{(\w+)\}/g)) if (!inputActions.has(a)) FAIL('localization', `zone ${z.id} hint references unknown action {${a}}`);
PASS('localization', `${inputActions.size} input actions; hint placeholders checked`);

// ------------------------------------------------------------------ Localization keys
const used = new Set(matchAll(allSrc, /\bt\('([a-zA-Z0-9_.]+)'\)/g));
for (const k of used) if (!(k in locale)) FAIL('localization', `missing locale key "${k}"`);
const dynamic = new Set(['hud.ability', 'hud.dash', 'hud.bolt', 'settings.gameplay', 'settings.graphics', 'settings.audio', 'settings.controls', 'settings.accessibility', 'settings.language', 'panel.inventory', 'panel.map', 'panel.journal', 'panel.skills', 'cs.kael.role', 'cs.lyra.role', 'cs.kael.desc', 'cs.lyra.desc', 'cs.kael.style', 'cs.lyra.style']);
const unused = Object.keys(locale).filter((k) => !used.has(k) && !dynamic.has(k));
if (unused.length) WARN('localization', `${unused.length} locale keys not referenced statically: ${unused.slice(0, 8).join(', ')}${unused.length > 8 ? '…' : ''}`);
PASS('localization', `${used.size} UI string keys resolved in en.json`);

// ------------------------------------------------------------------ Audio
const audioTs = read('src/audio/AudioEngine.ts');
const recipes = new Set(matchAll(audioTs, /^\s{2}(\w+): \(a, o, t, v\)/gm));
const sfxUsed = new Set([...matchAll(allSrc, /(?:audio\.play|\.sfx|sfx)\(\s*'(\w+)'/g), ...powerups.map((p) => p.sfx)]);
for (const s of sfxUsed) if (!recipes.has(s)) FAIL('audio', `sound "${s}" has no synthesis recipe`);
const moods = new Set(['menu', 'explore', 'combat', 'boss', 'sidequest', 'tension', 'ending', 'silence']);
const ambs = new Set(['rain_city', 'metro_drip', 'facility_hum', 'vault_hum', 'wind_roof', 'core_drone', 'none']);
for (const z of zones) { if (!moods.has(z.music)) FAIL('audio', `zone ${z.id} music "${z.music}" unknown`); if (!ambs.has(z.ambience)) FAIL('audio', `zone ${z.id} ambience "${z.ambience}" unknown`); }
for (const m of matchAll(allSrc, /setMusic\('(\w+)'/g)) if (!moods.has(m)) FAIL('audio', `music mood ${m} unknown`);
PASS('audio', `${recipes.size} synthesized sounds; ${sfxUsed.size} referenced sounds resolved`);

// ------------------------------------------------------------------ Animations
const animsTs = read('src/actors/human/Anims.ts') + read('src/actors/enemies/EnemyAnims.ts');
const clipNames = new Set(matchAll(animsTs, /new (?:KeyClip|FnClip)\('(\w+)'/g));
const clipUsed = new Set([...matchAll(allSrc, /playClip\('(\w+)'/g), ...matchAll(allSrc, /clips\.(\w+)/g), ...matchAll(allSrc, /clips\['(\w+)'\]/g)]);
for (const c of clipUsed) if (!clipNames.has(c)) FAIL('animations', `animation clip "${c}" referenced but not defined`);
for (const z of [...matchAll(allSrc, /behaviour: '(\w+)'/g)]) if (z !== 'wander' && z !== 'idle' && !clipNames.has(z)) FAIL('animations', `NPC behaviour clip "${z}" missing`);
PASS('animations', `${clipNames.size} clips defined; ${clipUsed.size} references resolved`);

// ------------------------------------------------------------------ Models (procedural looks)
const looksTs = read('src/actors/human/Looks.ts');
const lookIds = new Set(matchAll(looksTs, /id: '(\w+)'/g));
for (const s of speakers) if (s.portrait !== 'none' && !lookIds.has(s.portrait) && !fs.existsSync(r('public/art/portraits', s.portrait + '.png')) && !['bolt', 'guardian', 'maren'].includes(s.portrait)) WARN('models', `speaker ${s.id} portrait "${s.portrait}" has no model or art`);
for (const n of npcIds) if (n !== 'bolt' && !lookIds.has(n)) FAIL('models', `npc ${n} has no look definition`);
PASS('models', `${lookIds.size} character looks; robots built procedurally`);

// ------------------------------------------------------------------ Save schema & settings
const gsTs = read('src/game/GameState.ts');
const saveTs = read('src/game/SaveSystem.ts');
if (!/export function validateState/.test(gsTs)) FAIL('save-schema', 'validateState missing');
if (!/crc32/.test(saveTs) || !/\.bak/.test(saveTs) || !/writeAtomic/.test(saveTs)) FAIL('save-schema', 'save system lacks checksum, backup or atomic write');
else PASS('save-schema', 'save envelope has checksum, schema validation, backup and atomic writes');
const setTs = read('src/game/Settings.ts');
for (const sec of ['gameplay', 'graphics', 'audio', 'controls', 'accessibility', 'language']) if (!new RegExp(`${sec}: \\{`).test(setTs)) FAIL('settings', `settings section ${sec} missing`);
if (!/sanitizeSettings/.test(setTs)) FAIL('settings', 'settings sanitizer missing');
else PASS('settings', 'six settings sections with sanitizer');

// ------------------------------------------------------------------ UI resources & fonts
for (const f of ['@fontsource/rajdhani', '@fontsource/inter']) if (!fs.existsSync(r('node_modules', f))) FAIL('ui-resources', `font package ${f} missing`);
if (!fs.existsSync(r('src/ui/styles.css'))) FAIL('ui-resources', 'styles.css missing');
PASS('ui-resources', 'fonts and stylesheet present');

// ------------------------------------------------------------------ Dependencies
const pkg = json('package.json');
for (const [name, ver] of Object.entries({ ...pkg.dependencies, ...pkg.devDependencies })) {
  const p = r('node_modules', name, 'package.json');
  if (!fs.existsSync(p)) FAIL('dependencies', `${name}@${ver} not installed`);
}
PASS('dependencies', `${Object.keys({ ...pkg.dependencies, ...pkg.devDependencies }).length} dependencies installed`);

// ------------------------------------------------------------------ Secrets
const secretRe = /dlr_(?:live|test)_[A-Za-z0-9]{20,}/;
const scanFiles = [...walk('src', ['.ts', '.json', '.css']), ...walk('docs', ['.md']), ...walk('tools', ['.mjs', '.sh']), 'index.html', 'package.json'];
const leaks = scanFiles.filter((f) => secretRe.test(read(f)));
if (fs.existsSync(r('dist'))) for (const f of walk('dist', ['.js', '.html', '.json'])) if (secretRe.test(read(f))) leaks.push(f);
if (leaks.length) FAIL('secrets', 'API key pattern found in: ' + leaks.join(', '));
else PASS('secrets', `no API keys in ${scanFiles.length} source/doc files${fs.existsSync(r('dist')) ? ' or the build' : ''}`);

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
