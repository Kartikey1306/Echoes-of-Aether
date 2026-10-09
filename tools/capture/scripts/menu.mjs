export default async (page, shot, log, base) => {
  const t0 = Date.now();
  await page.goto(base, { waitUntil: 'load' });
  await page.waitForFunction(() => window.__ready === true || window.__bootError, null, { timeout: 120000 });
  const err = await page.evaluate(() => window.__bootError ?? null);
  if (err) log('BOOT ERROR', err);
  log('boot ms', Date.now() - t0);
  await page.waitForTimeout(2500);
  await shot('menu');
  log(JSON.stringify(await page.evaluate(() => window.__eoa?.errors() ?? [])));
};
