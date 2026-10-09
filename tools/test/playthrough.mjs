// Full main-story playthrough using the test API. Usage: node tools/test/playthrough.mjs [kael|lyra]
import { chromium } from '@playwright/test';
const hero = process.argv[2] ?? 'kael';
const base = process.env.EOA_URL ?? 'http://localhost:5173/';
const out = 'tools/capture/out/';
const browser = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--mute-audio'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const errors = [];
page.on('pageerror', (e) => errors.push('[pageerror] ' + e.message));
page.on('console', (m) => { if (m.type() === 'error') errors.push('[console] ' + m.text()); });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const E = (fn, arg) => page.evaluate(fn, arg);
const state = () => E(() => window.__eoa.state());
let step = 0;
const log = (...a) => console.log(`[${String(++step).padStart(2, '0')}]`, ...a);
const shot = (n) => page.screenshot({ path: out + 'pt_' + n + '.png' });
const flush = async (n = 40) => { for (let i = 0; i < n; i++) { const s = await E(() => ({ d: window.__eoa.game.dialogue.active, c: window.__eoa.game.cinematics.active })); if (!s.d && !s.c) break; await E(() => { window.__eoa.advanceDialogue(); window.__eoa.pickChoice(0); if (window.__eoa.game.cinematics.active) window.__eoa.skipCinematic(); }); await sleep(150); } };
const waitFor = async (desc, fn, arg, timeout = 60000) => {
  const t0 = Date.now();
  while (Date.now() - t0 < timeout) {
    if (await E(fn, arg)) return true;
    await flush(3);
    await sleep(250);
  }
  throw new Error('Timeout waiting for: ' + desc);
};
const stageOf = (q) => E((q) => { const s = window.__eoa.game.gs.d.quests[q]; if (!s) return 'none'; if (s.status === 'done') return 'done'; return window.__eoa.data.quests[q].stages[s.stage].id; }, q);
const expectStage = async (q, st, timeout = 60000) => { await waitFor(`${q} at ${st}`, ([q, st]) => { const s = window.__eoa.game.gs.d.quests[q]; if (!s) return st === 'none'; if (s.status === 'done') return st === 'done'; return window.__eoa.data.quests[q].stages[s.stage].id === st; }, [q, st], timeout); log(`${q} -> ${st}`); };
const zoneIs = (z) => waitFor('zone ' + z, (z) => window.__eoa.state().zone === z && window.__eoa.state().mode === 'play', z, 90000);
const tp = (x, y, z) => E(([x, y, z]) => window.__eoa.teleport(x, y, z), [x, y, z]);
const interact = (id) => E((id) => window.__eoa.interactWith(id), id);
const kill = async (enc) => { await waitFor('enemies of ' + enc, (e) => window.__eoa.game.world.enemies.some((x) => x.encounterId === e && x.alive) || window.__eoa.game.gs.isDefeated(e), enc, 20000); for (let i = 0; i < 6; i++) { await E((e) => window.__eoa.killEncounter(e), enc); await sleep(1800); if (await E((e) => window.__eoa.game.gs.isDefeated(e), enc)) break; } };
const invuln = () => E(() => { const p = window.__eoa.game.player; if (p) { p.invuln = 9999; p.health = p.stats.maxHealth; } });
const t0 = Date.now();
try {
  await page.goto(base + `?autostart=${hero}&slot=2`, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 180000 });
  await zoneIs('plaza');
  // Intro cinematic plays automatically
  await sleep(3000); await shot('intro'); await flush(60);
  await expectStage('m1_awakening', 'wake');
  await E(() => window.__eoa.setFlag('tut_moved'));
  await expectStage('m1_awakening', 'monument');
  await tp(0, 0.8, 8.5); await sleep(500); await interact('i_monument');
  await expectStage('m1_awakening', 'fight');
  await shot('m1_fight');
  await kill('e_plaza_drones');
  await expectStage('m1_awakening', 'powerup');
  await tp(3.5, 0.2, 9.4); await sleep(1500);
  await expectStage('m1_awakening', 'meet');
  await tp(16, 0.3, -16); await sleep(2000); await shot('m1_meeting'); await flush(80);
  await expectStage('m1_awakening', 'done');
  await expectStage('m2_dead_signal', 'enter');
  // ---- M2
  await tp(-27, -4.0, 16.4); await zoneIs('metro'); await shot('m2_metro');
  await expectStage('m2_dead_signal', 'concourse');
  await kill('e_metro_concourse');
  await expectStage('m2_dead_signal', 'power');
  for (const [id, n] of [['i_junction_1', 3], ['i_junction_2', 2], ['i_junction_3', 1]]) for (let i = 0; i < n; i++) { await interact(id); await sleep(120); }
  await expectStage('m2_dead_signal', 'transmitter');
  await kill('e_metro_platform');
  await tp(-34, 0.1, 37.5); await sleep(400); await interact('i_transmitter'); await flush(60);
  await expectStage('m2_dead_signal', 'spur');
  await kill('e_metro_tunnel');
  await tp(64, -1.2, 55); await zoneIs('facility'); await shot('m3_facility');
  // ---- M3
  await expectStage('m3_researcher', 'labs');
  await tp(-16, 0.1, 15); await expectStage('m3_researcher', 'logs');
  await kill('e_fac_labs');
  for (const id of ['i_log_echo', 'i_log_keys', 'i_log_cascade']) { await interact(id); await sleep(400); await flush(20); }
  await expectStage('m3_researcher', 'data');
  await interact('i_maren_terminal'); await flush(40);
  await expectStage('m3_researcher', 'truth');
  // Echo Sight as Lyra next to the hidden wall
  if ((await state()).character !== 'lyra') { await E(() => window.__eoa.game.swapCharacter()); await sleep(800); }
  await tp(-11, 0.1, -10); await sleep(400);
  await E(() => { const p = window.__eoa.game.player; p.energy = 100; p.cdAbility = 0; }); await E(() => window.__eoa.press('ability')); await sleep(2500);
  await shot('m3_echo');
  await tp(-24, 0.1, -16); await sleep(500); await interact('i_maren_final'); await flush(60);
  await expectStage('m3_researcher', 'elite');
  await tp(0, 0.1, 22); await sleep(1500); await shot('m3_warden');
  await kill('e_fac_warden');
  await expectStage('m3_researcher', 'clearance');
  await tp(0, 0.1, 10.5); await sleep(500); await interact('pickup_clearance'); await sleep(800);
  await expectStage('m3_researcher', 'done');
  await expectStage('m4_vault', 'lift');
  // ---- M4
  await tp(-37, 0.1, -9); await sleep(400); await E(() => window.__eoa.interact()); await zoneIs('vault'); await shot('m4_vault');
  await expectStage('m4_vault', 'traverse');
  await kill('e_vault_hall');
  await tp(0, 0.1, 42); await expectStage('m4_vault', 'puzzle');
  for (const [id, n] of [['i_resonator_1', 2], ['i_resonator_3', 3]]) for (let i = 0; i < n; i++) { await interact(id); await sleep(120); }
  await expectStage('m4_vault', 'upgrade');
  await tp(0, 0.1, 63.5); await sleep(1200); await interact('i_attunement'); await flush(40);
  await expectStage('m4_vault', 'guardian');
  await kill('e_vault_deep');
  await invuln();
  await tp(0, 0.1, 87); await sleep(1500); await shot('m4_guardian'); await flush(60);
  await expectStage('m4_vault', 'survive');
  for (let i = 0; i < 50; i++) { await invuln(); await sleep(1000); if (await E(() => window.__eoa.game.world.zone.blastOpen)) break; }
  await shot('m4_door');
  await tp(0, 0.1, 109); await expectStage('m4_vault', 'access');
  await tp(0, 0.1, 111); await sleep(400); await E(() => window.__eoa.interact()); await zoneIs('core'); await shot('m5_core');
  // ---- M5
  await expectStage('m5_core', 'listen');
  await tp(0, 0.1, 22); await sleep(400); await interact('i_core_terminal'); await flush(60);
  await expectStage('m5_core', 'waves');
  await kill('e_core_waves');
  await expectStage('m5_core', 'boss', 90000);
  await flush(30); await invuln(); await sleep(4000); await shot('m5_boss');
  log('boss state', JSON.stringify((await state()).enemies));
  await kill('e_core_guardian');
  await expectStage('m5_core', 'release', 60000);
  await tp(0, 1.3, 4.5); await sleep(600); await interact('i_core_heart');
  await sleep(6000); await shot('m5_ending'); 
  await waitFor('credits', () => !!document.querySelector('.credits'), null, 240000);
  await sleep(1500); await shot('credits');
  await page.keyboard.press('Space');
  await waitFor('menu', () => window.__eoa.game.mode === 'menu', null, 30000);
  log('main story complete in', ((Date.now() - t0) / 1000).toFixed(0), 's');
  log('flags', Object.keys((await state()).flags).join(','));
  log('PASS');
} catch (e) {
  log('FAIL', e.message);
  await shot('fail');
  console.log(JSON.stringify(await state().catch(() => null)));
  console.log((await E(() => window.__eoa?.events.slice(-12))).join('\n'));
} finally {
  console.log('errors:', JSON.stringify(errors.slice(0, 20)));
  console.log('log errors:', JSON.stringify(await E(() => window.__eoa?.errors()).catch(() => null)));
  await browser.close();
}
