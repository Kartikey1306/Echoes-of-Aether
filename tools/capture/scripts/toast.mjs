const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export default async (page, shot, log, base) => {
  await page.goto(base + '?autostart=kael&skipintro=1&slot=3', { waitUntil: 'load' });
  await page.waitForFunction(() => window.__eoa?.state().mode === 'play', null, { timeout: 120000 });
  await page.evaluate(() => { const u = window.__eoa.game.ui; u.toast('+1 Aether Fragment', 'item'); u.toast('Mission: Into the Vault', 'quest'); u.toast('Picked up Vault Clearance', 'item'); u.toast('Log recovered: Log: Final Entry', 'lore'); });
  await sleep(600);
  const boxes = await page.evaluate(() => [...document.querySelectorAll('.toasts > *')].map((e) => { const r = e.getBoundingClientRect(); return `${e.className} ${Math.round(r.width)}x${Math.round(r.height)} "${e.textContent}"`; }));
  log(boxes.join('\n'));
  await page.screenshot({ path: 'tools/capture/out/toast_crop.png', clip: { x: 900, y: 200, width: 380, height: 300 } });
};
