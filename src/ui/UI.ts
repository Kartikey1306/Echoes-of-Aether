import './styles.css';
import { events } from '../core/Events';
import { bindingLabel, type Action } from '../core/Input';
import { Log } from '../core/Log';
import { Data } from '../game/Data';
import type { Game } from '../game/Game';
import type { SettingsData } from '../game/Settings';
import { DialogueViewDOM } from './DialogueView';
import { Hud } from './Hud';
import { LoadingScreen } from './Loading';
import * as Screens from './Screens';
import { openSettings } from './SettingsScreen';
import * as Panels from './Panels';
import { t } from './Locale';

// DOM UI layer: screen stack with keyboard/gamepad navigation, overlays and feedback.

export function h<K extends keyof HTMLElementTagNameMap>(tag: K, attrs: Record<string, unknown> = {}, ...children: (Node | string | null | undefined | false)[]): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = String(v);
    else if (k === 'html') el.innerHTML = String(v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2).toLowerCase(), v as EventListener);
    else if (v === true) el.setAttribute(k, '');
    else el.setAttribute(k, String(v));
  }
  for (const c of children) {
    if (c === null || c === undefined || c === false) continue;
    el.append(typeof c === 'string' ? document.createTextNode(c) : c);
  }
  return el;
}

export interface ScreenEntry {
  id: string;
  el: HTMLElement;
  back?: () => void;
  /** Called on left/right for focused segmented controls. */
  overlay?: boolean;
  onClose?: () => void;
}

export class UI {
  readonly root: HTMLElement;
  readonly hud: Hud;
  readonly dialogue: DialogueViewDOM;
  readonly loading: LoadingScreen;
  private stack: ScreenEntry[] = [];
  private toasts: HTMLElement;
  private fader: HTMLElement;
  private bars: [HTMLElement, HTMLElement];
  private skip: HTMLElement;
  private debugEl: HTMLElement;
  private hintEl: HTMLElement | null = null;
  private hintTimer = 0;
  private backConsumed = false;
  private focusIndex = 0;
  private saveInd: HTMLElement;
  private saveIndT = 0;
  private repeatT = 0;
  private lastNavDir = '';
  debugOn = false;

  constructor(readonly game: Game, container: HTMLElement) {
    this.root = h('div', { id: 'ui' });
    container.appendChild(this.root);
    this.hud = new Hud(this);
    this.root.appendChild(this.hud.el);
    this.dialogue = new DialogueViewDOM(this);
    this.root.appendChild(this.dialogue.el);
    this.toasts = h('div', { class: 'toasts' });
    this.root.appendChild(this.toasts);
    this.bars = [h('div', { class: 'letterbox top' }), h('div', { class: 'letterbox bot' })];
    this.root.append(...this.bars);
    this.skip = h('div', { class: 'skip' });
    this.root.appendChild(this.skip);
    this.saveInd = h('div', { class: 'saveind' }, h('i'), t('hud.saving'));
    this.root.appendChild(this.saveInd);
    this.loading = new LoadingScreen(this);
    this.root.appendChild(this.loading.el);
    this.fader = h('div', { class: 'fader' });
    this.root.appendChild(this.fader);
    this.debugEl = h('div', { class: 'debug hidden' });
    this.root.appendChild(this.debugEl);
    this.hud.setVisible(false);
    events.on('ui:toast', (p) => this.toast(p.text, p.kind));
    window.addEventListener('keydown', this.onKey, { capture: false });
    this.root.addEventListener('mouseover', (e) => {
      const el = (e.target as HTMLElement).closest('[data-nav]') as HTMLElement | null;
      if (!el) return;
      const list = this.navList();
      const i = list.indexOf(el);
      if (i >= 0 && i !== this.focusIndex) {
        this.focusIndex = i;
        this.paintFocus();
        this.game.audio.play('ui_hover');
      }
    });
    this.root.addEventListener('click', (e) => {
      if ((e.target as HTMLElement).closest('button, [data-nav]')) this.game.audio.play('ui_click');
    });
  }

  // ------------------------------------------------------------------ Screen stack
  push(entry: ScreenEntry) {
    this.root.insertBefore(entry.el, this.fader);
    this.stack.push(entry);
    this.focusIndex = 0;
    const list = this.navList();
    const pre = list.findIndex((e) => e.hasAttribute('data-autofocus'));
    if (pre >= 0) this.focusIndex = pre;
    this.paintFocus();
    this.syncPause();
  }

  pop(id?: string) {
    const idx = id ? this.stack.findIndex((s) => s.id === id) : this.stack.length - 1;
    if (idx < 0) return;
    const [e] = this.stack.splice(idx, 1);
    e.el.remove();
    e.onClose?.();
    this.focusIndex = 0;
    this.paintFocus();
    this.syncPause();
  }

  top(): ScreenEntry | null {
    return this.stack[this.stack.length - 1] ?? null;
  }

  has(id: string) {
    return this.stack.some((s) => s.id === id);
  }

  hideAllScreens() {
    while (this.stack.length) this.pop();
  }

  /** Close in-game overlays (pause, panels, saves) and resume. */
  closeOverlays() {
    for (let i = this.stack.length - 1; i >= 0; i--) if (this.stack[i].overlay) this.pop(this.stack[i].id);
  }

  private syncPause() {
    const g = this.game;
    const overlay = this.stack.some((s) => s.overlay);
    if (g.mode === 'play') {
      const was = g.paused;
      g.paused = overlay;
      if (overlay && !was) {
        g.input.releaseLock();
        g.player?.cancelActions();
        g.voice.stop();
      }
      if (!overlay && was && !g.inDialogue && !g.cinematics.active) g.input.requestLock();
      this.hud.setVisible(!overlay);
    }
  }

  consumedBack() {
    const c = this.backConsumed;
    this.backConsumed = false;
    return c;
  }

  // ------------------------------------------------------------------ Navigation
  private navList(): HTMLElement[] {
    const t = this.dialogue.choicesActive ? { el: this.dialogue.el } : this.top();
    if (!t) return [];
    return [...t.el.querySelectorAll<HTMLElement>('[data-nav]')].filter((e) => e.offsetParent !== null && !e.hasAttribute('disabled'));
  }

  /** Re-apply focus styling after a screen re-renders. */
  refocus() {
    this.paintFocus();
  }

  private paintFocus() {
    const list = this.navList();
    if (!list.length) return;
    this.focusIndex = Math.max(0, Math.min(this.focusIndex, list.length - 1));
    list.forEach((e, i) => e.classList.toggle('focus', i === this.focusIndex));
    list[this.focusIndex].scrollIntoView?.({ block: 'nearest' });
  }

  private navigate(dir: 'up' | 'down' | 'left' | 'right' | 'ok' | 'back') {
    const list = this.navList();
    const cur = list[this.focusIndex];
    if (dir === 'back') {
      const top = this.top();
      if (this.dialogue.choicesActive) return;
      if (top?.back) {
        this.backConsumed = true;
        this.game.audio.play('ui_back');
        top.back();
      }
      return;
    }
    if (!list.length) return;
    if (dir === 'ok') {
      cur?.click();
      return;
    }
    if ((dir === 'left' || dir === 'right') && cur) {
      const kind = cur.getAttribute('data-nav');
      if (kind === 'seg' || kind === 'slider') {
        cur.dispatchEvent(new CustomEvent('nav', { detail: dir === 'left' ? -1 : 1 }));
        return;
      }
      if (kind === 'grid') {
        this.focusIndex += dir === 'left' ? -1 : 1;
        this.paintFocus();
        this.game.audio.play('ui_hover');
        return;
      }
    }
    if (dir === 'up' || dir === 'left') this.focusIndex = (this.focusIndex - 1 + list.length) % list.length;
    else this.focusIndex = (this.focusIndex + 1) % list.length;
    this.paintFocus();
    this.game.audio.play('ui_hover');
  }

  private onKey = (e: KeyboardEvent) => {
    if (!this.top() && !this.dialogue.choicesActive) return;
    const tag = (e.target as HTMLElement)?.tagName;
    if (tag === 'INPUT' && (e.code === 'ArrowLeft' || e.code === 'ArrowRight')) return;
    const map: Record<string, 'up' | 'down' | 'left' | 'right' | 'ok' | 'back'> = {
      ArrowUp: 'up', ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', KeyW: 'up', KeyS: 'down', Enter: 'ok', Escape: 'back', Backspace: 'back',
    };
    const d = map[e.code];
    if (!d) return;
    if (this.game.input.capturing) return;
    e.preventDefault();
    this.navigate(d);
  };

  update(dt: number) {
    const g = this.game;
    // Gamepad navigation (with key-repeat).
    if (this.top() || this.dialogue.choicesActive) {
      const inp = g.input;
      const dirs: [string, 'up' | 'down' | 'left' | 'right'][] = [['B12', 'up'], ['B13', 'down'], ['B14', 'left'], ['B15', 'right']];
      let held = '';
      for (const [code, d] of dirs) {
        if (inp.codePressed(code)) {
          this.navigate(d);
          this.repeatT = 0.4;
          this.lastNavDir = code;
        }
        if (inp.codeHeld(code)) held = code;
      }
      if (held && held === this.lastNavDir) {
        this.repeatT -= dt;
        if (this.repeatT <= 0) {
          this.repeatT = 0.12;
          this.navigate(dirs.find((x) => x[0] === held)![1]);
        }
      }
      if (inp.codePressed('B0')) this.navigate('ok');
      if (inp.codePressed('B1')) this.navigate('back');
    }
    this.hud.update(dt);
    this.dialogue.update(dt);
    if (this.hintEl) {
      this.hintTimer -= dt;
      if (this.hintTimer <= 0) {
        this.hintEl.remove();
        this.hintEl = null;
      }
    }
    if (this.saveIndT > 0) {
      this.saveIndT -= dt;
      if (this.saveIndT <= 0) this.saveInd.classList.remove('on');
    }
    if (this.debugOn) this.updateDebug();
  }

  // ------------------------------------------------------------------ Screens
  showMainMenu() {
    this.hideAllScreens();
    this.hud.setVisible(false);
    this.cinematicBars(false);
    this.fadeInstant(false);
    Screens.mainMenu(this);
  }

  showCharSelect() {
    Screens.charSelect(this);
  }

  showHud() {
    this.hud.setVisible(true);
    this.hud.characterChanged();
  }

  openPause() {
    if (this.has('pause') || this.game.mode !== 'play') return;
    Screens.pause(this);
  }

  openSettings(inGame: boolean) {
    openSettings(this, inGame);
  }

  openSaveScreen(mode: 'save' | 'load', fromTerminal = false) {
    Screens.saves(this, mode, fromTerminal);
  }

  openPanel(name: 'inventory' | 'map' | 'journal' | 'skills') {
    if (this.game.mode !== 'play') return;
    Panels.open(this, name);
  }

  showDeath() {
    this.hintEl?.remove();
    this.hintEl = null;
    Screens.death(this);
  }

  showCredits(): Promise<void> {
    return Screens.credits(this);
  }

  confirm(title: string, message: string, okLabel = 'Confirm', danger = false): Promise<boolean> {
    return Screens.confirm(this, title, message, okLabel, danger);
  }

  // ------------------------------------------------------------------ Feedback
  toast(text: string, kind: 'info' | 'quest' | 'item' | 'warn' | 'lore' = 'info') {
    const el = h('div', { class: 'toast k-' + kind }, text);
    this.toasts.prepend(el);
    while (this.toasts.children.length > 5) this.toasts.lastElementChild?.remove();
    setTimeout(() => el.classList.add('out'), 3800);
    setTimeout(() => el.remove(), 4300);
    if (kind === 'item') this.game.audio.play('item');
  }

  /** Text with {action} placeholders replaced by the current bindings. */
  keyText(text: string): string {
    const inp = this.game.input;
    return text.replace(/\{(\w+)\}/g, (_, a: string) => {
      const b = inp.bindings[a as Action];
      if (!b) return a;
      const code = inp.lastDevice === 'pad' && b.pad.length ? b.pad[0] : b.kb[0] ?? b.pad[0];
      return `<span class="keycap">${bindingLabel(code ?? '')}</span>`;
    });
  }

  hint(id: string) {
    const def = Data.hints[id];
    if (!def) return;
    this.hintEl?.remove();
    this.hintEl = h('div', { class: 'hintbox', html: this.keyText(def.text) });
    this.root.insertBefore(this.hintEl, this.toasts);
    this.hintTimer = 8;
  }

  questComplete(id: string) {
    const q = Data.quests[id];
    if (!q) return;
    const el = h('div', { class: 'questbanner' }, h('div', { class: 'k' }, q.type === 'main' ? t('hud.missionComplete') : t('hud.questComplete')), h('div', { class: 't' }, q.title));
    this.root.insertBefore(el, this.toasts);
    setTimeout(() => el.remove(), 4200);
  }

  saveIndicator(kind: string) {
    this.saveInd.lastChild!.textContent = kind === 'manual' ? t('hud.saved') : t('hud.autosaved');
    this.saveInd.classList.add('on');
    this.saveIndT = 2.2;
  }

  fade(toBlack: boolean, sec: number): Promise<void> {
    const f = this.fader;
    f.style.transition = `opacity ${sec}s ease`;
    // Force style flush so the transition runs.
    void f.offsetWidth;
    f.style.opacity = toBlack ? '1' : '0';
    return new Promise((r) => setTimeout(r, sec * 1000 + 20));
  }

  fadeInstant(toBlack: boolean) {
    this.fader.style.transition = 'none';
    this.fader.style.opacity = toBlack ? '1' : '0';
  }

  cinematicBars(on: boolean) {
    this.bars.forEach((b) => b.classList.toggle('on', on));
    this.hud.setVisible(!on && this.game.mode === 'play' && !this.game.paused);
    if (!on) this.skip.classList.remove('on');
  }

  skipPrompt(frac: number, visible: boolean) {
    const key = this.game.input.lastDevice === 'pad' ? 'A' : 'Space';
    const hold = this.game.settings.data.accessibility.holdToSkip;
    this.skip.innerHTML = `<svg class="ring" viewBox="0 0 20 20"><circle cx="10" cy="10" r="8" stroke="rgba(255,255,255,0.2)" stroke-width="2" fill="none"/><circle cx="10" cy="10" r="8" stroke="#5fd4f0" stroke-width="2" fill="none" stroke-dasharray="${(frac * 50.3).toFixed(1)} 60" transform="rotate(-90 10 10)"/></svg><span>${hold ? t('cine.holdSkip') : t('cine.pressSkip')}</span><span class="keycap">${key}</span>`;
    this.skip.classList.toggle('on', true);
    void visible;
  }

  applySettings(s: SettingsData) {
    const r = document.documentElement.style;
    r.setProperty('--ui-scale', String(s.accessibility.uiScale));
    r.setProperty('--sub-bg', String(s.accessibility.subtitleBackground));
    r.setProperty('--sub-size', { small: '0.95em', medium: '1.15em', large: '1.4em', xl: '1.75em' }[s.accessibility.subtitleSize]);
    this.dialogue.subtitles = s.accessibility.subtitles;
    this.dialogue.speakerNames = s.accessibility.speakerNames;
  }

  setDebug(on: boolean) {
    this.debugOn = on && __DEV_TOOLS__;
    this.debugEl.classList.toggle('hidden', !this.debugOn);
  }

  private updateDebug() {
    const g = this.game;
    const p = g.player;
    const mem = (performance as unknown as { memory?: { usedJSHeapSize: number } }).memory;
    const q = g.quests.tracked();
    const st = q ? g.gs.d.quests[q.id] : null;
    const rs = g.rs.stats;
    const lines = [
      `FPS        ${g.fps.toFixed(0)}  (${g.frameMs.toFixed(1)} ms)`,
      `Memory     ${mem ? (mem.usedJSHeapSize / 1048576).toFixed(0) + ' MB' : 'n/a'}`,
      `Draw calls ${rs.drawCalls}   tris ${(rs.triangles / 1000).toFixed(0)}k`,
      `GPU res    tex ${rs.textures}  geo ${rs.geometries}  prog ${rs.programs}`,
      `Mode       ${g.mode}${g.paused ? ' (paused)' : ''}${g.cinematics.active ? ' cine:' + g.cinematics.active : ''}`,
      `Scene      ${g.world.zone?.id ?? '-'}  colliders ${g.physics.staticCount}`,
      `Player     ${p ? p.position.toArray().map((v) => v.toFixed(1)).join(', ') : '-'}`,
      `Character  ${g.gs.d.character}  state ${p?.state ?? '-'}  hp ${p?.health.toFixed(0)}/${p?.stats.maxHealth}`,
      `Animation  ${p?.model.animator.currentAction() ?? p?.model.animator.stateName() ?? 'locomotion'}`,
      `Quest      ${q ? q.id + ' / ' + (q.stages[st?.stage ?? 0]?.id ?? '-') : '-'}`,
      `Enemies    ${g.world.enemies.filter((e) => e.alive).length} alive  ${g.world.aggroCount(p?.position ?? g.rs.camera.position)} aggro`,
      `Combat     ${g.combat.list.length} combatants  ${g.combat.activeProjectiles()} projectiles`,
      `Audio      ${g.audio.unlocked ? 'on' : 'locked'}  music ${g.audio.stats.mood}  amb ${g.audio.stats.amb}  voices ${g.audio.stats.voices}`,
      `Save       slot ${g.saves.activeSlot}  backend ${g.saves.backend.name}  ${g.saves.lastSaveAt ? ((performance.now() - g.saves.lastSaveAt) / 1000).toFixed(0) + 's ago' : 'never'}`,
      `Errors     ${Log.errorCount()}`,
    ];
    this.debugEl.textContent = lines.join('\n');
  }
}
