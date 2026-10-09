// Systems test: saves (write, reload, backup, corruption recovery), settings persistence and repair,
// death -> retry -> checkpoint respawn, pause/resume. Run with the dev server up:
//   node tools/test/systems.mjs
import { chromium } from '@playwright/test';
const base = process.env.EOA_URL ?? 'http://localhost:5173/';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const browser = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--mute-audio'] });
const ctx = await browser.newContext({ viewport: { width: 1280, height: 720 } });
const page = await ctx.newPage();
const errors = [];
page.on('pageerror', (e) => errors.push(e.message));
page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
let failures = 0;
const check = (name, ok, extra = '') => { console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${extra ? '  ' + extra : ''}`); if (!ok) failures++; };
const ev = (fn, arg) => page.evaluate(fn, arg);
const waitPlay = () => page.waitForFunction(() => window.__eoa?.state().mode === 'play' && !window.__eoa.game.loading, null, { timeout: 120000 });

// ---------------------------------------------------------------- 1. New game and manual saves
await page.goto(base + '?autostart=lyra&skipintro=1&slot=2', { waitUntil: 'load' });
await waitPlay();
await ev(() => { const e = window.__eoa; e.setFlag('test_marker'); e.give('pu_shield_fragment', 2); });
check('manual save #1', await ev(() => window.__eoa.save(2)));
await ev(() => window.__eoa.give('pu_shield_fragment', 1));
await sleep(300);
check('manual save #2', await ev(() => window.__eoa.save(2)));
const raw = await ev(() => ({ main: localStorage.getItem('eoa.slot2'), bak: localStorage.getItem('eoa.slot2.bak'), tmp: localStorage.getItem('eoa.slot2.tmp') }));
const main = JSON.parse(raw.main), bak = JSON.parse(raw.bak);
check('envelope has magic, version, checksum, thumbnail', main.magic && main.version >= 1 && /^[0-9a-f]{8}$/.test(main.checksum) && main.thumbnail.startsWith('data:image/jpeg'));
check('save holds character, flag and items', main.character === 'lyra' && main.state.flags.test_marker === true && main.state.inventory.pu_shield_fragment === 3, `items=${main.state.inventory.pu_shield_fragment}`);
check('backup holds the previous save', bak.state.inventory.pu_shield_fragment === 2);
check('no temp file left behind', raw.tmp === null);

// ---------------------------------------------------------------- 2. Reload and continue
await page.goto(base, { waitUntil: 'load' });
await page.waitForFunction(() => window.__eoa?.state().mode === 'menu', null, { timeout: 120000 });
const menuText = await ev(() => document.querySelector('.screen.main')?.textContent ?? document.body.textContent);
check('main menu offers Continue', /continue/i.test(menuText));
await ev(() => window.__eoa.game.continueGame());
await waitPlay();
const st = await ev(() => ({ c: window.__eoa.game.gs.d.character, f: window.__eoa.game.gs.d.flags.test_marker, n: window.__eoa.game.gs.d.inventory.pu_shield_fragment, slot: window.__eoa.game.saves.activeSlot }));
check('continue restores state from slot 2', st.c === 'lyra' && st.f === true && st.n === 3 && st.slot === 2, JSON.stringify(st));

// ---------------------------------------------------------------- 3. Corruption: checksum mismatch -> backup
await ev(() => { const s = JSON.parse(localStorage.getItem('eoa.slot2')); s.state.inventory.pu_shield_fragment = 99; localStorage.setItem('eoa.slot2', JSON.stringify(s)); });
let info = await ev(() => window.__eoa.game.saves.info(2));
check('tampered save detected (checksum)', info.status === 'recovered' && /checksum/i.test(info.error ?? ''), `${info.status} ${info.error}`);
let env = await ev(() => window.__eoa.game.saves.load(2));
check('load falls back to backup', env?.state.inventory.pu_shield_fragment === 2);

// Truncated file
await ev(() => localStorage.setItem('eoa.slot2', localStorage.getItem('eoa.slot2').slice(0, 500)));
info = await ev(() => window.__eoa.game.saves.info(2));
check('truncated save detected', info.status === 'recovered', `${info.status} ${info.error}`);
check('recover() restores main file from backup', await ev(() => window.__eoa.game.saves.recover(2)));
info = await ev(() => window.__eoa.game.saves.info(2));
check('slot healthy after recovery', info.status === 'ok');

// Schema-invalid state with a valid checksum (e.g. edited by hand and re-hashed)
await ev(async () => {
  const s = JSON.parse(localStorage.getItem('eoa.slot2'));
  s.state.zone = 'nowhere';
  const { crc32 } = await import('/src/game/SaveSystem.ts');
  s.checksum = crc32(JSON.stringify(s.state));
  localStorage.setItem('eoa.slot2', JSON.stringify(s));
});
info = await ev(() => window.__eoa.game.saves.info(2));
check('schema-invalid save rejected', info.status !== 'ok', `${info.status} ${info.error}`);

// Both main and backup broken
await ev(() => { localStorage.setItem('eoa.slot2', '{not json'); localStorage.setItem('eoa.slot2.bak', 'garbage'); });
info = await ev(() => window.__eoa.game.saves.info(2));
check('fully corrupt slot reported as corrupt', info.status === 'corrupt');
check('latest() ignores the corrupt slot without throwing', (await ev(async () => (await window.__eoa.game.saves.latest())?.slot ?? null)) !== 2);

// Saves screen renders corrupt slot without crashing
await page.goto(base, { waitUntil: 'load' });
await page.waitForFunction(() => window.__eoa?.state().mode === 'menu', null, { timeout: 120000 });
const loadBtn = page.locator('.screen button', { hasText: /load game/i }).first();
if (await loadBtn.count()) {
  await loadBtn.click();
  await sleep(600);
  const txt = await ev(() => [...document.querySelectorAll('.slot-card')].map((c) => c.textContent).join(' | '));
  check('load screen shows the corrupt slot', /corrupt|damaged/i.test(txt), txt.slice(0, 160).replace(/\s+/g, ' '));
  await page.screenshot({ path: 'tools/capture/out/test_saves_corrupt.png' });
  await page.keyboard.press('Escape');
} else check('main menu has Load Game', false);

// ---------------------------------------------------------------- 4. Settings persistence and repair
await ev(() => { const s = window.__eoa.game.settings; s.update('gameplay', { cameraSensitivity: 1.7 }); s.update('accessibility', { subtitleSize: 'large' }); s.update('audio', { voiceSynthesis: true }); });
await page.goto(base, { waitUntil: 'load' });
await page.waitForFunction(() => window.__eoa?.state().mode === 'menu', null, { timeout: 120000 });
const sd = await ev(() => window.__eoa.game.settings.data);
check('settings persist across reload', sd.gameplay.cameraSensitivity === 1.7 && sd.accessibility.subtitleSize === 'large', `sens=${sd.gameplay.cameraSensitivity} sub=${sd.accessibility.subtitleSize}`);
check('voice synthesis cannot be re-enabled', sd.audio.voiceSynthesis === false && (await ev(() => window.__eoa.game.voice.enabled)) === false);
await ev(() => localStorage.setItem('eoa.settings', '{"gameplay":{"cameraSensitivity":"fast","difficulty":"nightmare"},"graphics":{"shadows":42},"audio":{"master":7}}'));
await page.goto(base, { waitUntil: 'load' });
await page.waitForFunction(() => window.__eoa?.state().mode === 'menu', null, { timeout: 120000 });
const sr = await ev(() => window.__eoa.game.settings.data);
check('invalid settings repaired to safe values', typeof sr.gameplay.cameraSensitivity === 'number' && ['story', 'normal', 'hard'].includes(sr.gameplay.difficulty) && typeof sr.graphics.shadows === 'string' && sr.audio.master <= 1, JSON.stringify({ sens: sr.gameplay.cameraSensitivity, diff: sr.gameplay.difficulty, sh: sr.graphics.shadows, m: sr.audio.master }));
await ev(() => localStorage.setItem('eoa.settings', 'not json at all'));
await page.goto(base, { waitUntil: 'load' });
await page.waitForFunction(() => window.__eoa?.state().mode === 'menu', null, { timeout: 120000 });
check('unparseable settings fall back to defaults', (await ev(() => window.__eoa.game.settings.data.gameplay.cameraSensitivity)) > 0);

// ---------------------------------------------------------------- 5. Death, retry, checkpoint respawn
await page.goto(base + '?autostart=kael&skipintro=1&slot=3', { waitUntil: 'load' });
await waitPlay();
await ev(() => { window.__eoa.setFlag('met_lyra'); return window.__eoa.loadZone('metro', 'from_plaza'); });
await waitPlay();
await ev(() => window.__eoa.autosave());
await sleep(500);
const cp = await ev(() => window.__eoa.game.gs.d.checkpoint);
await ev(() => window.__eoa.teleport(0, 4.05, 14));
await ev(() => { window.__eoa.game.player.invuln = 0; window.__eoa.damagePlayer(100000); });
await page.waitForSelector('.screen.death', { timeout: 8000 }).catch(() => null);
const deathShown = await ev(() => !!document.querySelector('.screen.death'));
check('death screen appears', deathShown);
await page.screenshot({ path: 'tools/capture/out/test_death.png' });
const deaths0 = await ev(() => window.__eoa.game.gs.d.stats.deaths);
await page.locator('.screen.death button').first().click();
await waitPlay();
await sleep(800);
const after = await ev(() => ({ hp: window.__eoa.game.player.health, max: window.__eoa.game.player.stats.maxHealth, zone: window.__eoa.state().zone, deaths: window.__eoa.game.gs.d.stats.deaths, pos: window.__eoa.game.player.position.toArray() }));
check('retry respawns at the checkpoint with full health', after.hp === after.max && after.zone === 'metro' && after.deaths === deaths0 + 1, JSON.stringify({ ...after, cp }));

// ---------------------------------------------------------------- 6. Pause freezes the simulation
await ev(() => window.__eoa.press('pause'));
await sleep(500);
const paused = await ev(() => ({ open: !!document.querySelector('.screen.pause'), t: window.__eoa.game.gs.d.stats.playtime }));
await sleep(1200);
const paused2 = await ev(() => window.__eoa.game.gs.d.stats.playtime);
check('pause menu opens and playtime stops', paused.open && Math.abs(paused2 - paused.t) < 0.05, `open=${paused.open} dt=${(paused2 - paused.t).toFixed(2)}`);
await ev(() => window.__eoa.press('pause'));
await sleep(500);
check('pause menu closes', !(await ev(() => !!document.querySelector('.screen.pause'))));

const unexpected = errors.filter((e) => !/checksum|refusing|corrupt|parse|JSON|Unexpected token|not valid JSON|unknown zone|write failed/i.test(e));
check('no unexpected runtime errors', unexpected.length === 0, unexpected.slice(0, 5).join(' | '));
console.log(failures ? `\n${failures} check(s) FAILED` : '\nAll systems checks passed');
await browser.close();
process.exit(failures ? 1 : 0);
