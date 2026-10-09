// Screenshot the loading screen mid-transition to check zone art is displayed.
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export default async (page, shot, log, base) => {
  await page.goto(base + '?autostart=kael&skipintro=1&slot=3', { waitUntil: 'load' });
  await page.waitForFunction(() => window.__eoa?.state().mode === 'play', null, { timeout: 120000 });
  await page.evaluate(() => { window.__eoa.setFlag('met_lyra'); void window.__eoa.loadZone('vault', 'from_facility'); });
  await sleep(150); await shot('loadscreen_vault'); await page.waitForFunction(() => window.__eoa.state().mode === 'play', null, { timeout: 60000 }); await page.evaluate(() => window.__eoa.autosave()); await sleep(400); await shot('saveind');
  const img = await page.evaluate(() => [...document.querySelectorAll('.loading *')].map((e) => getComputedStyle(e).backgroundImage).filter((b) => b && b !== 'none'));
  log('bg images', JSON.stringify(img));
};
