// Capture every major screen for the visual audit and store-page screenshots.
// node tools/capture/run.mjs tools/capture/scripts/screens.mjs 1920 1080
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export default async (page, shot, log, base) => {
  const ev = (fn, a) => page.evaluate(fn, a);
  const play = () => page.waitForFunction(() => window.__eoa?.state().mode === 'play' && !window.__eoa.game.loading, null, { timeout: 120000 });

  await page.goto(base, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 120000 });
  await sleep(2500); await shot('s01_main_menu');
  await page.locator('.screen.main-menu button', { hasText: /new game/i }).first().click();
  await sleep(2200); await shot('s02_character_select_kael');
  await page.locator('.cs-tab.lyra').click();
  await sleep(1800); await shot('s03_character_select_lyra');
  await page.locator('.screen.char-select button', { hasText: /customi[sz]e/i }).first().click();
  await sleep(2200); await shot('s04_designer');
  await page.locator('.designer .tab, .dz-tabs button', { hasText: /hair/i }).first().click().catch(() => null);
  await sleep(1200); await shot('s05_designer_hair');

  await page.goto(base + '?autostart=kael&skipintro=1&slot=3', { waitUntil: 'load' });
  await play();
  await ev(() => { const e = window.__eoa; for (const f of ['met_lyra', 'swap_unlocked']) e.setFlag(f); e.give('pu_aether_shard', 2); e.give('pu_overcharge', 1); e.give('lore_rec_01', 1); });
  await sleep(4000); await shot('s06_gameplay_plaza');
  await ev(() => window.__eoa.game.ui.openPanel('inventory')); await sleep(800); await shot('s07_inventory');
  await ev(() => window.__eoa.game.ui.openPanel('map')); await sleep(800); await shot('s08_map');
  await ev(() => window.__eoa.game.ui.openPanel('journal')); await sleep(800); await shot('s09_journal');
  await ev(() => window.__eoa.game.ui.openPanel('skills')); await sleep(800); await shot('s10_skills');
  await page.keyboard.press('Escape'); await sleep(500);
  await ev(() => window.__eoa.press('pause')); await sleep(800); await shot('s11_pause');
  await page.locator('.screen.pause button', { hasText: /settings/i }).first().click(); await sleep(800); await shot('s12_settings_gameplay');
  for (const [tab, name] of [['graphics', 's13_settings_graphics'], ['controls', 's14_settings_controls'], ['accessibility', 's15_settings_accessibility']]) {
    await page.locator('.settings .tab, .screen button', { hasText: new RegExp('^' + tab + '$', 'i') }).first().click().catch(() => null);
    await sleep(600); await shot(name);
  }
  await page.keyboard.press('Escape'); await sleep(400); await page.keyboard.press('Escape'); await sleep(600);

  // Dialogue with an NPC
  await ev(() => { const g = window.__eoa.game; const n = g.world.npcs.find((x) => x.id === 'oren'); if (n) { window.__eoa.teleport(n.position.x + 1.6, n.position.y + 0.1, n.position.z + 1.6); void g.talkTo(n); } });
  await sleep(1800); await shot('s16_dialogue');
  for (let i = 0; i < 12; i++) { await ev(() => { window.__eoa.advanceDialogue(); window.__eoa.pickChoice(0); }); await sleep(250); }

  // Combat in the metro
  await ev(() => window.__eoa.loadZone('metro', 'from_plaza'));
  await play();
  await ev(() => { const e = window.__eoa, g = e.game; g.world.spawnEncounter('e_metro_concourse'); g.player.invuln = 999; });
  await sleep(2500);
  for (let i = 0; i < 6; i++) { await ev(() => window.__eoa.press('light')); await sleep(260); }
  await shot('s17_combat');
  await ev(() => window.__eoa.press('ability')); await sleep(350); await shot('s18_ability');

  // Boss
  await ev(() => window.__eoa.loadZone('core', 'from_vault'));
  await play();
  await ev(() => { const e = window.__eoa, g = e.game; g.world.spawnEncounter('e_core_guardian'); g.player.invuln = 999; e.teleport(2, 0.1, 10); e.face(Math.PI); });
  await sleep(5000); await shot('s19_boss');
  log('errors', JSON.stringify(await ev(() => window.__eoa.errors())));
};
