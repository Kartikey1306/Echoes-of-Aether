// Drive the game with Playwright: node tools/capture/run.mjs <script.mjs> [width height]
// The script default-exports async (page, shot, log) => {}.
import { chromium } from '@playwright/test';
import path from 'node:path';
const [,, script, w = '1280', h = '720'] = process.argv;
const base = process.env.EOA_URL ?? 'http://localhost:5173/';
const outDir = process.env.EOA_OUT ?? 'tools/capture/out';
const browser = await chromium.launch({ headless: true, args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist', '--mute-audio'] });
const page = await browser.newPage({ viewport: { width: +w, height: +h } });
const logs = [];
page.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') logs.push(`[${m.type()}] ${m.text()}`); });
page.on('pageerror', (e) => logs.push('[pageerror] ' + e.message + '\n' + (e.stack ?? '').split('\n').slice(0, 4).join('\n')));
const shot = async (name) => { const p = path.join(outDir, name + '.png'); await page.screenshot({ path: p }); console.log('shot', p); };
const log = (...a) => console.log(...a);
const mod = await import(path.resolve(script));
try {
  await mod.default(page, shot, log, base);
} catch (e) {
  console.log('SCRIPT ERROR', e.message);
  await shot('error');
}
for (const l of logs.slice(0, 40)) console.log(l);
await browser.close();
