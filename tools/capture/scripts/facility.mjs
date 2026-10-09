const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export default async (page, shot, log, base) => {
  await page.goto(base + '?autostart=lyra&skipintro=1&slot=3', { waitUntil: 'load' });
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 180000 });
  await page.waitForFunction(() => window.__eoa?.state().mode === 'play', null, { timeout: 120000 });
  await page.evaluate(() => { const e = window.__eoa; e.setFlag('swap_unlocked'); });
  const t0 = Date.now();
  await page.evaluate(() => window.__eoa.loadZone('facility', 'from_metro'));
  await page.waitForFunction(() => window.__eoa.state().mode === 'play' && window.__eoa.state().zone === 'facility', null, { timeout: 120000 });
  log('facility load ms', Date.now() - t0, JSON.stringify((await page.evaluate(() => window.__eoa.state())).stats));
  await sleep(1500); await shot('fac_station');
  const views = [['fac_atrium', 0, 0.1, 27, 0], ['fac_labs', -30, 0.1, 15, -Math.PI / 2], ['fac_lab_a', -37, 0.1, 19, Math.PI], ['fac_server', -16, 0.1, 6.5, -Math.PI / 2], ['fac_offices', 24, 0.1, 10, Math.PI], ['fac_hall', 0, 0.1, -3, Math.PI], ['fac_lobby', 0, 0.1, 44, Math.PI]];
  for (const [n, x, y, z, yaw] of views) { await page.evaluate(([x, y, z, yaw]) => { window.__eoa.teleport(x, y, z); window.__eoa.face(yaw); }, [x, y, z, yaw]); await sleep(1100); await shot(n); }
  // Echo reveal test: unlock echo, go near the hidden wall, use ability.
  await page.evaluate(() => { const e = window.__eoa; e.game.gs.unlock('echo'); e.teleport(-10, 0.1, -10); e.face(-Math.PI / 2); });
  await sleep(600);
  await page.evaluate(() => window.__eoa.press('ability'));
  await sleep(2500);
  await shot('fac_echo');
  log('revealed', JSON.stringify(await page.evaluate(() => window.__eoa.game.gs.d.revealed)));
  await page.evaluate(() => { window.__eoa.teleport(-18, 0.1, -10); window.__eoa.face(-Math.PI / 2); });
  await sleep(1200); await shot('fac_hidden_office');
  log('errors', JSON.stringify(await page.evaluate(() => window.__eoa.errors())));
};
