import { HAIR_STYLES, type HairStyle } from '../actors/human/HumanBuilder';
import { ACCENT_COLORS, appearanceFrom, ARMOR_COLORS, baseLook, EYE_COLORS, GLOW_COLORS, HAIR_COLORS, OUTFIT_COLORS, PRESETS, randomAppearance, SKIN_TONES, type Appearance, type HeroId } from '../actors/human/Appearance';
import { h, type UI } from './UI';

// Character Designer: edit Kael and Lyra with a live 3D preview. Changes persist immediately.

type Section = 'presets' | 'body' | 'face' | 'hair' | 'outfit';
const HAIR_LABELS: Record<HairStyle, string> = { short: 'Short', swept: 'Swept', undercut: 'Undercut', buzz: 'Buzz', curly: 'Curly', bob: 'Bob', tied: 'Braided tail', bun: 'Bun', long: 'Long', none: 'Shaved', hood: 'Hood' };

export function openDesigner(ui: UI, start: HeroId, onClose?: () => void) {
  const g = ui.game;
  const menu = g.menu!;
  const inGame = g.mode === 'play';
  let hero: HeroId = start;
  let section: Section = 'presets';
  let a: Appearance = g.appearanceFor(hero);
  let rebuildTimer = 0;
  const prevScene = g.rs.scene;
  g.designerActive = true;
  menu.select(hero);
  menu.enter('designer');
  menu.focus = 'body';
  if (inGame) {
    g.rs.setScene(menu.scene);
    g.rs.setGrade(menu.grade);
  }

  // Hide the screen underneath (character select / pause) while designing.
  const under = ui.top();
  if (under) under.el.style.visibility = 'hidden';
  const panel = h('div', { class: 'info designer' });
  const drag = h('div', { class: 'drag' });
  const el = h('div', { class: 'screen char-select' }, drag, panel);
  let dragging = false, lastX = 0;
  drag.addEventListener('pointerdown', (e) => { dragging = true; lastX = e.clientX; drag.setPointerCapture(e.pointerId); });
  drag.addEventListener('pointermove', (e) => { if (dragging) { menu.rotate((e.clientX - lastX) * 0.05); lastX = e.clientX; } });
  drag.addEventListener('pointerup', () => (dragging = false));

  const commit = (immediateRender = true) => {
    void g.setAppearance(hero, a);
    window.clearTimeout(rebuildTimer);
    rebuildTimer = window.setTimeout(() => menu.setLook(hero, g.lookFor(hero)), 120);
    if (immediateRender) render();
  };

  const swatches = (label: string, palette: string[], value: string, set: (v: string) => void) => {
    const row = h('div', { class: 'dz-row' }, h('div', { class: 'dz-lab' }, label));
    const sw = h('div', { class: 'swatches', 'data-nav': 'seg' });
    for (const c of palette) {
      const b = h('button', { class: 'sw' + (c.toLowerCase() === value.toLowerCase() ? ' sel' : ''), style: { background: c }, title: c });
      b.addEventListener('click', (e) => { e.stopPropagation(); set(c); commit(); });
      sw.appendChild(b);
    }
    const picker = h('input', { type: 'color', value, class: 'sw-pick', title: 'Custom colour' }) as HTMLInputElement;
    picker.addEventListener('input', () => { set(picker.value); commit(false); });
    picker.addEventListener('change', () => render());
    sw.appendChild(picker);
    sw.addEventListener('nav', (e) => {
      const i = palette.findIndex((c) => c.toLowerCase() === value.toLowerCase());
      set(palette[(i + (e as CustomEvent).detail + palette.length) % palette.length]);
      commit();
    });
    row.appendChild(sw);
    return row;
  };
  const slider = (label: string, value: number, min: number, max: number, step: number, set: (v: number) => void, fmt = (v: number) => v.toFixed(2)) => {
    const input = h('input', { type: 'range', min, max, step, value }) as HTMLInputElement;
    const val = h('span', { class: 'val' }, fmt(value));
    const wrap = h('div', { class: 'slider', 'data-nav': 'slider' }, input, val);
    const apply = (v: number) => {
      v = Math.max(min, Math.min(max, v));
      input.value = String(v);
      val.textContent = fmt(v);
      set(v);
      commit(false);
    };
    input.addEventListener('input', () => apply(parseFloat(input.value)));
    wrap.addEventListener('nav', (e) => apply(parseFloat(input.value) + (e as CustomEvent).detail * step));
    return h('div', { class: 'dz-row' }, h('div', { class: 'dz-lab' }, label), wrap);
  };
  const toggle = (label: string, value: boolean, set: (v: boolean) => void) => {
    const b = h('button', { class: 'toggle' + (value ? ' on' : ''), 'data-nav': 'btn' });
    b.addEventListener('click', () => { set(!value); commit(); });
    return h('div', { class: 'dz-row inline' }, h('div', { class: 'dz-lab' }, label), b);
  };

  const render = () => {
    panel.innerHTML = '';
    const heroTabs = h('div', { class: 'cs-tabs' });
    for (const c of ['kael', 'lyra'] as HeroId[]) {
      const t = h('button', { class: `cs-tab ${c}${c === hero ? ' sel' : ''}`, 'data-nav': 'grid' }, h('div', { class: 'n' }, c === 'kael' ? 'Kael Voss' : 'Lyra Vale'), h('div', { class: 'r' }, 'Edit appearance'));
      t.addEventListener('click', () => {
        hero = c;
        a = g.appearanceFor(hero);
        menu.select(c);
        render();
      });
      heroTabs.appendChild(t);
    }
    const secTabs = h('div', { class: 'tabs dz-tabs' });
    for (const s of ['presets', 'body', 'face', 'hair', 'outfit'] as Section[]) {
      const b = h('button', { class: 'tab' + (s === section ? ' sel' : ''), 'data-nav': 'grid' }, s);
      b.addEventListener('click', () => {
        section = s;
        menu.focus = s === 'face' || s === 'hair' ? 'face' : 'body';
        render();
      });
      secTabs.appendChild(b);
    }
    const body = h('div', { class: 'dz-body' });
    const fem = baseLook(hero).body.build === 'female';
    switch (section) {
      case 'presets':
        for (const p of PRESETS[hero]) {
          const b = h('button', { class: 'btn', 'data-nav': 'btn' }, p.name);
          b.addEventListener('click', () => {
            a = { ...appearanceFrom(baseLook(hero)), ...p.a };
            commit();
          });
          body.appendChild(b);
        }
        body.appendChild(h('div', { class: 'cs-hint', style: { marginTop: '1em' } }, 'Pick a starting point, then fine-tune Body, Face, Hair and Outfit. Changes are saved automatically and apply to new games and your current game.'));
        break;
      case 'body':
        body.append(
          slider('Height', a.height, fem ? 1.55 : 1.65, fem ? 1.85 : 1.98, 0.01, (v) => (a.height = v), (v) => v.toFixed(2) + ' m'),
          slider('Shoulders', a.shoulders, 0.88, 1.15, 0.01, (v) => (a.shoulders = v)),
          slider('Hips', a.hips, 0.88, 1.15, 0.01, (v) => (a.hips = v)),
          slider('Build', a.build, 0.88, 1.15, 0.01, (v) => (a.build = v)),
          swatches('Skin tone', SKIN_TONES, a.skin, (v) => (a.skin = v)),
        );
        break;
      case 'face':
        body.append(
          swatches('Eye colour', EYE_COLORS, a.eyes, (v) => (a.eyes = v)),
          slider('Jaw width', a.jaw, 0.8, 1.2, 0.01, (v) => (a.jaw = v)),
          slider('Chin', a.chin, 0.6, 1.4, 0.01, (v) => (a.chin = v)),
          slider('Nose', a.nose, 0.6, 1.4, 0.01, (v) => (a.nose = v)),
          slider('Brow ridge', a.brow, 0.3, 1.5, 0.01, (v) => (a.brow = v)),
          slider('Cheekbones', a.cheek, 0.6, 1.5, 0.01, (v) => (a.cheek = v)),
          slider('Lips', a.lips, 0.6, 1.5, 0.01, (v) => (a.lips = v)),
          slider('Freckles', a.freckles, 0, 1, 0.01, (v) => (a.freckles = v)),
          slider('Age lines', a.age, 0, 1, 0.01, (v) => (a.age = v)),
          slider('Stubble', a.stubble, 0, 1, 0.01, (v) => (a.stubble = v)),
          slider('Beard', a.beard, 0, 1, 0.01, (v) => (a.beard = v)),
          toggle('Facial scar', a.scar, (v) => (a.scar = v)),
        );
        break;
      case 'hair': {
        const grid = h('div', { class: 'hairgrid' });
        for (const st of HAIR_STYLES) {
          const b = h('button', { class: 'btn-small' + (st === a.hairStyle ? ' primary' : ''), 'data-nav': 'grid' }, HAIR_LABELS[st]);
          b.addEventListener('click', () => {
            a.hairStyle = st;
            commit();
          });
          grid.appendChild(b);
        }
        body.append(h('div', { class: 'dz-lab' }, 'Style'), grid, swatches('Hair colour', HAIR_COLORS, a.hairColor, (v) => (a.hairColor = v)));
        break;
      }
      case 'outfit':
        body.append(
          swatches('Jacket / suit', OUTFIT_COLORS, a.outfit, (v) => (a.outfit = v)),
          swatches('Accent panels', ACCENT_COLORS, a.accent, (v) => (a.accent = v)),
          swatches('Trousers', OUTFIT_COLORS, a.pants, (v) => (a.pants = v)),
          swatches('Boots', ['#2e2722', '#26252a', '#3a2e24', '#1a1a1c', '#4a3a2a', '#3a3a3e'], a.boots, (v) => (a.boots = v)),
          swatches('Armour', ARMOR_COLORS, a.armor, (v) => (a.armor = v)),
          swatches('Aether glow', GLOW_COLORS, a.glow, (v) => (a.glow = v)),
          swatches('Glow secondary', GLOW_COLORS, a.glow2, (v) => (a.glow2 = v)),
          toggle('Shoulder armour', a.shoulderPads, (v) => (a.shoulderPads = v)),
          toggle('Chest plate', a.chestPlate, (v) => (a.chestPlate = v)),
          toggle('Knee pads', a.kneePads, (v) => (a.kneePads = v)),
          toggle('Gloves', a.gloves, (v) => (a.gloves = v)),
          toggle('Back pack', a.backpack, (v) => (a.backpack = v)),
        );
        break;
    }
    const focus = h('button', { class: 'btn-small', 'data-nav': 'btn' }, menu.focus === 'face' ? 'View: Face' : 'View: Body');
    focus.addEventListener('click', () => {
      menu.focus = menu.focus === 'face' ? 'body' : 'face';
      render();
    });
    const rand = h('button', { class: 'btn-small', 'data-nav': 'btn' }, 'Randomize');
    rand.addEventListener('click', () => {
      a = randomAppearance(hero);
      commit();
    });
    const reset = h('button', { class: 'btn-small', 'data-nav': 'btn' }, 'Reset');
    reset.addEventListener('click', async () => {
      if (!(await ui.confirm('Reset appearance', `Restore ${hero === 'kael' ? 'Kael' : 'Lyra'}'s original design?`, 'Reset'))) return;
      a = appearanceFrom(baseLook(hero));
      commit();
    });
    const done = h('button', { class: 'btn-small primary', 'data-nav': 'btn', 'data-autofocus': true }, 'Done');
    done.addEventListener('click', () => close());
    panel.append(h('div', { class: 'kicker' }, 'Character Designer'), heroTabs, secTabs, body, h('div', { class: 'cs-hint' }, 'Drag the character to rotate.'), h('div', { class: 'cs-actions' }, focus, rand, reset, done));
    ui.refocus();
  };

  const close = async () => {
    window.clearTimeout(rebuildTimer);
    menu.setLook(hero, g.lookFor(hero));
    ui.pop('designer');
    if (under) under.el.style.visibility = '';
    g.designerActive = false;
    await g.refreshAppearanceVisuals();
    if (inGame && g.world.zone) {
      g.rs.setScene(g.world.zone.scene);
      g.rs.setGrade(g.world.zone.grade);
    } else if (!inGame) {
      g.rs.setScene(prevScene);
    }
    menu.enter(inGame ? 'menu' : 'charselect');
    onClose?.();
  };

  ui.push({ id: 'designer', el, back: () => void close(), overlay: inGame });
  render();
}
