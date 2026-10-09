// Rasterizes the prototype's SVG icon set (src/ui/Icons.ts) to 128 px white-on-transparent PNGs for
// Unity (Assets/Resources/UI/Icons/<name>.png). The UI tints them at runtime.
//
// Usage (from anywhere; Playwright resolves from the repository's node_modules):
//   node "unity/EchoesOfAether/Assets/Editor/UI/Tools~/rasterize_icons.mjs" [iconsTs] [outDir] [size]
// The folder ends in "~" so Unity ignores it.
import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const repo = resolve(here, '../../../../../..');
const iconsTs = resolve(process.argv[2] ?? `${repo}/src/ui/Icons.ts`);
const outDir = resolve(process.argv[3] ?? resolve(here, '../../../Resources/UI/Icons'));
const size = Number(process.argv[4] ?? 128);

// Node 22.18+ strips TypeScript types natively; Icons.ts has no imports.
const { icon, ICON_NAMES } = await import(iconsTs);
mkdirSync(outDir, { recursive: true });

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: size, height: size }, deviceScaleFactor: 1 });
const render = async (name, svg) => {
  const sized = svg.replace('class="icon"', `class="icon" width="${size}" height="${size}"`);
  await page.setContent(`<!doctype html><html><body style="margin:0;background:transparent">${sized}</body></html>`);
  const el = await page.$('svg');
  await el.screenshot({ path: `${outDir}/${name}.png`, omitBackground: true });
};
for (const name of ICON_NAMES) await render(name, icon(name, '#ffffff'));
// Fallback glyph used for unknown icon ids (same as icon() with an unknown name).
await render('unknown', icon('__unknown__', '#ffffff'));
await browser.close();
console.log(`rasterized ${ICON_NAMES.length + 1} icons at ${size}px into ${outDir}`);
