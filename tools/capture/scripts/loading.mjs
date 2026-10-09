// In-engine loading-screen art: frames each zone from a fixed vantage with the HUD hidden and saves
// a JPEG to public/art/loading/<zone>.jpg. Run: node tools/capture/run.mjs tools/capture/scripts/loading.mjs 1920 1080
// EOA_SHOTS=plaza,core limits the zones; EOA_PREVIEW=1 writes to tools/capture/out instead.
import fs from 'node:fs';
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// cam / look in world space; hero: where to stand the active hero (null keeps them at the spawn).
export const SHOTS = {
  plaza: { entry: 'start', cam: [-2.2, 2.6, 22.5], look: [-8, 3.6, -6], fov: 50, hero: [-5.6, 0.16, 16.2], yaw: Math.PI * 0.95, partner: [-7.4, 0.16, 15.4] },
  metro: { entry: 'from_plaza', cam: [1.6, 5.6, -2.5], look: [-1, 2.5, 18], fov: 52, hero: [0.3, 4.05, 3.5], yaw: 0.05 },
  facility: { entry: 'from_plaza', cam: [8, 2.4, 27.5], look: [-3, 3.2, 10], fov: 54, hero: [3.4, 0.05, 22], yaw: Math.PI * 1.15, partner: [5.2, 0.05, 23.5] },
  vault: { entry: 'from_facility', cam: [1.4, 2.2, -3.2], look: [-0.5, 2.6, 20], fov: 50, hero: [0.2, 0.05, 3.2], yaw: 0 },
  rooftops: { entry: 'start', cam: [-5.5, 16.3, 2.2], look: [32, 17.5, 1.5], fov: 50, hero: [1.8, 14.05, 3.4], yaw: Math.PI * 0.5, partner: [0.6, 14.05, 0.2], exposure: 1.35, flags: ['relay_active'] },
  core: { entry: 'start', cam: [7.5, 2.2, 25], look: [0, 7, 0], fov: 52, hero: [2.6, 0.05, 19.5], yaw: Math.PI * 1.05, partner: [0.2, 0.05, 20.5] },
};

export default async (page, shot, log, base) => {
  const only = process.env.EOA_SHOTS?.split(',');
  const preview = process.env.EOA_PREVIEW === '1';
  const dir = preview ? 'tools/capture/out' : 'public/art/loading';
  fs.mkdirSync(dir, { recursive: true });
  await page.goto(base + '?autostart=kael&skipintro=1&slot=3', { waitUntil: 'load' });
  await page.waitForFunction(() => window.__eoa?.state().mode === 'play', null, { timeout: 120000 });
  await page.evaluate(() => {
    const e = window.__eoa;
    for (const f of ['met_lyra', 'swap_unlocked', 'metro_power', 'game_started']) e.setFlag(f);
    document.body.classList.add('capture-clean');
    const st = document.createElement('style');
    st.textContent = '.capture-clean .hud, .capture-clean .toasts, .capture-clean .hint, .capture-clean .prompt, .capture-clean .subtitle { display: none !important; }';
    document.head.appendChild(st);
  });
  for (const [zone, s] of Object.entries(SHOTS)) {
    if (only && !only.includes(zone)) continue;
    await page.evaluate(([z, en, flags]) => { for (const f of flags ?? []) window.__eoa.setFlag(f); window.__eoa.loadZone(z, en); }, [zone, s.entry, s.flags]);
    await page.waitForFunction((z) => window.__eoa.state().zone === z && window.__eoa.state().mode === 'play', zone, { timeout: 120000 });
    await page.evaluate((s) => {
      const e = window.__eoa, g = e.game;
      g.world.freezeEnemies = true;
      if (s.hero) { e.teleport(...s.hero); e.face(s.yaw); }
      const V = g.rs.camera.position.constructor;
      if (s.partner && g.companion?.body) g.companion.body.teleport(new V(...s.partner));
      g.cam.cinematic = { pos: new V(...s.cam), look: new V(...s.look), fov: s.fov };
      const u = g.rs.final.uniforms.exposure;
      window.__baseExposure ??= u.value;
      g.rs.setPost({ exposure: window.__baseExposure * (s.exposure ?? 1) });
    }, s);
    await sleep(3500);
    const data = await page.evaluate(() => window.__eoa.game.rs.snapshot(1920, 0.86));
    const file = `${dir}/${zone}.jpg`;
    fs.writeFileSync(file, Buffer.from(data.split(',')[1], 'base64'));
    log('wrote', file, 'fps', (await page.evaluate(() => window.__eoa.state().fps)).toFixed(0));
  }
  log('errors', JSON.stringify(await page.evaluate(() => window.__eoa.errors())));
};
