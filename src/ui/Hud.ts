import * as THREE from 'three';
import { Data } from '../game/Data';
import { h, type UI } from './UI';
import { icon } from './Icons';
import { portrait } from './Portraits';
import { t } from './Locale';
import { drawZoneMap } from './MapDraw';
import type { Enemy } from '../actors/enemies/Enemy';

// Gameplay HUD.

const ZONE_GRAPH: Record<string, string[]> = {
  plaza: ['metro', 'facility', 'rooftops'],
  metro: ['plaza', 'facility'],
  facility: ['metro', 'plaza', 'vault'],
  vault: ['facility', 'core'],
  rooftops: ['plaza'],
  core: ['vault'],
};

function nextHop(from: string, to: string): string | null {
  if (from === to) return null;
  const prev: Record<string, string> = {};
  const q = [from];
  const seen = new Set([from]);
  while (q.length) {
    const z = q.shift()!;
    for (const n of ZONE_GRAPH[z] ?? []) {
      if (seen.has(n)) continue;
      seen.add(n);
      prev[n] = z;
      if (n === to) {
        let cur = n;
        while (prev[cur] !== from) cur = prev[cur];
        return cur;
      }
      q.push(n);
    }
  }
  return null;
}

export class Hud {
  readonly el: HTMLElement;
  private hp!: HTMLElement;
  private hpTrail!: HTMLElement;
  private sh!: HTMLElement;
  private en!: HTMLElement;
  private hpNum!: HTMLElement;
  private name!: HTMLElement;
  private port!: HTMLElement;
  private abEls: Record<string, { root: HTMLElement; cd: HTMLElement; cdt: HTMLElement; extra?: HTMLElement }> = {};
  private ultRing!: SVGCircleElement;
  private ultEl!: HTMLElement;
  private tracker!: HTMLElement;
  private trackerKey = '';
  private mini!: HTMLCanvasElement;
  private miniZone!: HTMLElement;
  private pus!: HTMLElement;
  private prompt!: HTMLElement;
  private cross!: HTMLElement;
  private hitm!: HTMLElement;
  private marker!: HTMLElement;
  private markerD!: HTMLElement;
  private ebars: HTMLElement[] = [];
  private boss!: HTMLElement;
  private bossFill!: HTMLElement;
  private bossName!: HTMLElement;
  private bossPhase!: HTMLElement;
  private dmg = 0;
  private hitT = 0;
  private miniT = 0;
  private trailW = 1;
  visible = true;

  constructor(private ui: UI) {
    this.el = h('div', { class: 'hud' });
    this.build();
  }

  private build() {
    // Vitals
    this.port = h('div', { class: 'portrait' }, h('div', { class: 'swap hidden' }));
    this.name = h('div', { class: 'vit-name' });
    this.hpTrail = h('b');
    this.hp = h('i');
    this.sh = h('i');
    this.en = h('i');
    this.hpNum = h('div', { class: 'vit-num' });
    const bars = h('div', {}, this.name, h('div', { class: 'bar sh' }, this.sh), h('div', { class: 'bar hp' }, this.hpTrail, this.hp), h('div', { class: 'bar en' }, this.en), this.hpNum);
    this.el.appendChild(h('div', { class: 'vitals' }, this.port, bars));
    // Abilities
    const abWrap = h('div', { class: 'abilities' });
    for (const [key, lbl] of [['bolt', 'hud.bolt'], ['dash', 'hud.dash'], ['ability', 'hud.ability']] as [string, string][]) {
      const cd = h('div', { class: 'cd' });
      const cdt = h('div', { class: 'cdt' });
      const extra = h('div', { class: 'charges' });
      const slot = h('div', { class: 'slot' }, h('span', { class: 'ic' }), cd, cdt, extra);
      const root = h('div', { class: 'ab' }, slot, h('div', { class: 'kc' }), h('div', { class: 'lbl' }, t(lbl)));
      abWrap.appendChild(root);
      this.abEls[key] = { root, cd, cdt, extra };
    }
    this.ultEl = h('div', { class: 'ab ult-wrap' });
    const svgNS = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(svgNS, 'svg');
    svg.setAttribute('viewBox', '0 0 60 60');
    const bg = document.createElementNS(svgNS, 'circle');
    bg.setAttribute('cx', '30'); bg.setAttribute('cy', '30'); bg.setAttribute('r', '26');
    bg.setAttribute('stroke', 'rgba(255,255,255,0.12)'); bg.setAttribute('stroke-width', '3'); bg.setAttribute('fill', 'rgba(6,9,13,0.7)');
    this.ultRing = document.createElementNS(svgNS, 'circle');
    this.ultRing.setAttribute('cx', '30'); this.ultRing.setAttribute('cy', '30'); this.ultRing.setAttribute('r', '26');
    this.ultRing.setAttribute('stroke', '#5fd4f0'); this.ultRing.setAttribute('stroke-width', '3'); this.ultRing.setAttribute('fill', 'none');
    this.ultRing.setAttribute('transform', 'rotate(-90 30 30)');
    this.ultRing.classList.add('ring');
    svg.append(bg, this.ultRing);
    const ult = h('div', { class: 'ult' });
    ult.appendChild(svg);
    ult.appendChild(h('span', { class: 'ic' }));
    this.ultEl.append(ult, h('div', { class: 'kc' }), h('div', { class: 'lbl' }, t('hud.ult')));
    abWrap.appendChild(this.ultEl);
    this.el.appendChild(abWrap);
    // Tracker
    this.tracker = h('div', { class: 'tracker' });
    this.el.appendChild(this.tracker);
    // Minimap
    this.mini = h('canvas', { width: 230, height: 230 }) as HTMLCanvasElement;
    this.miniZone = h('div', { class: 'zn' });
    this.el.appendChild(h('div', { class: 'minimap' }, this.mini, this.miniZone));
    // Powerups
    this.pus = h('div', { class: 'powerups' });
    this.el.appendChild(this.pus);
    // Prompt, crosshair, markers
    this.prompt = h('div', { class: 'prompt hidden' });
    this.cross = h('div', { class: 'crosshair' });
    this.hitm = h('div', { class: 'hitmark' });
    this.markerD = h('div', { class: 'd' });
    this.marker = h('div', { class: 'marker hidden' }, h('div', { class: 'm' }), this.markerD);
    this.el.append(this.prompt, this.cross, this.hitm, this.marker);
    for (let i = 0; i < 10; i++) {
      const b = h('div', { class: 'ebar hidden' }, h('div', { class: 'n' }), h('div', { class: 'b' }, h('i')), h('div', { class: 'p' }, h('i')));
      this.ebars.push(b);
      this.el.appendChild(b);
    }
    this.bossFill = h('i');
    this.bossName = h('div', { class: 'n' });
    this.bossPhase = h('div', { class: 'ph' });
    this.boss = h('div', { class: 'bossbar hidden' }, this.bossName, h('div', { class: 'b' }, this.bossFill), this.bossPhase);
    this.el.appendChild(this.boss);
  }

  setVisible(v: boolean) {
    this.visible = v;
    this.el.classList.toggle('fade', !v);
  }

  characterChanged() {
    const g = this.ui.game;
    const c = g.gs.d.character;
    this.port.className = 'portrait ' + c;
    const p = portrait(c);
    this.port.style.backgroundImage = p ? `url(${p})` : '';
    this.name.innerHTML = '';
    this.name.append(c === 'kael' ? 'Kael Voss' : 'Lyra Vale');
    const color = c === 'kael' ? '#5fb8ff' : '#a68bff';
    const ab = c === 'kael' ? 'ab_pulse' : 'ab_echo';
    const dash = c === 'kael' ? 'ab_dash' : 'ab_step';
    this.abEls.ability.root.querySelector('.ic')!.innerHTML = icon(ab, color);
    this.abEls.dash.root.querySelector('.ic')!.innerHTML = icon(dash, color);
    this.abEls.bolt.root.querySelector('.ic')!.innerHTML = icon('ab_bolt', color);
    this.ultEl.querySelector('.ic')!.innerHTML = icon(c === 'kael' ? 'ab_corebreak' : 'ab_resonance', color);
    this.ultRing.setAttribute('stroke', color);
    this.refreshKeys();
  }

  refreshKeys() {
    const inp = this.ui.game.input;
    this.abEls.ability.root.querySelector('.kc')!.innerHTML = `<span class="keycap">${inp.label('ability')}</span>`;
    this.abEls.dash.root.querySelector('.kc')!.innerHTML = `<span class="keycap">${inp.label('dash')}</span>`;
    this.abEls.bolt.root.querySelector('.kc')!.innerHTML = `<span class="keycap">${inp.label('bolt')}</span>`;
    this.ultEl.querySelector('.kc')!.innerHTML = `<span class="keycap">${inp.label('ultimate')}</span>`;
    const sw = this.port.querySelector('.swap') as HTMLElement;
    sw.classList.toggle('hidden', !this.ui.game.gs.flag('swap_unlocked'));
    sw.innerHTML = `<span class="keycap">${inp.label('swap')}</span>`;
  }

  damagePulse(amount: number) {
    this.dmg = Math.min(1, this.dmg + amount / 40);
  }
  damageAmount() {
    return this.dmg;
  }
  hitMarker() {
    this.hitT = 0.12;
    this.hitm.classList.remove('kill');
    this.hitm.classList.add('on');
  }
  killMarker() {
    this.hitT = 0.25;
    this.hitm.classList.add('on', 'kill');
  }

  update(dt: number) {
    const g = this.ui.game;
    this.dmg = Math.max(0, this.dmg - dt * 1.5);
    if (this.hitT > 0) {
      this.hitT -= dt;
      if (this.hitT <= 0) this.hitm.classList.remove('on');
    }
    if (g.mode !== 'play' || !this.visible) return;
    const p = g.player;
    if (!p) return;
    const st = p.stats;
    const hpF = Math.max(0, p.health / st.maxHealth);
    this.hp.style.width = (hpF * 100).toFixed(1) + '%';
    this.trailW = Math.max(hpF, this.trailW - dt * 0.4);
    if (hpF > this.trailW) this.trailW = hpF;
    this.hpTrail.style.width = (this.trailW * 100).toFixed(1) + '%';
    this.sh.style.width = ((p.shield / st.maxShield) * 100).toFixed(1) + '%';
    this.en.style.width = ((p.energy / st.maxEnergy) * 100).toFixed(1) + '%';
    this.hpNum.innerHTML = `<span>${Math.ceil(p.health)} / ${st.maxHealth}</span><span>${Math.floor(p.shield)} SH</span>`;
    // Abilities
    const kael = p.character === 'kael';
    const abId = kael ? 'pulse' : 'echo';
    const abUnlocked = g.gs.hasAbility(abId);
    const abCdMax = (kael ? 6 : 4) * st.cooldownMul;
    this.setSlot('ability', abUnlocked, p.cdAbility, abCdMax, p.energy >= (kael ? 35 : 25));
    const dashUnlocked = g.gs.hasAbility(kael ? 'dash' : 'step');
    this.setSlot('dash', dashUnlocked, p.dashCharges > 0 ? 0 : p.cdDash, st.dashCooldown * st.cooldownMul, true);
    this.abEls.dash.extra!.textContent = st.dashCharges > 1 ? String(p.dashCharges) : '';
    this.setSlot('bolt', true, 0, 1, p.energy >= 6);
    const ultOn = st.ultimates;
    this.ultEl.classList.toggle('locked', !ultOn);
    const circ = 2 * Math.PI * 26;
    this.ultRing.setAttribute('stroke-dasharray', `${((ultOn ? p.ult / 100 : 0) * circ).toFixed(1)} ${circ.toFixed(1)}`);
    this.ultEl.querySelector('.ult')!.classList.toggle('full', ultOn && p.ult >= 100);
    // Powerups
    const act = [...g.powerups.active.entries()];
    const key = act.map(([id]) => id).join(',');
    if (this.pus.dataset.k !== key) {
      this.pus.dataset.k = key;
      this.pus.innerHTML = '';
      for (const [id] of act) {
        const d = Data.powerups[id];
        this.pus.appendChild(h('div', { class: 'pu', 'data-id': id, style: { color: d.color } }, h('span', { html: icon(d.icon, d.color) }), h('div', { class: 'ring' }), h('div', { class: 't' })));
      }
    }
    for (const [id, s] of act) {
      const el = this.pus.querySelector(`[data-id="${id}"]`);
      if (!el) continue;
      (el.querySelector('.ring') as HTMLElement).style.width = ((s.remaining / s.duration) * 100).toFixed(0) + '%';
      el.querySelector('.t')!.textContent = Math.ceil(s.remaining) + 's';
    }
    // Tracker
    this.updateTracker();
    // Prompt
    const c = g.world.candidate;
    if (c && !g.inDialogue && !g.cinematics.active && p.alive) {
      const text = typeof c.prompt === 'function' ? c.prompt() : c.prompt;
      const locked = g.world.candidateLocked;
      const html = locked ? `<span>${locked}</span>` : `<span class="keycap">${g.input.label('interact')}</span><span>${text}</span>`;
      if (this.prompt.innerHTML !== html) this.prompt.innerHTML = html;
      this.prompt.classList.toggle('locked', !!locked);
      this.prompt.classList.remove('hidden');
    } else this.prompt.classList.add('hidden');
    this.cross.classList.toggle('on', g.cam.aiming);
    // Marker + minimap
    this.updateMarker();
    this.miniT -= dt;
    if (this.miniT <= 0) {
      this.miniT = 1 / 20;
      this.drawMinimap();
    }
    this.updateEnemyBars();
  }

  private setSlot(key: string, unlocked: boolean, cd: number, cdMax: number, affordable: boolean) {
    const s = this.abEls[key];
    s.root.classList.toggle('locked', !unlocked);
    s.root.classList.toggle('ready', unlocked && cd <= 0 && affordable);
    s.cd.style.height = unlocked ? Math.min(100, (cd / Math.max(0.01, cdMax)) * 100).toFixed(0) + '%' : '100%';
    s.cdt.textContent = unlocked && cd > 0.05 ? cd.toFixed(cd < 1 ? 1 : 0) : '';
    if (!unlocked) s.cdt.innerHTML = icon('lock', '#8a9aab');
  }

  /** World position of the tracked objective (or the exit toward it). */
  objectiveTarget(): { pos: THREE.Vector3; label: string } | null {
    const g = this.ui.game;
    const q = g.quests.tracked();
    const z = g.world.zone;
    if (!q || !z) return null;
    const obj = g.quests.currentObjectives(q.id).find((o) => !o.done);
    if (!obj) return null;
    const markerId = obj.def.marker;
    let pos: THREE.Vector3 | null = markerId ? z.resolveMarker(markerId) : null;
    // Encounter objectives point at the nearest living enemy of the encounter.
    if (!pos && obj.def.type === 'kill') {
      const e = g.world.enemies.find((x) => x.encounterId === obj.def.target && x.alive);
      if (e) pos = e.position.clone().setY(e.position.y + e.height);
    }
    if (pos) return { pos, label: g.quests.objectiveText(obj.def) };
    // Off-zone: route through the right exit.
    let targetZone = obj.def.type === 'zone' ? obj.def.target : q.zone;
    if (markerId === 'npc_mira' || markerId === 'npc_tomas' || markerId === 'i_bolt' || markerId === 'i_market_cell') targetZone = 'plaza';
    if (markerId?.startsWith('i_metro')) targetZone = 'metro';
    if (markerId === 'i_control_component' || markerId === 'i_relay_tower' || markerId === 'i_relay_cell' || markerId === 'i_relay_socket') targetZone = 'rooftops';
    if (markerId === 'c_rec_03') targetZone = 'metro';
    if (markerId === 'c_rec_05') targetZone = 'facility';
    if (markerId === 'c_rec_02') targetZone = 'plaza';
    if (markerId === 'i_freight_lift') targetZone = 'facility';
    if (markerId === 'i_hidden_door') targetZone = 'vault';
    const hop = nextHop(z.id, targetZone);
    if (!hop) return null;
    const exit = z.exits.find((x) => x.target === hop && (!x.requires || x.requires())) ?? z.exits.find((x) => x.target === hop);
    if (!exit) return null;
    return { pos: exit.pos.clone().setY(exit.pos.y + 1.5), label: `${g.quests.objectiveText(obj.def)} · ${Data.zones[hop]?.name ?? hop}` };
  }

  private updateMarker() {
    const g = this.ui.game;
    const tgt = this.objectiveTarget();
    if (!tgt || g.cinematics.active || g.inDialogue) {
      this.marker.classList.add('hidden');
      return;
    }
    const cam = g.rs.camera;
    const v = tgt.pos.clone().project(cam);
    const behind = v.z > 1;
    let x = (v.x * 0.5 + 0.5) * window.innerWidth;
    let y = (-v.y * 0.5 + 0.5) * window.innerHeight;
    const margin = 50;
    // Keep clear of the vitals, abilities and subtitles along the bottom edge.
    const maxY = window.innerHeight - Math.max(margin, window.innerHeight * 0.22);
    let edge = false;
    if (behind) {
      x = window.innerWidth - x;
      y = maxY;
      edge = true;
    }
    if (x < margin || x > window.innerWidth - margin || y < margin || y > maxY) edge = true;
    x = Math.max(margin, Math.min(window.innerWidth - margin, x));
    y = Math.max(margin + 20, Math.min(maxY, y));
    this.marker.style.left = x + 'px';
    this.marker.style.top = y + 'px';
    this.marker.classList.toggle('edge', edge);
    const d = g.player ? g.player.position.distanceTo(tgt.pos) : 0;
    this.markerD.textContent = `${Math.round(d)} m`;
    this.marker.classList.toggle('hidden', d < 2.5);
  }

  private updateTracker() {
    const g = this.ui.game;
    const q = g.quests.tracked();
    if (!q) {
      if (this.trackerKey !== '') {
        this.tracker.innerHTML = '';
        this.trackerKey = '';
      }
      return;
    }
    const objs = g.quests.currentObjectives(q.id);
    const key = q.id + '|' + objs.map((o) => `${o.def.id}:${o.progress}`).join(',') + '|' + g.gs.d.character;
    if (key === this.trackerKey) return;
    const changed = this.trackerKey.split('|')[0] === q.id;
    this.trackerKey = key;
    this.tracker.innerHTML = '';
    this.tracker.appendChild(h('div', { class: 'q' + (changed ? ' flash' : '') }, h('span', { class: 'tag' + (q.type === 'side' ? ' side' : '') }, q.type === 'main' ? t('hud.mission') : t('hud.side')), q.title));
    for (const o of objs) {
      const txt = g.quests.objectiveText(o.def) + (o.required > 1 ? ` (${o.progress}/${o.required})` : '');
      this.tracker.appendChild(h('div', { class: 'obj' + (o.done ? ' done' : '') }, h('div', { class: 'dot' }), h('div', {}, txt)));
    }
  }

  private drawMinimap() {
    const g = this.ui.game;
    const z = g.world.zone;
    const p = g.player;
    if (!z || !p) return;
    this.miniZone.textContent = z.meta.name;
    const tgt = this.objectiveTarget();
    drawZoneMap(this.mini, z, {
      center: p.position,
      heading: g.cam.heading,
      radius: 55,
      round: true,
      player: p.position,
      playerYaw: p.yaw,
      companion: g.companion?.model.root.visible ? g.companion.position : null,
      npcs: g.world.npcs.filter((n) => n.visible).map((n) => n.position),
      enemies: g.world.enemies.filter((e) => e.alive && (e.aggro || e.position.distanceTo(p.position) < 25)).map((e) => e.position),
      objective: tgt?.pos ?? null,
      exits: z.exits.map((e) => e.pos),
      echo: g.world.echoActive && g.progression.stats('lyra').echoDetect ? g.world.pickups.filter((x) => !x.collected).map((x) => x.pos) : [],
    });
  }

  private updateEnemyBars() {
    const g = this.ui.game;
    const p = g.player;
    const cam = g.rs.camera;
    let i = 0;
    let boss: Enemy | null = null;
    if (p) {
      for (const e of g.world.enemies) {
        if (!e.alive) continue;
        if (e.def.tags.includes('boss')) {
          if (e.aggro) boss = e;
          continue;
        }
        if (i >= this.ebars.length) break;
        const d = e.position.distanceTo(p.position);
        if (d > 28 || (!e.aggro && e.sinceHit > 4)) continue;
        const pos = e.position.clone().setY(e.position.y + e.height + 0.35);
        const v = pos.project(cam);
        if (v.z > 1 || Math.abs(v.x) > 1 || Math.abs(v.y) > 1) continue;
        const el = this.ebars[i++];
        el.classList.remove('hidden');
        el.style.left = ((v.x * 0.5 + 0.5) * window.innerWidth).toFixed(0) + 'px';
        el.style.top = ((-v.y * 0.5 + 0.5) * window.innerHeight).toFixed(0) + 'px';
        (el.querySelector('.n') as HTMLElement).textContent = e.def.tags.includes('elite') ? e.name : '';
        (el.querySelector('.b i') as HTMLElement).style.width = (e.hpFrac * 100).toFixed(0) + '%';
        (el.querySelector('.p i') as HTMLElement).style.width = ((1 - e.poise / e.maxPoise) * 100).toFixed(0) + '%';
        el.classList.toggle('stag', e.state === 'stagger');
      }
    }
    for (; i < this.ebars.length; i++) this.ebars[i].classList.add('hidden');
    if (boss) {
      this.boss.classList.remove('hidden');
      this.bossName.textContent = boss.name;
      this.bossFill.style.width = (boss.hpFrac * 100).toFixed(1) + '%';
      const ph = (boss as unknown as { phase?: number }).phase;
      this.bossPhase.textContent = ph ? `Phase ${ph}` : '';
    } else this.boss.classList.add('hidden');
  }
}
