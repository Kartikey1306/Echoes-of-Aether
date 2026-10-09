import { Data, COLLECTIBLE_TOTALS, type ItemCategory } from '../game/Data';
import { h, type UI } from './UI';
import { icon } from './Icons';
import { t } from './Locale';
import { drawZoneMap } from './MapDraw';

// In-game panels: Inventory, Map, Journal, Ability Matrix. Tabs switch between them.

type PanelName = 'inventory' | 'map' | 'journal' | 'skills';
const PANELS: PanelName[] = ['inventory', 'map', 'journal', 'skills'];
const RARITY_COLOR: Record<string, string> = { common: '#c8d2dc', uncommon: '#5fd4f0', rare: '#a68bff', epic: '#ffb45e' };

export function open(ui: UI, start: PanelName) {
  const g = ui.game;
  if (ui.has('panel')) ui.pop('panel');
  let current = start;
  const tabs = h('div', { class: 'tabs' });
  const body = h('div', { class: 'body' });
  const title = h('div', { class: 'h2' });
  const close = () => ui.pop('panel');
  const el = h('div', { class: 'screen dim-bg' }, h('div', { class: 'center-wrap' }, h('div', { class: 'modal panel' },
    h('div', { class: 'head' }, title, h('button', { class: 'btn-small', 'data-nav': 'btn', onclick: close }, t('panel.close'))),
    tabs,
    body,
    h('div', { class: 'foot' }, h('div', { class: 'hintline' }, h('span', {}, h('span', { class: 'keycap' }, 'Esc'), ' close'), h('span', {}, h('span', { class: 'keycap' }, '←'), h('span', { class: 'keycap' }, '→'), ' navigate'))),
  )));
  const render = () => {
    title.textContent = t('panel.' + current);
    tabs.innerHTML = '';
    for (const p of PANELS) {
      const b = h('button', { class: 'tab' + (p === current ? ' sel' : ''), 'data-nav': 'grid' }, t('panel.' + p));
      b.addEventListener('click', () => {
        current = p;
        render();
      });
      tabs.appendChild(b);
    }
    body.innerHTML = '';
    if (current === 'inventory') inventory(ui, body, render);
    else if (current === 'map') map(ui, body);
    else if (current === 'journal') journal(ui, body, render);
    else skills(ui, body, render);
    ui.refocus();
  };
  ui.push({ id: 'panel', el, back: close, overlay: true });
  render();
}

// ---------------------------------------------------------------------------- Inventory
let invCat: ItemCategory = 'aether';
let invSel: string | null = null;

function inventory(ui: UI, body: HTMLElement, rerender: () => void) {
  const g = ui.game;
  const cats: [ItemCategory, string][] = [['aether', t('inv.aether')], ['powerups', t('inv.powerups')], ['quest', t('inv.quest')], ['upgrades', t('inv.upgrades')], ['lore', t('inv.lore')]];
  const seg = h('div', { class: 'seg', 'data-nav': 'seg', style: { justifyContent: 'flex-start', marginBottom: '1em' } });
  for (const [c, l] of cats) {
    const n = g.inventory.list(c).length;
    const b = h('button', { class: c === invCat ? 'sel' : '' }, `${l} (${n})`);
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      invCat = c;
      invSel = null;
      rerender();
    });
    seg.appendChild(b);
  }
  seg.addEventListener('nav', (e) => {
    const i = cats.findIndex(([c]) => c === invCat);
    invCat = cats[(i + (e as CustomEvent).detail + cats.length) % cats.length][0];
    invSel = null;
    rerender();
  });
  const items = g.inventory.list(invCat);
  if (!invSel || !items.some((i) => i.def.id === invSel)) invSel = items[0]?.def.id ?? null;
  const grid = h('div', { class: 'inv-grid' });
  for (const it of items) {
    const color = RARITY_COLOR[it.def.rarity];
    const cell = h('button', { class: `item r-${it.def.rarity}${it.def.id === invSel ? ' sel' : ''}`, 'data-nav': 'grid', title: it.def.name }, h('span', { html: icon(it.def.icon, color) }), it.qty > 1 ? h('span', { class: 'q' }, '×' + it.qty) : null);
    cell.addEventListener('click', () => {
      invSel = it.def.id;
      rerender();
    });
    grid.appendChild(cell);
  }
  if (!items.length) grid.appendChild(h('div', { class: 'dim' }, t('inv.empty')));
  const sel = invSel ? Data.items[invSel] : null;
  const detail = h('div', { class: 'detail' });
  if (sel) {
    detail.append(
      h('span', { html: icon(sel.icon, RARITY_COLOR[sel.rarity]).replace('class="icon"', 'class="icon" style="width:3.4em;height:3.4em"') }),
      h('div', { class: 'nm' }, sel.name),
      h('div', { class: 'rar', style: { color: RARITY_COLOR[sel.rarity] } }, `${sel.rarity} · ${sel.category}`),
      h('div', { class: 'ds' }, sel.description),
      h('div', { class: 'faint', style: { fontSize: '0.8em' } }, `Quantity ${g.inventory.count(sel.id)} / ${sel.stack}${sel.quest ? ' · Quest: ' + (Data.quests[sel.quest]?.title ?? sel.quest) : ''}`),
    );
    if (sel.effect.type === 'powerup') {
      const use = h('button', { class: 'btn-small primary', 'data-nav': 'btn' }, t('inv.use'));
      use.addEventListener('click', () => {
        if (g.usePowerupItem(sel.id)) rerender();
      });
      detail.appendChild(use);
    }
    if (sel.effect.type === 'lore' && Data.dialogues[sel.effect.lore as string]) {
      const lines = g.dialogue.linearLines(sel.effect.lore as string);
      for (const l of lines) detail.appendChild(h('div', { class: 'lore-entry' }, h('div', { class: 'h', style: { color: l.speaker.color } }, l.speaker.name), h('div', { class: 'l' }, l.text)));
    }
  }
  body.append(seg, h('div', { class: 'inv' }, grid, detail));
}

// ---------------------------------------------------------------------------- Map
function map(ui: UI, body: HTMLElement) {
  const g = ui.game;
  const z = g.world.zone;
  if (!z) return;
  const cv = h('canvas', { width: 900, height: 690 }) as HTMLCanvasElement;
  const p = g.player;
  const tgt = g.ui.hud.objectiveTarget();
  drawZoneMap(cv, z, {
    center: p?.position ?? z.spawns.start.pos,
    heading: Math.PI,
    radius: 80,
    round: false,
    fit: true,
    player: p?.position ?? null,
    playerYaw: p?.yaw ?? 0,
    companion: g.companion?.model.root.visible ? g.companion.position : null,
    npcs: g.world.npcs.filter((n) => n.visible).map((n) => n.position),
    enemies: [],
    objective: tgt?.pos ?? null,
    exits: z.exits.map((e) => e.pos),
    echo: [],
    labels: true,
  });
  const exits = z.exits.map((e) => h('div', {}, h('i', { style: { background: '#5fd4f0' } }), `${e.prompt} → ${Data.zones[e.target]?.name ?? e.target}${e.requires && !e.requires() ? ' (locked)' : ''}`));
  body.appendChild(h('div', { class: 'map-wrap' }, cv, h('div', { class: 'legend' },
    h('div', { class: 'h2', style: { fontSize: '1.2em' } }, z.meta.name),
    h('div', { class: 'faint' }, z.meta.subtitle),
    h('div', {}, h('i', { style: { background: '#fff' } }), 'You'),
    h('div', {}, h('i', { style: { background: '#a68bff' } }), 'Partner'),
    h('div', {}, h('i', { style: { background: '#73e6b0' } }), 'Survivors'),
    h('div', {}, h('i', { style: { background: '#ffb45e' } }), tgt ? 'Objective: ' + tgt.label : 'No active objective'),
    h('div', { class: 'section-title', style: { margin: '1em 0 0.3em' } }, 'Exits'),
    ...exits,
  )));
}

// ---------------------------------------------------------------------------- Journal
let journalTab: 'active' | 'completed' | 'lore' = 'active';
let journalSel: string | null = null;

function journal(ui: UI, body: HTMLElement, rerender: () => void) {
  const g = ui.game;
  const d = g.gs.d;
  const count = (k: string) => d.collected.filter((c) => Data.collectibles[c]?.kind === k).length;
  body.appendChild(h('div', { class: 'completion' },
    h('div', { class: 'stat' }, h('div', { class: 'v' }, `${count('fragment')}/${COLLECTIBLE_TOTALS.fragment}`), h('div', { class: 'l' }, 'Aether Fragments')),
    h('div', { class: 'stat' }, h('div', { class: 'v' }, `${count('recording')}/${COLLECTIBLE_TOTALS.recording}`), h('div', { class: 'l' }, 'Memory Recordings')),
    h('div', { class: 'stat' }, h('div', { class: 'v' }, `${count('cache')}/${COLLECTIBLE_TOTALS.cache}`), h('div', { class: 'l' }, 'Hidden Caches')),
  ));
  const seg = h('div', { class: 'seg', 'data-nav': 'seg', style: { justifyContent: 'flex-start', marginBottom: '1em' } });
  const tabsDef: ['active' | 'completed' | 'lore', string][] = [['active', t('journal.active')], ['completed', t('journal.completed')], ['lore', t('journal.lore')]];
  for (const [k, l] of tabsDef) {
    const b = h('button', { class: k === journalTab ? 'sel' : '' }, l);
    b.addEventListener('click', (e) => {
      e.stopPropagation();
      journalTab = k;
      journalSel = null;
      rerender();
    });
    seg.appendChild(b);
  }
  seg.addEventListener('nav', (e) => {
    const i = tabsDef.findIndex(([k]) => k === journalTab);
    journalTab = tabsDef[(i + (e as CustomEvent).detail + 3) % 3][0];
    journalSel = null;
    rerender();
  });
  body.appendChild(seg);
  if (journalTab === 'lore') {
    const wrap = h('div', {});
    if (!d.lore.length) wrap.appendChild(h('div', { class: 'dim' }, 'No lore discovered yet. Recordings and research logs appear here.'));
    for (const id of d.lore) {
      const item = Data.itemList.find((i) => i.effect.type === 'lore' && i.effect.lore === id);
      const lines = g.dialogue.linearLines(id);
      wrap.appendChild(h('div', { class: 'lore-entry' }, h('div', { class: 'h' }, item?.name ?? id), ...lines.map((l) => h('div', { class: 'l' }, h('b', { style: { color: l.speaker.color } }, l.speaker.name + ': '), l.text))));
    }
    body.appendChild(wrap);
    return;
  }
  const quests = journalTab === 'active' ? g.quests.active() : g.quests.completed();
  if (!journalSel || !quests.some((q) => q.id === journalSel)) journalSel = quests[0]?.id ?? null;
  const list = h('div', { class: 'qlist' });
  for (const q of quests) {
    const b = h('button', { class: 'btn' + (q.id === journalSel ? ' focus' : ''), 'data-nav': 'btn' }, q.title, h('span', { class: 'sub' }, q.type === 'main' ? t('hud.mission') : t('hud.side')));
    b.addEventListener('click', () => {
      journalSel = q.id;
      rerender();
    });
    list.appendChild(b);
  }
  if (!quests.length) list.appendChild(h('div', { class: 'dim' }, journalTab === 'active' ? 'No active quests.' : 'Nothing completed yet.'));
  const detail = h('div', { class: 'qd' });
  const q = journalSel ? Data.quests[journalSel] : null;
  if (q) {
    detail.append(h('div', { class: 'kicker' }, q.type === 'main' ? `${t('hud.mission')} ${q.order}` : t('hud.side')), h('div', { class: 't' }, q.title), h('div', { class: 's' }, q.summary));
    if (journalTab === 'active') {
      for (const o of g.quests.currentObjectives(q.id)) detail.appendChild(h('div', { class: 'o' + (o.done ? ' done' : '') }, h('div', { class: 'dot' }), h('div', {}, g.quests.objectiveText(o.def) + (o.required > 1 ? ` (${o.progress}/${o.required})` : ''))));
      const tracked = g.quests.tracked()?.id === q.id;
      const tb = h('button', { class: 'btn-small' + (tracked ? '' : ' primary'), 'data-nav': 'btn', disabled: tracked, style: { marginTop: '1em' } }, tracked ? t('journal.tracked') : t('journal.track'));
      tb.addEventListener('click', () => {
        g.quests.track(q.id);
        rerender();
      });
      detail.appendChild(tb);
    } else detail.appendChild(h('div', { class: 'dim' }, '✓ Completed'));
  }
  body.appendChild(h('div', { class: 'journal' }, list, detail));
}

// ---------------------------------------------------------------------------- Ability Matrix
function skills(ui: UI, body: HTMLElement, rerender: () => void) {
  const g = ui.game;
  body.appendChild(h('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1em' } },
    h('div', { class: 'dim', style: { fontSize: '0.85em', maxWidth: '40em', lineHeight: '1.5' } }, 'Spend Aether to upgrade abilities. Each Aether Fragment is worth 1 point and each Aether Core is worth 3. Nodes unlock in order.'),
    h('div', {}, h('span', { class: 'faint', style: { fontSize: '0.8em', marginRight: '0.6em' } }, t('skills.points')), h('span', { class: 'points' }, String(g.progression.points()))),
  ));
  const tree = h('div', { class: 'tree' });
  for (const char of ['kael', 'lyra'] as const) {
    const col = h('div', { class: 'tree-col' }, h('div', { class: 'h', style: { color: char === 'kael' ? '#5fb8ff' : '#a68bff' } }, char === 'kael' ? 'Kael Voss' : 'Lyra Vale'));
    for (const ab of Data.abilityList.filter((a) => a.character === char && a.slot !== 'ultimate')) {
      const unlocked = g.gs.hasAbility(ab.id);
      col.appendChild(h('div', { class: 'faint', style: { fontSize: '0.75em', margin: '0.6em 0 0.4em', letterSpacing: '0.15em', textTransform: 'uppercase' } }, `${ab.name}${unlocked ? '' : ' · locked'}`));
      const rowEl = h('div', { class: 'tree-row' });
      for (const n of Data.skillList.filter((s) => s.ability === ab.id)) {
        const owned = g.progression.hasSkill(n.id);
        const can = g.progression.canBuy(n.id);
        const node = h('button', { class: `node ${owned ? 'owned' : can.ok ? 'avail' : 'locked'}`, 'data-nav': 'grid', title: owned ? 'Unlocked' : can.ok ? t('skills.unlock') : can.reason ?? '' }, h('div', { class: 'c' }, owned ? '✓' : String(n.cost)), h('div', { class: 'n' }, n.name), h('div', { class: 'd' }, n.description));
        node.addEventListener('click', () => {
          if (owned) return;
          if (g.progression.buy(n.id)) {
            g.audio.play('quest_accept');
            rerender();
          } else {
            g.audio.play('error_ui');
            ui.toast(can.reason ?? 'Unavailable', 'warn');
          }
        });
        rowEl.appendChild(node);
      }
      col.appendChild(rowEl);
    }
    tree.appendChild(col);
  }
  body.appendChild(tree);
}
