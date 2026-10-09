// Sample every procedural animation clip of the prototype (src/actors/human/Anims.ts) at 30 fps to JSON,
// for retargeting onto the Unity humanoid rig in Blender.
// Usage: node tools/anim/sample_clips.mjs   (needs the Vite dev server on :5173)
import { chromium } from '@playwright/test';
import fs from 'node:fs';
const base = process.env.EOA_URL ?? 'http://localhost:5173/';
const browser = await chromium.launch({ headless: true, args: ['--mute-audio'] });
const page = await browser.newPage();
await page.goto(base + '?view=chars&ids=kael', { waitUntil: 'load' });
await page.waitForFunction(() => window.__ready === true, null, { timeout: 60000 });
const data = await page.evaluate(async () => {
  const A = await import('/src/actors/human/Anims.ts');
  const M = await import('/src/actors/human/Animator.ts');
  const R = await import('/src/actors/human/HumanRig.ts');
  const out = { bones: R.BONE_NAMES, fps: 30, styles: {} };
  for (const style of ['male', 'female']) {
    const lib = A.getAnimLib(style);
    const clips = { ...lib.clips, idle: lib.loco.idle, walk: lib.loco.walk, run: lib.loco.run, sprint: lib.loco.sprint, jump: lib.loco.jump, fall: lib.loco.fall, combat_idle: lib.loco.combatIdle };
    const strides = { walk: lib.loco.strideWalk, run: lib.loco.strideRun, sprint: lib.loco.strideSprint };
    const res = {};
    for (const [name, clip] of Object.entries(clips)) {
      if (!clip) continue;
      // Gait FnClips have a normalised duration of 1; give them real cycle times from stride / speed.
      const speeds = { walk: 1.9, run: 5.0, sprint: 7.4 };
      const realDur = strides[name] ? strides[name] / speeds[name] : clip.duration;
      const n = Math.max(2, Math.round(realDur * 30) + (clip.loop ? 0 : 1));
      const buf = new M.PoseBuf();
      const frames = [];
      for (let i = 0; i < n; i++) {
        const t = clip.loop ? (i / n) * clip.duration : Math.min(clip.duration, (i / 30) * (clip.duration / realDur));
        buf.clear();
        clip.sample(t, buf);
        frames.push([...buf.e].map((x) => +x.toFixed(3)).concat([...buf.p].map((x) => +x.toFixed(4))));
      }
      res[name] = { duration: realDur, loop: !!clip.loop, events: (clip.events ?? []).map((e) => ({ t: e.t * (realDur / clip.duration), name: e.name })), frames, speed: speeds[name] ?? 0 };
    }
    out.styles[style] = res;
  }
  return out;
});
fs.mkdirSync('blender/anim', { recursive: true });
fs.writeFileSync('blender/anim/clips.json', JSON.stringify(data));
const s = data.styles.male;
console.log('clips', Object.keys(s).length, Object.entries(s).map(([k, v]) => `${k}:${v.frames.length}`).join(' '));
await browser.close();
