// Screenshot helper: node tools/capture/shot.mjs "<url query>" out.png [width height waitMs]
import { chromium } from '@playwright/test';
const [,, query, out, w = '1280', h = '720', wait = '1500'] = process.argv;
const base = process.env.EOA_URL ?? 'http://localhost:5173/';
const browser = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--mute-audio'] });
const page = await browser.newPage({ viewport: { width: +w, height: +h } });
const logs = [];
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') logs.push(`[${m.type()}] ${m.text()}`); });
page.on('pageerror', (e) => logs.push('[pageerror] ' + e.message));
await page.goto(base + query, { waitUntil: 'load' });
try { await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 }); } catch { logs.push('timeout waiting for __ready'); }
await page.waitForTimeout(+wait);
await page.screenshot({ path: out });
const stats = await page.evaluate(() => window.__stats ?? null);
if (stats) console.log('stats', JSON.stringify(stats));
for (const l of logs.slice(0, 20)) console.log(l);
await browser.close();
