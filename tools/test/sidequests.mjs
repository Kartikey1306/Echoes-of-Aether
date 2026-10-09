// Side quests + collectibles test. Starts from a post-Mission-3 state.
import { chromium } from '@playwright/test';
const base = process.env.EOA_URL ?? 'http://localhost:5173/';
const browser = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--mute-audio'] });
const page = await browser.newPage({ viewport: { width: 1280, height: 720 } });
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const E = (fn, arg) => page.evaluate(fn, arg);
let n = 0;
const log = (...a) => console.log(`[${String(++n).padStart(2, '0')}]`, ...a);
const flush = async (k = 40) => { for (let i = 0; i < k; i++) { const s = await E(() => ({ d: window.__eoa.game.dialogue.active, c: window.__eoa.game.cinematics.active })); if (!s.d && !s.c) break; await E(() => { window.__eoa.advanceDialogue(); window.__eoa.pickChoice(0); if (window.__eoa.game.cinematics.active) window.__eoa.skipCinematic(); }); await sleep(150); } };
const status = (q) => E((q) => { const s = window.__eoa.game.gs.d.quests[q]; if (!s) return 'none'; if (s.status === 'done') return 'done'; return window.__eoa.data.quests[q].stages[s.stage].id; }, q);
const zone = async (z, entry) => { await E(([z, e]) => window.__eoa.loadZone(z, e), [z, entry]); await page.waitForFunction((z) => window.__eoa.state().zone === z && window.__eoa.state().mode === 'play', z, { timeout: 90000 }); await sleep(600); };
const tp = (x, y, z) => E(([x, y, z]) => window.__eoa.teleport(x, y, z), [x, y, z]);
const interact = (id) => E((id) => window.__eoa.interactWith(id), id);
const talk = async (npc) => { await E((npc) => { const n = window.__eoa.game.world.findNpc(npc); window.__eoa.teleport(n.position.x + 1.2, n.position.y + 0.1, n.position.z + 1.2); }, npc); await sleep(300); await interact('npc_' + npc); await sleep(300); await flush(40); await sleep(300); };
const collectAll = async () => {
  const list = await E(() => window.__eoa.game.world.pickups.filter((p) => !p.collected).map((p) => ({ id: p.id, pos: p.pos.toArray(), auto: p.auto, hidden: p.hidden })));
  for (const p of list) {
    if (p.hidden) await E((id) => { const w = window.__eoa.game.world; const pk = w.pickups.find((x) => x.id === id); pk.hidden = false; pk.visual.group.visible = true; const ii = w.zone.findInteractable(id); if (ii) ii.hidden = false; window.__eoa.game.gs.reveal(id); }, p.id);
    await tp(p.pos[0], p.pos[1] - 0.6, p.pos[2]);
    await sleep(350);
    if (!p.auto) await interact(p.id);
    await sleep(250);
  }
  await flush(20);
  return list.length;
};
try {
  await page.goto(base + '?autostart=lyra&skipintro=1&slot=1', { waitUntil: 'load' });
  await page.waitForFunction(() => window.__eoa?.state().mode === 'play', null, { timeout: 120000 });
  await E(() => { const e = window.__eoa; for (const f of ['tut_moved', 'swap_unlocked', 'metro_open', 'spur_open', 'metro_power_on', 'facility_gate_open']) e.setFlag(f); e.game.gs.unlock('dash'); e.game.gs.unlock('step'); e.game.gs.unlock('echo'); });
  await zone('plaza', 'camp');
  // Offers
  await talk('oren'); log('broken guardian', await status('sq_broken_guardian'));
  await talk('mira'); log('last signal', await status('sq_last_signal'));
  await talk('tomas'); log('memory fragments', await status('sq_memory_fragments'));
  // Nia: visible only with Echo Sight
  await E(() => window.__eoa.game.world.echoReveal(window.__eoa.game.player.position.clone(), 40, 20));
  await talk('nia'); log('hidden vault', await status('sq_hidden_vault'));
  // Plaza / market collectibles and the power cell
  await tp(-15, 0.2, 88); await sleep(800);
  log('plaza pickups collected', await collectAll());
  // Rooftops
  await zone('rooftops', 'from_market');
  await interact('i_relay_tower'); await sleep(300); log('last signal', await status('sq_last_signal'));
  log('roof pickups collected', await collectAll());
  log('last signal', await status('sq_last_signal'));
  await tp(35.5, 19.2, 4); await sleep(300); await interact('i_relay_socket'); await sleep(300); await flush(20);
  log('last signal', await status('sq_last_signal'));
  await E(() => window.__eoa.game.world.echoReveal(window.__eoa.game.player.position.clone(), 40, 10));
  await tp(20, 15.6, 4.6); await sleep(4000); await interact('i_hidden_hatch'); await sleep(2500);
  log('last signal', await status('sq_last_signal'));
  log('room pickups', await collectAll());
  log('last signal', await status('sq_last_signal'));
  // Metro / facility recordings and the actuator
  await zone('metro', 'from_plaza'); log('metro pickups', await collectAll());
  await zone('facility', 'from_metro'); log('facility pickups', await collectAll());
  log('memory fragments', await status('sq_memory_fragments'), 'broken guardian', await status('sq_broken_guardian'));
  // Turn-ins in the plaza
  await zone('plaza', 'camp');
  await talk('mira'); log('last signal', await status('sq_last_signal'));
  await talk('tomas'); log('memory fragments', await status('sq_memory_fragments'));
  await tp(14.5, 0.3, -24); await sleep(400); await interact('i_bolt'); await sleep(500); await flush(30);
  log('broken guardian', await status('sq_broken_guardian'));
  // Hidden vault
  await zone('vault', 'from_facility');
  await E(() => window.__eoa.game.world.echoReveal(window.__eoa.game.player.position.clone(), 60, 10));
  await tp(-9, 0.1, 24); await sleep(4500); await interact('i_hidden_door'); await sleep(600);
  log('hidden vault', await status('sq_hidden_vault'));
  await tp(-15, 0.1, 25.5); await sleep(400); await interact('i_hidden_pedestal'); await sleep(1500); await flush(60);
  log('hidden vault', await status('sq_hidden_vault'));
  log('vault pickups', await collectAll());
  const inv = await E(() => window.__eoa.game.gs.d.inventory);
  const col = await E(() => window.__eoa.game.gs.d.collected.filter((c) => c.startsWith('c_')));
  log('upgrades', Object.keys(inv).filter((k) => k.startsWith('up_')).join(','));
  log('collectibles found (excluding the vault ledge and other zones visited)', col.length, col.join(','));
  log('points', await E(() => window.__eoa.game.progression.points()));
  // Spend points in the Ability Matrix
  const bought = await E(() => ['echo_range', 'echo_duration', 'step_distance', 'pulse_radius', 'dash_distance'].filter((id) => window.__eoa.game.progression.buy(id)));
  log('skills bought', bought.join(','));
} catch (e) {
  log('FAIL', e.message);
}
console.log('errors', JSON.stringify(errors), JSON.stringify(await E(() => window.__eoa?.errors())));
await browser.close();
