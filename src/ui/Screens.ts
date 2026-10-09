import { Data, COLLECTIBLE_TOTALS } from '../game/Data';
import type { CharacterId } from '../game/GameState';
import { SLOT_COUNT, type SlotInfo } from '../game/SaveSystem';
import { h, type UI } from './UI';
import { icon } from './Icons';
import { t } from './Locale';
import { openDesigner } from './Designer';

// Menu screens.

const fmtTime = (s: number) => {
  const hh = Math.floor(s / 3600), mm = Math.floor((s % 3600) / 60), ss = Math.floor(s % 60);
  return hh > 0 ? `${hh}h ${mm}m` : `${mm}m ${ss.toString().padStart(2, '0')}s`;
};
const fmtDate = (iso: string) => {
  try {
    return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
};

// ---------------------------------------------------------------------------- Main menu
export function mainMenu(ui: UI) {
  const g = ui.game;
  const list = h('div', { class: 'menu-list' });
  const el = h(
    'div',
    { class: 'screen main-menu' },
    h(
      'div',
      { class: 'col' },
      h('div', { class: 'title-block' }, h('div', { class: 'kicker' }, t('menu.kicker')), h('div', { class: 'title' }, 'Echoes', h('span', {}, t('menu.subtitle')))),
      h('div', { class: 'title-rule' }),
      list,
      h('div', { class: 'menu-foot' }, `${t('menu.version')} · ${__DEV_TOOLS__ ? 'development' : 'release'}`, h('br'), 'Mouse / keyboard / controller supported'),
    ),
  );
  const btn = (label: string, fn: () => void, opts: { disabled?: boolean; sub?: string; auto?: boolean } = {}) => {
    const b = h('button', { class: 'btn', 'data-nav': 'btn', disabled: opts.disabled, ...(opts.auto ? { 'data-autofocus': true } : {}) }, label, opts.sub ? h('span', { class: 'sub' }, opts.sub) : null);
    b.addEventListener('click', () => {
      if (!b.hasAttribute('disabled')) fn();
    });
    list.appendChild(b);
    return b;
  };
  const cont = btn(t('menu.continue'), () => void g.continueGame(), { disabled: true, sub: '…' });
  btn(t('menu.newGame'), () => {
    ui.pop('main');
    g.showCharSelect();
  }, { auto: true });
  btn(t('menu.loadGame'), () => ui.openSaveScreen('load'));
  btn(t('menu.settings'), () => ui.openSettings(false));
  btn(t('menu.credits'), () => void credits(ui).then(() => undefined));
  btn(t('menu.exit'), async () => {
    const native = (window as unknown as { eoaNative?: { quit?: () => void } }).eoaNative;
    const ok = await ui.confirm(t('menu.exit'), native?.quit ? t('menu.exitConfirm') : t('menu.exitBrowser'), t('menu.exit'));
    if (!ok) return;
    if (native?.quit) native.quit();
    else exited(ui);
  });
  ui.push({ id: 'main', el });
  // Fill Continue from the newest valid save.
  void g.saves.latest().then((env) => {
    if (env) {
      cont.removeAttribute('disabled');
      cont.querySelector('.sub')!.textContent = `${env.mission} · ${fmtTime(env.playtime)}`;
      cont.setAttribute('data-autofocus', '');
    } else cont.querySelector('.sub')!.textContent = t('menu.noSave');
  });
}

function exited(ui: UI) {
  window.close();
  // Most browsers refuse window.close() for user-opened tabs; show a parked screen instead.
  const el = h('div', { class: 'screen', style: { background: '#000', display: 'grid', placeItems: 'center' } },
    h('div', { style: { textAlign: 'center' } }, h('div', { class: 'h2' }, 'Echoes of Aether'), h('p', { class: 'dim' }, t('menu.exitBrowser')),
      h('button', { class: 'btn-small', 'data-nav': 'btn', onclick: () => { ui.pop('exited'); } }, 'Back to menu')));
  ui.push({ id: 'exited', el, back: () => ui.pop('exited') });
}

// ---------------------------------------------------------------------------- Character select
const CS: Record<CharacterId, { abilities: [string, string, string][] }> = {
  kael: { abilities: [['ab_pulse', 'Aether Pulse', 'Area shockwave: damage, knockback and stagger.'], ['ab_dash', 'Phase Dash', 'Short-range phase through space with invulnerability.'], ['ab_corebreak', 'Core Break', 'Ultimate: leap and drive the Core into the ground.']] },
  lyra: { abilities: [['ab_echo', 'Echo Sight', 'Reveals hidden objects, collectibles, secret paths and lore.'], ['ab_step', 'Phase Step', 'Fast evasive step with long invulnerability.'], ['ab_resonance', 'Resonance Burst', 'Ultimate: a spinning burst that stuns everything nearby.']] },
};

export function charSelect(ui: UI) {
  const g = ui.game;
  const menu = g.menu!;
  let sel: CharacterId = menu.selected;
  let slot = 1;
  let slots: SlotInfo[] = [];
  const info = h('div', { class: 'info' });
  const drag = h('div', { class: 'drag' });
  const el = h('div', { class: 'screen char-select' }, drag, info);
  let dragging = false, lastX = 0;
  drag.addEventListener('pointerdown', (e) => { dragging = true; lastX = e.clientX; drag.setPointerCapture(e.pointerId); });
  drag.addEventListener('pointermove', (e) => { if (dragging) { menu.rotate((e.clientX - lastX) * 0.05); lastX = e.clientX; } });
  drag.addEventListener('pointerup', () => (dragging = false));
  const render = () => {
    const kael = sel === 'kael';
    info.innerHTML = '';
    const tabs = h('div', { class: 'cs-tabs' });
    for (const c of ['kael', 'lyra'] as CharacterId[]) {
      const tab = h('button', { class: `cs-tab ${c}${c === sel ? ' sel' : ''}`, 'data-nav': 'grid' }, h('div', { class: 'n' }, c === 'kael' ? 'Kael Voss' : 'Lyra Vale'), h('div', { class: 'r' }, t(`cs.${c}.role`)));
      tab.addEventListener('click', () => {
        sel = c;
        menu.select(c);
        render();
      });
      tabs.appendChild(tab);
    }
    const abilities = h('div', { class: 'cs-abilities' });
    for (const [ic, n, d] of CS[sel].abilities) abilities.appendChild(h('div', { class: 'cs-ab' }, h('span', { html: icon(ic, kael ? '#5fb8ff' : '#a68bff') }), h('div', {}, h('div', { class: 't' }, n), h('div', { class: 'd' }, d))));
    const slotSeg = h('div', { class: 'seg', 'data-nav': 'seg' });
    for (let s = 1; s <= SLOT_COUNT; s++) {
      const si = slots[s - 1];
      const label = si?.status === 'ok' ? `${t('saves.slot')} ${s} · ${si.envelope!.mission}` : `${t('saves.slot')} ${s} · ${t('saves.empty')}`;
      const b = h('button', { class: s === slot ? 'sel' : '' }, label);
      b.addEventListener('click', (e) => { e.stopPropagation(); slot = s; render(); });
      slotSeg.appendChild(b);
    }
    slotSeg.addEventListener('nav', (e) => { slot = ((slot - 1 + (e as CustomEvent).detail + SLOT_COUNT) % SLOT_COUNT) + 1; render(); });
    const begin = h('button', { class: 'btn-small primary', 'data-nav': 'btn', 'data-autofocus': true }, t('cs.begin'));
    begin.addEventListener('click', async () => {
      const si = slots[slot - 1];
      if (si && si.status !== 'empty') {
        const ok = await ui.confirm(t('saves.overwrite'), `${t('saves.slot')} ${slot}: ${si.envelope?.mission ?? t('saves.corrupt')}`, t('cs.begin'), true);
        if (!ok) return;
      }
      ui.pop('charselect');
      void g.newGame(sel, slot);
    });
    const back = h('button', { class: 'btn-small', 'data-nav': 'btn' }, t('cs.back'));
    back.addEventListener('click', () => goBack());
    const custom = h('button', { class: 'btn-small', 'data-nav': 'btn' }, t('cs.customize'));
    custom.addEventListener('click', () => openDesigner(ui, sel, () => render()));
    info.append(
      h('div', { class: 'kicker' }, t('cs.title')),
      tabs,
      h('div', { class: 'cs-name' }, kael ? 'Kael Voss' : 'Lyra Vale'),
      h('div', { class: 'cs-role' }, t(`cs.${sel}.role`)),
      h('div', { class: 'cs-desc' }, t(`cs.${sel}.desc`)),
      h('div', { class: 'cs-meta' }, h('span', {}, 'Playstyle: ', h('b', {}, t(`cs.${sel}.style`))), h('span', {}, 'Combo: ', h('b', {}, kael ? 'L · L · L · Heavy' : 'Q · Q · Heavy'))),
      abilities,
      h('div', { class: 'section-title', style: { margin: '0.4em 0 0' } }, t('cs.slot')),
      slotSeg,
      h('div', { class: 'cs-hint' }, t('cs.note')),
      h('div', { class: 'cs-hint' }, t('cs.rotate')),
      h('div', { class: 'cs-actions' }, back, custom, begin),
    );
    ui.refocus();
  };
  const goBack = () => {
    ui.pop('charselect');
    g.showMenu();
  };
  ui.push({ id: 'charselect', el, back: goBack });
  void g.saves.allInfo().then((s) => {
    slots = s;
    const firstEmpty = s.findIndex((x) => x.status === 'empty');
    slot = firstEmpty >= 0 ? firstEmpty + 1 : 1;
    render();
  });
  render();
  // Right stick / keys rotate the model.
  const spin = () => {
    if (!ui.has('charselect')) return;
    const ax = navigator.getGamepads?.()[0]?.axes[2] ?? 0;
    if (Math.abs(ax) > 0.2) menu.rotate(ax * 0.15);
    requestAnimationFrame(spin);
  };
  spin();
}

// ---------------------------------------------------------------------------- Pause
export function pause(ui: UI) {
  const g = ui.game;
  const side = h('div', { class: 'side' }, h('div', { class: 'kicker' }, g.world.zone?.meta.name ?? ''), h('div', { class: 'h2' }, t('pause.title')));
  const resume = () => ui.pop('pause');
  const btn = (label: string, fn: () => void, opts: { disabled?: boolean; sub?: string } = {}) => {
    const b = h('button', { class: 'btn', 'data-nav': 'btn', disabled: opts.disabled }, label, opts.sub ? h('span', { class: 'sub' }, opts.sub) : null);
    b.addEventListener('click', () => !b.hasAttribute('disabled') && fn());
    side.appendChild(b);
  };
  const canSave = g.canSaveNow();
  btn(t('pause.resume'), resume);
  btn(t('pause.save'), () => ui.openSaveScreen('save'), { disabled: !canSave.ok, sub: canSave.ok ? '' : canSave.reason });
  btn(t('pause.load'), () => ui.openSaveScreen('load'));
  btn(t('pause.inventory'), () => ui.openPanel('inventory'));
  btn(t('pause.map'), () => ui.openPanel('map'));
  btn(t('pause.journal'), () => ui.openPanel('journal'));
  btn(t('pause.skills'), () => ui.openPanel('skills'));
  btn(t('pause.appearance'), () => openDesigner(ui, g.gs.d.character));
  btn(t('pause.settings'), () => ui.openSettings(true));
  btn(t('pause.quitMenu'), async () => {
    if (await ui.confirm(t('pause.quitMenu'), t('pause.quitConfirm'), t('pause.quitMenu'), true)) {
      ui.hideAllScreens();
      g.world.unload();
      g.disposeHeroes();
      g.showMenu();
    }
  });
  const d = g.gs.d;
  const count = (k: string) => d.collected.filter((c) => Data.collectibles[c]?.kind === k).length;
  const q = g.quests.tracked();
  const summary = h(
    'div',
    { class: 'summary' },
    h('div', { class: 'kicker' }, q ? (q.type === 'main' ? t('hud.mission') : t('hud.side')) : ''),
    h('div', { class: 'h1' }, q?.title ?? 'Aether-9'),
    h('div', { class: 'dim', style: { lineHeight: '1.6' } }, q?.summary ?? ''),
    h(
      'div',
      { class: 'stat-grid' },
      h('div', { class: 'stat' }, h('div', { class: 'v' }, fmtTime(d.stats.playtime)), h('div', { class: 'l' }, t('pause.playtime'))),
      h('div', { class: 'stat' }, h('div', { class: 'v' }, String(d.stats.kills)), h('div', { class: 'l' }, t('pause.kills'))),
      h('div', { class: 'stat' }, h('div', { class: 'v' }, `${d.quests ? Object.values(d.quests).filter((x) => x.status === 'done').length : 0}`), h('div', { class: 'l' }, 'Quests done')),
      h('div', { class: 'stat' }, h('div', { class: 'v' }, `${count('fragment')}/${COLLECTIBLE_TOTALS.fragment}`), h('div', { class: 'l' }, 'Aether Fragments')),
      h('div', { class: 'stat' }, h('div', { class: 'v' }, `${count('recording')}/${COLLECTIBLE_TOTALS.recording}`), h('div', { class: 'l' }, 'Recordings')),
      h('div', { class: 'stat' }, h('div', { class: 'v' }, `${count('cache')}/${COLLECTIBLE_TOTALS.cache}`), h('div', { class: 'l' }, 'Hidden Caches')),
    ),
  );
  const el = h('div', { class: 'screen dim-bg pause' }, side, summary);
  ui.push({ id: 'pause', el, back: resume, overlay: true });
}

// ---------------------------------------------------------------------------- Save / Load
export function saves(ui: UI, mode: 'save' | 'load', fromTerminal: boolean) {
  const g = ui.game;
  const body = h('div', { class: 'body' });
  const close = () => ui.pop('saves');
  const el = h('div', { class: 'screen dim-bg' }, h('div', { class: 'center-wrap' }, h('div', { class: 'modal panel' },
    h('div', { class: 'head' }, h('div', { class: 'h2' }, mode === 'save' ? t('saves.saveTitle') : t('saves.loadTitle')), h('button', { class: 'btn-small', 'data-nav': 'btn', onclick: close }, t('panel.close'))),
    body,
    h('div', { class: 'foot' }, h('div', { class: 'hintline' }, `Backend: ${g.saves.backend.name} · atomic writes with backup`)),
  )));
  const render = async () => {
    const infos = await g.saves.allInfo();
    body.innerHTML = '';
    const list = h('div', { class: 'slots' });
    for (const i of infos) {
      const e = i.envelope;
      const thumb = h('div', { class: 'thumb', style: e?.thumbnail ? { backgroundImage: `url(${e.thumbnail})` } : {} }, e ? '' : i.status === 'empty' ? t('saves.empty') : '!');
      const acts = h('div', { class: 'acts' });
      const card = h('div', { class: 'slot-card' }, thumb, h('div', {},
        h('div', { class: 't' }, `${t('saves.slot')} ${i.slot}${e ? ' · ' + e.mission : ''}`),
        e
          ? h('div', { class: 'm' }, `${Data.zones[e.zone]?.name ?? e.zone} · ${e.character === 'kael' ? 'Kael' : 'Lyra'} · ${fmtTime(e.playtime)}`, h('br'), `${fmtDate(e.timestamp)} · ${e.kind}`)
          : i.status === 'empty'
            ? h('div', { class: 'm' }, t('saves.empty'))
            : h('div', {}, h('div', { class: 'st ' + (i.status === 'recovered' ? 'rec' : 'bad') }, i.status === 'recovered' ? t('saves.recovered') : t('saves.corrupt')), h('div', { class: 'm' }, i.error ?? '')),
      ), acts);
      const add = (label: string, cls: string, fn: () => void | Promise<void>) => {
        const b = h('button', { class: 'btn-small ' + cls, 'data-nav': 'btn' }, label);
        b.addEventListener('click', () => void fn());
        acts.appendChild(b);
      };
      if (mode === 'save') {
        add(t('saves.save'), 'primary', async () => {
          if (i.status !== 'empty' && i.slot !== g.saves.activeSlot) {
            if (!(await ui.confirm(t('saves.overwrite'), `${t('saves.slot')} ${i.slot}`, t('saves.save'), true))) return;
          }
          if (await g.manualSave(i.slot)) await render();
        });
      } else if (e) {
        add(t('saves.load'), 'primary', async () => {
          ui.hideAllScreens();
          await g.loadFromEnvelope(e);
        });
      }
      if (i.status !== 'ok' && i.backup) add(t('saves.recover'), '', async () => {
        await g.saves.recover(i.slot);
        await render();
      });
      if (mode === 'load' && !e && i.backup && i.status === 'recovered') {
        add(t('saves.load') + ' (backup)', '', async () => {
          ui.hideAllScreens();
          await g.loadFromEnvelope(i.backup!);
        });
      }
      if (i.status !== 'empty') add(t('saves.delete'), 'danger', async () => {
        if (await ui.confirm(t('saves.delete'), t('saves.deleteConfirm'), t('saves.delete'), true)) {
          await g.saves.delete(i.slot);
          await render();
        }
      });
      list.appendChild(card);
    }
    body.appendChild(list);
    ui.refocus();
  };
  ui.push({ id: 'saves', el, back: close, overlay: g.mode === 'play', onClose: () => void fromTerminal });
  void render();
}

// ---------------------------------------------------------------------------- Death
export function death(ui: UI) {
  const g = ui.game;
  const acts = h('div', { class: 'acts' });
  const add = (label: string, fn: () => void, auto = false) => {
    const b = h('button', { class: 'btn', 'data-nav': 'btn', ...(auto ? { 'data-autofocus': true } : {}) }, label);
    b.addEventListener('click', fn);
    acts.appendChild(b);
  };
  add(t('death.retry'), () => {
    ui.pop('death');
    void g.respawnAtCheckpoint();
  }, true);
  add(t('death.load'), async () => {
    const env = await g.saves.load(g.saves.activeSlot);
    ui.pop('death');
    if (env) await g.loadFromEnvelope(env);
    else void g.respawnAtCheckpoint();
  });
  add(t('death.quit'), () => {
    ui.hideAllScreens();
    g.world.unload();
    g.disposeHeroes();
    g.showMenu();
  });
  const el = h('div', { class: 'screen death' }, h('div', { class: 'box' }, h('div', { class: 't' }, t('death.title')), h('div', { class: 's' }, t('death.sub')), acts));
  ui.push({ id: 'death', el, overlay: true });
}

// ---------------------------------------------------------------------------- Credits
export function credits(ui: UI): Promise<void> {
  const roll = h('div', { class: 'roll' });
  const sec = (title: string, ...lines: string[]) => {
    roll.appendChild(h('h2', {}, title));
    for (const l of lines) roll.appendChild(h('p', { html: l }));
  };
  roll.appendChild(h('h1', {}, 'Echoes of Aether'));
  roll.appendChild(h('p', {}, 'A story of Aether-9'));
  sec('Created by', 'Directed and produced by <b>Kartikey</b>');
  sec('Starring', '<b>Kael Voss</b> · survey lead', '<b>Lyra Vale</b> · systems engineer', '<b>Dr. Ilse Maren</b> · Aether Research Division', '<b>Oren Hale</b>, <b>Mira Sato</b>, <b>Tomas Reyes</b>, <b>Nia</b>, <b>BOLT-7</b>');
  sec('Technology', 'Three.js (MIT) · Rapier physics (Apache-2.0) · Vite (MIT) · TypeScript (Apache-2.0)', 'Rajdhani &amp; Inter typefaces (SIL Open Font License 1.1)');
  sec('Visual development', 'All 3D models, animation, textures and effects generated procedurally in code', 'Loading-screen art captured in-engine');
  sec('Audio', 'All music, sound effects and ambience synthesized in real time with the Web Audio API', 'Dialogue presented with subtitles');
  sec('Special thanks', 'The DreamLayer Jam', 'Everyone who stayed on the air until the very end');
  roll.appendChild(h('p', { style: { marginTop: '6em', fontStyle: 'italic' } }, '"Now we wake the rest of the city."'));
  const el = h('div', { class: 'screen credits' }, roll, h('div', { class: 'skiphint' }, t('credits.skip')));
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      window.removeEventListener('keydown', onKey);
      el.removeEventListener('click', finish);
      ui.pop('credits');
      resolve();
    };
    const onKey = (e: KeyboardEvent) => {
      if (performance.now() - start > 800) {
        e.preventDefault();
        finish();
      }
    };
    const start = performance.now();
    ui.push({ id: 'credits', el, back: finish });
    window.addEventListener('keydown', onKey);
    el.addEventListener('click', finish);
    const dur = 48000;
    roll.animate([{ transform: 'translate(-50%, 0)' }, { transform: `translate(-50%, calc(-100% - 100vh))` }], { duration: dur, easing: 'linear', fill: 'forwards' });
    setTimeout(finish, dur);
    // Gamepad skip
    const poll = () => {
      if (done) return;
      const pad = navigator.getGamepads?.()[0];
      if (pad && pad.buttons.some((b) => b.pressed) && performance.now() - start > 800) return finish();
      requestAnimationFrame(poll);
    };
    poll();
  });
}

// ---------------------------------------------------------------------------- Confirm
export function confirm(ui: UI, title: string, message: string, okLabel: string, danger: boolean): Promise<boolean> {
  return new Promise((resolve) => {
    const id = 'confirm-' + Math.random().toString(36).slice(2, 6);
    const done = (v: boolean) => {
      ui.pop(id);
      resolve(v);
    };
    const el = h('div', { class: 'screen dim-bg' }, h('div', { class: 'center-wrap' }, h('div', { class: 'confirm panel' },
      h('div', { class: 't' }, title),
      h('div', { class: 'm' }, message),
      h('div', { class: 'acts' },
        h('button', { class: 'btn-small', 'data-nav': 'btn', 'data-autofocus': true, onclick: () => done(false) }, 'Cancel'),
        h('button', { class: 'btn-small ' + (danger ? 'danger' : 'primary'), 'data-nav': 'btn', onclick: () => done(true) }, okLabel)),
    )));
    ui.push({ id, el, back: () => done(false), overlay: ui.game.mode === 'play' });
  });
}
