import { bindingLabel, REBINDABLE, type Action } from '../core/Input';
import type { SettingsData } from '../game/Settings';
import { h, type UI } from './UI';
import { locales, setLocale, t } from './Locale';

// Settings: Gameplay, Graphics, Audio, Controls, Accessibility, Language. Every control applies immediately.

type Section = 'gameplay' | 'graphics' | 'audio' | 'controls' | 'accessibility' | 'language';
const SECTIONS: Section[] = ['gameplay', 'graphics', 'audio', 'controls', 'accessibility', 'language'];

const ACTION_LABELS: Record<string, string> = {
  moveF: 'Move forward', moveB: 'Move back', moveL: 'Move left', moveR: 'Move right', jump: 'Jump', dash: 'Sprint / Phase', light: 'Light attack',
  heavy: 'Heavy attack', bolt: 'Aether Bolt (hold to aim)', ability: 'Ability (Pulse / Echo Sight)', ultimate: 'Ultimate', interact: 'Interact', swap: 'Switch character',
  lockon: 'Lock on', inventory: 'Inventory', map: 'Map', journal: 'Journal', skills: 'Ability Matrix', quick1: 'Use Aether Shard', quick2: 'Use Phase Core',
  quick3: 'Use Overcharge', quick4: 'Use Shield Fragment', quick5: 'Use Echo Fragment',
};

export function openSettings(ui: UI, inGame: boolean) {
  const g = ui.game;
  const S = g.settings;
  let section: Section = 'gameplay';
  const tabs = h('div', { class: 'tabs' });
  const body = h('div', { class: 'body' });
  const close = () => {
    g.input.cancelCapture();
    ui.pop('settings');
  };
  const reset = h('button', { class: 'btn-small', 'data-nav': 'btn' }, t('settings.reset'));
  reset.addEventListener('click', async () => {
    if (await ui.confirm(t('settings.reset'), `Reset ${t('settings.' + section)} settings to defaults?`, t('settings.reset'))) {
      S.resetSection(section === 'language' ? 'language' : section);
      render();
    }
  });
  const el = h('div', { class: 'screen dim-bg' }, h('div', { class: 'center-wrap' }, h('div', { class: 'modal panel' },
    h('div', { class: 'head' }, h('div', { class: 'h2' }, t('settings.title')), reset, h('button', { class: 'btn-small', 'data-nav': 'btn', onclick: close }, t('settings.close'))),
    tabs,
    body,
    h('div', { class: 'foot' }, h('div', { class: 'hintline' }, 'Changes apply immediately and are saved automatically.')),
  )));

  const row = (label: string, desc: string | null, control: HTMLElement) => h('div', { class: 'row' }, h('div', { class: 'lab' }, label, desc ? h('div', { class: 'd' }, desc) : null), control);
  const seg = <T extends string>(value: T, opts: [T, string][], set: (v: T) => void) => {
    let cur = value;
    const el = h('div', { class: 'seg', 'data-nav': 'seg' });
    const draw = () => {
      el.innerHTML = '';
      for (const [v, l] of opts) {
        const b = h('button', { class: v === cur ? 'sel' : '' }, l);
        b.addEventListener('click', (e) => {
          e.stopPropagation();
          cur = v;
          set(v);
          draw();
        });
        el.appendChild(b);
      }
    };
    draw();
    el.addEventListener('nav', (e) => {
      const i = Math.max(0, opts.findIndex(([v]) => v === cur));
      cur = opts[(i + (e as CustomEvent).detail + opts.length) % opts.length][0];
      set(cur);
      draw();
      g.audio.play('ui_hover');
    });
    return el;
  };
  const slider = (value: number, min: number, max: number, step: number, fmt: (v: number) => string, set: (v: number) => void) => {
    const input = h('input', { type: 'range', min, max, step, value }) as HTMLInputElement;
    const val = h('span', { class: 'val' }, fmt(value));
    const wrap = h('div', { class: 'slider', 'data-nav': 'slider' }, input, val);
    const apply = (v: number) => {
      v = Math.max(min, Math.min(max, Math.round(v / step) * step));
      input.value = String(v);
      val.textContent = fmt(v);
      set(v);
    };
    input.addEventListener('input', () => apply(parseFloat(input.value)));
    wrap.addEventListener('nav', (e) => apply(parseFloat(input.value) + (e as CustomEvent).detail * step));
    return wrap;
  };
  const toggle = (value: boolean, set: (v: boolean) => void) => {
    const b = h('button', { class: 'toggle' + (value ? ' on' : ''), 'data-nav': 'btn' });
    b.addEventListener('click', () => {
      value = !value;
      b.classList.toggle('on', value);
      set(value);
    });
    return b;
  };
  const pct = (v: number) => Math.round(v * 100) + '%';
  const upd = <K extends keyof SettingsData>(sec: K, patch: Partial<SettingsData[K]>) => S.update(sec, patch as Record<string, unknown>);

  const render = () => {
    tabs.innerHTML = '';
    for (const s of SECTIONS) {
      const b = h('button', { class: 'tab' + (s === section ? ' sel' : ''), 'data-nav': 'grid' }, t('settings.' + s));
      b.addEventListener('click', () => {
        section = s;
        render();
      });
      tabs.appendChild(b);
    }
    body.innerHTML = '';
    const d = S.data;
    switch (section) {
      case 'gameplay':
        body.append(
          row('Difficulty', 'Story: gentler enemies and faster recovery. Hard: enemies hit harder and attack more often.', seg(d.gameplay.difficulty, [['story', 'Story'], ['normal', 'Normal'], ['hard', 'Hard']], (v) => upd('gameplay', { difficulty: v }))),
          row('Camera sensitivity', null, slider(d.gameplay.cameraSensitivity, 0.2, 3, 0.05, (v) => v.toFixed(2), (v) => upd('gameplay', { cameraSensitivity: v }))),
          row('Aim sensitivity', 'Used while holding Aether Bolt to aim.', slider(d.gameplay.aimSensitivity, 0.1, 2, 0.05, (v) => v.toFixed(2), (v) => upd('gameplay', { aimSensitivity: v }))),
          row('Invert Y axis', null, toggle(d.gameplay.invertY, (v) => upd('gameplay', { invertY: v }))),
          row('Camera shake', null, slider(d.gameplay.cameraShake, 0, 1.5, 0.05, pct, (v) => upd('gameplay', { cameraShake: v }))),
        );
        break;
      case 'graphics':
        body.append(
          row('Preset', 'Applies a group of settings below.', seg(d.graphics.preset, [['low', 'Low'], ['medium', 'Medium'], ['high', 'High'], ['ultra', 'Ultra'], ['custom', 'Custom']], (v) => {
            if (v !== 'custom') S.applyPreset(v);
            render();
          })),
          row('Resolution', 'Internal render resolution.', seg(d.graphics.resolution, [['performance', '720p'], ['balanced', '1080p'], ['quality', '1440p'], ['native', 'Native']], (v) => upd('graphics', { resolution: v, preset: 'custom' }))),
          row('Display mode', null, seg(d.graphics.fullscreen ? 'full' : 'win', [['win', 'Windowed'], ['full', 'Fullscreen']], (v) => upd('graphics', { fullscreen: v === 'full' }))),
          row('VSync / frame limit', 'VSync follows your display refresh. 30 FPS caps rendering to save power.', seg(d.graphics.frameLimit, [['vsync', 'VSync'], ['30', '30 FPS']], (v) => upd('graphics', { frameLimit: v }))),
          row('Shadows', null, seg(d.graphics.shadows, [['off', 'Off'], ['low', 'Low'], ['medium', 'Medium'], ['high', 'High']], (v) => upd('graphics', { shadows: v, preset: 'custom' }))),
          row('Effects', 'Bloom, particles, film grain and chromatic aberration.', seg(d.graphics.effects, [['low', 'Low'], ['medium', 'Medium'], ['high', 'High']], (v) => upd('graphics', { effects: v, preset: 'custom' }))),
          row('Textures', 'Procedural texture resolution. Applies on the next area load.', seg(d.graphics.textures, [['low', 'Low'], ['medium', 'Medium'], ['high', 'High']], (v) => upd('graphics', { textures: v, preset: 'custom' }))),
          row('View distance', null, seg(d.graphics.viewDistance, [['low', 'Low'], ['medium', 'Medium'], ['high', 'High']], (v) => upd('graphics', { viewDistance: v, preset: 'custom' }))),
          row('Anti-aliasing', null, seg(d.graphics.antialiasing, [['off', 'Off'], ['fxaa', 'FXAA'], ['msaa', 'MSAA 4x']], (v) => upd('graphics', { antialiasing: v, preset: 'custom' }))),
        );
        break;
      case 'audio':
        body.append(
          row('Master volume', null, slider(d.audio.master, 0, 1, 0.01, pct, (v) => upd('audio', { master: v }))),
          row('Music', null, slider(d.audio.music, 0, 1, 0.01, pct, (v) => upd('audio', { music: v }))),
          row('Sound effects', null, slider(d.audio.sfx, 0, 1, 0.01, pct, (v) => upd('audio', { sfx: v }))),
          row('Ambience', null, slider(d.audio.ambience, 0, 1, 0.01, pct, (v) => upd('audio', { ambience: v }))),
          row('Interface', null, slider(d.audio.ui, 0, 1, 0.01, pct, (v) => upd('audio', { ui: v }))),
        );
        break;
      case 'controls': {
        body.append(
          row('Controller look speed', null, slider(d.controls.padLookSpeed, 0.2, 3, 0.05, (v) => v.toFixed(2), (v) => upd('controls', { padLookSpeed: v }))),
          row('Controller vibration', null, toggle(d.controls.vibration, (v) => upd('controls', { vibration: v }))),
          h('div', { class: 'section-title' }, g.input.padConnected() ? 'Bindings · Keyboard & Mouse / Controller' : 'Bindings · Keyboard & Mouse (connect a controller to edit its bindings)'),
        );
        for (const a of REBINDABLE) body.appendChild(bindRow(a));
        break;
      }
      case 'accessibility':
        body.append(
          row('Subtitles', null, toggle(d.accessibility.subtitles, (v) => upd('accessibility', { subtitles: v }))),
          row('Subtitle size', null, seg(d.accessibility.subtitleSize, [['small', 'S'], ['medium', 'M'], ['large', 'L'], ['xl', 'XL']], (v) => upd('accessibility', { subtitleSize: v }))),
          row('Subtitle background', null, slider(d.accessibility.subtitleBackground, 0, 1, 0.05, pct, (v) => upd('accessibility', { subtitleBackground: v }))),
          row('Speaker names', null, toggle(d.accessibility.speakerNames, (v) => upd('accessibility', { speakerNames: v }))),
          row('Flash intensity', 'Lightning, explosions and screen flashes.', slider(d.accessibility.flashIntensity, 0, 1, 0.05, pct, (v) => upd('accessibility', { flashIntensity: v }))),
          row('Camera shake limit', 'Caps all camera shake regardless of the gameplay setting.', slider(d.accessibility.cameraShake, 0, 1, 0.05, pct, (v) => upd('accessibility', { cameraShake: v }))),
          row('UI scale', null, slider(d.accessibility.uiScale, 0.75, 1.5, 0.05, pct, (v) => upd('accessibility', { uiScale: v }))),
          row('Hold to skip cinematics', 'When off, a single press skips.', toggle(d.accessibility.holdToSkip, (v) => upd('accessibility', { holdToSkip: v }))),
        );
        break;
      case 'language':
        body.append(row('Language', 'Additional languages can be added as locale files.', seg(d.language.locale, locales().map((l) => [l, l === 'en' ? 'English' : l] as [string, string]), (v) => {
          upd('language', { locale: v });
          setLocale(v);
        })));
        break;
    }
    ui.refocus();
  };

  const bindRow = (a: Action) => {
    const b = g.settings.data.controls.bindings[a];
    const wrap = h('div', { class: 'bind' });
    const mk = (kind: 'kb' | 'pad', idx: number) => {
      const code = b[kind][idx];
      const btn = h('button', { 'data-nav': 'grid' }, code ? bindingLabel(code) : '—');
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        if (kind === 'pad' && !g.input.padConnected()) {
          ui.toast('Connect a controller to rebind it.', 'warn');
          return;
        }
        btn.classList.add('listen');
        btn.textContent = 'Press…';
        g.input.captureNext((newCode) => {
          btn.classList.remove('listen');
          if (newCode === 'Escape') {
            render();
            return;
          }
          const isPad = /^B\d+$/.test(newCode);
          if ((kind === 'pad') !== isPad) {
            ui.toast(kind === 'pad' ? 'Press a controller button.' : 'Press a key or mouse button.', 'warn');
            render();
            return;
          }
          const binds = structuredClone(g.settings.data.controls.bindings);
          // Swap with any conflicting rebindable action so nothing silently loses its input.
          for (const other of REBINDABLE) {
            if (other === a) continue;
            const list = binds[other][kind];
            const i = list.indexOf(newCode);
            if (i >= 0) {
              list[i] = binds[a][kind][idx] ?? '';
              binds[other][kind] = list.filter(Boolean);
              ui.toast(`${ACTION_LABELS[other]} now uses ${bindingLabel(binds[a][kind][idx] ?? '') || 'nothing'}`, 'info');
            }
          }
          binds[a][kind][idx] = newCode;
          g.settings.update('controls', { bindings: binds });
          g.ui.hud.refreshKeys();
          render();
        });
      });
      return btn;
    };
    wrap.append(mk('kb', 0), mk('kb', 1), mk('pad', 0));
    return row(ACTION_LABELS[a] ?? a, null, wrap);
  };

  ui.push({ id: 'settings', el, back: close, overlay: inGame && g.mode === 'play' });
  render();
}
