const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export default async (page, shot, log, base) => {
  await page.goto(base + '?autostart=kael&skipintro=1&slot=3', { waitUntil: 'load' });
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 180000 });
  await page.waitForFunction(() => window.__eoa?.state().mode === 'play', null, { timeout: 120000 });
  await page.evaluate(() => { const e = window.__eoa; e.setFlag('swap_unlocked'); e.setFlag('metro_open'); });
  const t0 = Date.now();
  await page.evaluate(() => window.__eoa.loadZone('metro', 'from_plaza'));
  await page.waitForFunction(() => window.__eoa.state().mode === 'play' && window.__eoa.state().zone === 'metro', null, { timeout: 120000 });
  log('metro load ms', Date.now() - t0, JSON.stringify((await page.evaluate(() => window.__eoa.state())).stats));
  await sleep(1500);
  await shot('metro_entry');
  await page.evaluate(() => { window.__eoa.teleport(0, 4.1, 16); window.__eoa.face(0); });
  await sleep(1200); await shot('metro_concourse');
  await page.evaluate(() => { window.__eoa.teleport(-20, 0.1, 47); window.__eoa.face(Math.PI / 2); });
  await sleep(1200); await shot('metro_platform');
  await page.evaluate(() => { window.__eoa.teleport(35, 0.1, 37.5); window.__eoa.face(Math.PI); });
  await sleep(1000); await shot('metro_power');
  log('cand', JSON.stringify((await page.evaluate(() => window.__eoa.state())).candidate));
  // Solve the puzzle: J1 needs 3 presses, J2 2, J3 1.
  for (const [id, n] of [['i_junction_1', 3], ['i_junction_2', 2], ['i_junction_3', 1]]) for (let i = 0; i < n; i++) { await page.evaluate((x) => window.__eoa.interactWith(x), id); await sleep(150); }
  await sleep(1500);
  log('flags', JSON.stringify(Object.keys((await page.evaluate(() => window.__eoa.state())).flags)));
  await shot('metro_power_on');
  await page.evaluate(() => { window.__eoa.teleport(-34, 0.1, 44); window.__eoa.face(Math.PI); });
  await sleep(1500); await shot('metro_signal');
  log('errors', JSON.stringify(await page.evaluate(() => window.__eoa.errors())));
};
