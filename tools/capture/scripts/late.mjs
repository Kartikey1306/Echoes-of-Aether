const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export default async (page, shot, log, base) => {
  await page.goto(base + '?autostart=kael&skipintro=1&slot=3', { waitUntil: 'load' });
  await page.waitForFunction(() => window.__eoa?.state().mode === 'play', null, { timeout: 120000 });
  await page.evaluate(() => { const e = window.__eoa; e.setFlag('swap_unlocked'); });
  await page.evaluate(() => window.__eoa.loadZone('core', 'from_vault'));
  await page.waitForFunction(() => window.__eoa.state().zone === 'core' && window.__eoa.state().mode === 'play', null, { timeout: 120000 });
  await sleep(1500); await shot('core_entry');
  log('core stats', JSON.stringify((await page.evaluate(() => window.__eoa.state())).stats), 'fps', (await page.evaluate(() => window.__eoa.state())).fps.toFixed(0));
  await page.evaluate(() => { window.__eoa.game.world.spawnEncounter('e_core_guardian'); const p = window.__eoa.game.player; p.invuln = 999; window.__eoa.teleport(0, 0.1, 12); window.__eoa.face(Math.PI); });
  await sleep(4000); await shot('core_boss');
  await page.evaluate(() => window.__eoa.loadZone('vault', 'from_core'));
  await page.waitForFunction(() => window.__eoa.state().zone === 'vault' && window.__eoa.state().mode === 'play', null, { timeout: 120000 });
  await page.evaluate(() => { window.__eoa.game.world.spawnEncounter('e_vault_guardian'); const p = window.__eoa.game.player; p.invuln = 999; window.__eoa.teleport(0, 0.1, 92); window.__eoa.face(Math.PI); });
  await sleep(3500); await shot('vault_gallery');
  log('errors', JSON.stringify(await page.evaluate(() => window.__eoa.errors())));
};
