const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
export default async (page, shot, log, base) => {
  await page.goto(base + '?autostart=kael&skipintro=1&slot=3', { waitUntil: 'load' });
  await page.waitForFunction(() => window.__ready === true || window.__bootError, null, { timeout: 180000 });
  await page.waitForFunction(() => window.__eoa?.state().mode === 'play', null, { timeout: 120000 });
  const st = () => page.evaluate(() => { const s = window.__eoa.state(); const q = s.quests.m1_awakening; return { stage: q?.stage, status: q?.status, enemies: s.enemies, cand: s.candidate, dlg: s.dialogue, cine: s.cinematic, hp: s.hp, flags: Object.keys(s.flags) }; });
  const flush = async (n = 30) => { for (let i = 0; i < n; i++) { await page.evaluate(() => window.__eoa.advanceDialogue()); await sleep(120); } };
  await page.evaluate(() => window.__eoa.setFlag('tut_moved'));
  await flush(10);
  log('after move', JSON.stringify(await st()));
  await page.evaluate(() => { window.__eoa.teleport(0, 0.8, 8.5); window.__eoa.face(Math.PI); });
  await sleep(800);
  log('near monument', JSON.stringify(await st()));
  await shot('m1_monument');
  await page.evaluate(() => window.__eoa.interact());
  await sleep(500);
  await flush(25);
  await sleep(1500);
  log('after signal', JSON.stringify(await st()));
  await shot('m1_drones');
  // Fire bolts at the drones.
  for (let i = 0; i < 12; i++) { await page.evaluate(() => window.__eoa.press('bolt')); await sleep(350); }
  await shot('m1_fight');
  log('after bolts', JSON.stringify(await st()));
  await page.evaluate(() => window.__eoa.killEncounter('e_plaza_drones'));
  await sleep(3500);
  await flush(20);
  log('after kill', JSON.stringify(await st()));
  await shot('m1_after');
  // Collect the shard
  const pk = await page.evaluate(() => { const p = window.__eoa.game.world.pickups.find((x) => x.id === 'pickup_m1_shard'); return p ? p.pos.toArray() : null; });
  log('pickup at', JSON.stringify(pk));
  if (pk) { await page.evaluate((p) => window.__eoa.teleport(p[0], 0.2, p[2] + 0.5), pk); await sleep(1200); }
  await flush(10);
  log('after pickup', JSON.stringify(await st()), JSON.stringify(await page.evaluate(() => [...window.__eoa.game.powerups.active.keys()])));
  // Go to the camp
  await page.evaluate(() => window.__eoa.teleport(16, 0.3, -16));
  await sleep(1500);
  log('camp', JSON.stringify(await st()));
  await shot('m1_meeting');
  await sleep(4000);
  await shot('m1_meeting2');
  await page.evaluate(() => window.__eoa.skipCinematic());
  await sleep(2500);
  await flush(10);
  log('after meeting', JSON.stringify(await st()), JSON.stringify(Object.keys((await page.evaluate(() => window.__eoa.state())).quests)));
  await shot('m1_done');
  log('events', JSON.stringify(await page.evaluate(() => window.__eoa.events)));
  log('errors', JSON.stringify(await page.evaluate(() => window.__eoa.errors())));
};
