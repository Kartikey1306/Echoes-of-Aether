// Unified keyboard / mouse / gamepad input with named actions and remappable bindings.

export type Action =
  | 'moveF' | 'moveB' | 'moveL' | 'moveR'
  | 'jump' | 'dash' | 'light' | 'heavy' | 'bolt' | 'ability' | 'ultimate'
  | 'interact' | 'swap' | 'lockon' | 'pause' | 'inventory' | 'map' | 'journal' | 'skills'
  | 'quick1' | 'quick2' | 'quick3' | 'quick4' | 'quick5' | 'skip' | 'debug';

export interface Binding { kb: string[]; pad: string[] }
export type Bindings = Record<Action, Binding>;

export const ACTIONS: Action[] = [
  'moveF', 'moveB', 'moveL', 'moveR', 'jump', 'dash', 'light', 'heavy', 'bolt', 'ability', 'ultimate',
  'interact', 'swap', 'lockon', 'pause', 'inventory', 'map', 'journal', 'skills',
  'quick1', 'quick2', 'quick3', 'quick4', 'quick5', 'skip', 'debug',
];

/** Actions the player may rebind from the Controls settings page. */
export const REBINDABLE: Action[] = [
  'moveF', 'moveB', 'moveL', 'moveR', 'jump', 'dash', 'light', 'heavy', 'bolt', 'ability', 'ultimate',
  'interact', 'swap', 'lockon', 'inventory', 'map', 'journal', 'skills', 'quick1', 'quick2', 'quick3', 'quick4', 'quick5',
];

export function defaultBindings(): Bindings {
  return {
    moveF: { kb: ['KeyW', 'ArrowUp'], pad: [] },
    moveB: { kb: ['KeyS', 'ArrowDown'], pad: [] },
    moveL: { kb: ['KeyA', 'ArrowLeft'], pad: [] },
    moveR: { kb: ['KeyD', 'ArrowRight'], pad: [] },
    jump: { kb: ['Space'], pad: ['B0'] },
    dash: { kb: ['ShiftLeft'], pad: ['B1'] },
    light: { kb: ['Mouse0'], pad: ['B2'] },
    heavy: { kb: ['Mouse2'], pad: ['B3'] },
    bolt: { kb: ['KeyF'], pad: ['B6'] },
    ability: { kb: ['KeyQ'], pad: ['B4'] },
    ultimate: { kb: ['KeyX'], pad: ['B5'] },
    interact: { kb: ['KeyE'], pad: ['B0'] },
    swap: { kb: ['KeyT'], pad: ['B13'] },
    lockon: { kb: ['Mouse1', 'KeyR'], pad: ['B11'] },
    pause: { kb: ['Escape', 'KeyP'], pad: ['B9'] },
    inventory: { kb: ['KeyI', 'Tab'], pad: ['B14'] },
    map: { kb: ['KeyM'], pad: ['B8'] },
    journal: { kb: ['KeyJ'], pad: ['B12'] },
    skills: { kb: ['KeyK'], pad: ['B15'] },
    quick1: { kb: ['Digit1'], pad: [] },
    quick2: { kb: ['Digit2'], pad: [] },
    quick3: { kb: ['Digit3'], pad: [] },
    quick4: { kb: ['Digit4'], pad: [] },
    quick5: { kb: ['Digit5'], pad: [] },
    skip: { kb: ['Space', 'Enter'], pad: ['B0'] },
    debug: { kb: ['F1'], pad: [] },
  };
}

const PAD_NAMES: Record<string, string> = {
  B0: 'A', B1: 'B', B2: 'X', B3: 'Y', B4: 'LB', B5: 'RB', B6: 'LT', B7: 'RT', B8: 'View', B9: 'Menu',
  B10: 'LS', B11: 'RS', B12: 'D-Up', B13: 'D-Down', B14: 'D-Left', B15: 'D-Right', B16: 'Home',
};

export function bindingLabel(code: string): string {
  if (!code) return '—';
  if (PAD_NAMES[code]) return PAD_NAMES[code];
  if (code === 'Mouse0') return 'LMB';
  if (code === 'Mouse1') return 'MMB';
  if (code === 'Mouse2') return 'RMB';
  if (code.startsWith('Mouse')) return 'Mouse ' + code.slice(5);
  if (code.startsWith('Key')) return code.slice(3);
  if (code.startsWith('Digit')) return code.slice(5);
  const map: Record<string, string> = {
    Space: 'Space', ShiftLeft: 'L-Shift', ShiftRight: 'R-Shift', ControlLeft: 'L-Ctrl', AltLeft: 'L-Alt',
    Escape: 'Esc', Enter: 'Enter', Tab: 'Tab', ArrowUp: '↑', ArrowDown: '↓', ArrowLeft: '←', ArrowRight: '→',
    Backquote: '`', CapsLock: 'Caps',
  };
  return map[code] ?? code;
}

const GAME_KEYS = new Set(['Space', 'Tab', 'F1', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Quote', 'Slash']);

export class Input {
  bindings: Bindings = defaultBindings();
  sensitivity = 1;
  aimSensitivity = 0.6;
  padLookSpeed = 1;
  invertY = false;
  /** When false, gameplay actions read as idle (menus, dialogue, cinematics). */
  gameplayEnabled = true;
  lastDevice: 'kbm' | 'pad' = 'kbm';

  readonly move = { x: 0, y: 0 };
  readonly look = { x: 0, y: 0 };
  aiming = false;

  /** Physically held right now (event-driven). */
  private down = new Set<string>();
  /** Held state sampled at the previous update. */
  private prevDown = new Set<string>();
  /** Held state sampled at this update (includes taps that were released within the frame). */
  private curDown = new Set<string>();
  /** Codes that went down since the last update (event-driven accumulator). */
  private frameDown = new Set<string>();
  /** Codes that went down this frame. */
  private pressedNow = new Set<string>();
  private mouseDX = 0;
  private mouseDY = 0;
  private wheel = 0;
  private padState: { buttons: number[]; axes: number[] } = { buttons: [], axes: [] };
  private captureCb: ((code: string) => void) | null = null;
  private holdTimes = new Map<Action, number>();
  locked = false;
  onUnlock: (() => void) | null = null;
  private target: HTMLElement;

  constructor(target: HTMLElement) {
    this.target = target;
    window.addEventListener('keydown', this.onKeyDown, { capture: true });
    window.addEventListener('keyup', this.onKeyUp, { capture: true });
    window.addEventListener('mousedown', this.onMouseDown);
    window.addEventListener('mouseup', this.onMouseUp);
    window.addEventListener('mousemove', this.onMouseMove);
    window.addEventListener('wheel', this.onWheel, { passive: true });
    window.addEventListener('blur', () => this.down.clear());
    target.addEventListener('contextmenu', (e) => e.preventDefault());
    document.addEventListener('pointerlockchange', () => {
      const was = this.locked;
      this.locked = document.pointerLockElement === this.target;
      if (was && !this.locked) this.onUnlock?.();
    });
  }

  requestLock() {
    if (this.locked || this.lastDevice === 'pad') return;
    try {
      const p = this.target.requestPointerLock() as unknown as Promise<void> | undefined;
      if (p && typeof p.catch === 'function') p.catch(() => undefined);
    } catch {
      /* not allowed without gesture; ignored */
    }
  }

  releaseLock() {
    if (document.pointerLockElement) document.exitPointerLock();
  }

  /** Next physical input is reported to cb instead of being processed (used by the rebinding UI). */
  captureNext(cb: (code: string) => void) {
    this.captureCb = cb;
  }
  cancelCapture() {
    this.captureCb = null;
  }
  get capturing() {
    return !!this.captureCb;
  }

  private onKeyDown = (e: KeyboardEvent) => {
    if (this.captureCb) {
      e.preventDefault();
      e.stopPropagation();
      const cb = this.captureCb;
      this.captureCb = null;
      cb(e.code);
      return;
    }
    const tag = (e.target as HTMLElement | null)?.tagName;
    if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') return;
    this.lastDevice = 'kbm';
    if (GAME_KEYS.has(e.code) || this.isBoundKey(e.code)) {
      // Keep the page from scrolling / focusing browser chrome on game keys.
      if (e.code !== 'Escape') e.preventDefault();
    }
    if (!e.repeat) {
      this.down.add(e.code);
      this.frameDown.add(e.code);
    }
  };
  private onKeyUp = (e: KeyboardEvent) => {
    this.down.delete(e.code);
  };
  private onMouseDown = (e: MouseEvent) => {
    const code = 'Mouse' + e.button;
    if (this.captureCb) {
      e.preventDefault();
      const cb = this.captureCb;
      this.captureCb = null;
      cb(code);
      return;
    }
    this.lastDevice = 'kbm';
    if (e.target === this.target || this.locked) {
      this.down.add(code);
      this.frameDown.add(code);
    }
  };
  private onMouseUp = (e: MouseEvent) => {
    this.down.delete('Mouse' + e.button);
  };
  private onMouseMove = (e: MouseEvent) => {
    if (!this.locked) return;
    // Clamp spikes some browsers report on lock changes.
    this.mouseDX += Math.max(-250, Math.min(250, e.movementX));
    this.mouseDY += Math.max(-250, Math.min(250, e.movementY));
  };
  private onWheel = (e: WheelEvent) => {
    this.wheel += Math.sign(e.deltaY);
  };

  private isBoundKey(code: string) {
    for (const a of ACTIONS) if (this.bindings[a].kb.includes(code)) return true;
    return false;
  }

  /** Call once at the start of every frame. */
  update(dt: number) {
    this.prevDown = this.curDown;
    this.pressedNow = this.frameDown;
    this.frameDown = new Set();
    this.pollPad();
    this.curDown = new Set(this.down);
    for (const c of this.pressedNow) this.curDown.add(c);

    // Movement axes
    let mx = 0, my = 0;
    if (this.raw('moveR')) mx += 1;
    if (this.raw('moveL')) mx -= 1;
    if (this.raw('moveF')) my += 1;
    if (this.raw('moveB')) my -= 1;
    const ax = this.padState.axes;
    if (ax.length >= 2) {
      const [sx, sy] = deadzone(ax[0], ax[1], 0.18);
      if (sx !== 0 || sy !== 0) {
        mx += sx;
        my -= sy;
      }
    }
    const len = Math.hypot(mx, my);
    if (len > 1) { mx /= len; my /= len; }
    this.move.x = this.gameplayEnabled ? mx : 0;
    this.move.y = this.gameplayEnabled ? my : 0;

    // Look axes (radians this frame)
    const sens = (this.aiming ? this.aimSensitivity : this.sensitivity) * 0.0022;
    let lx = this.mouseDX * sens;
    let ly = this.mouseDY * sens;
    if (ax.length >= 4) {
      const [rx, ry] = deadzone(ax[2], ax[3], 0.15);
      const padRate = 2.6 * this.padLookSpeed * (this.aiming ? this.aimSensitivity : this.sensitivity) * dt;
      lx += Math.sign(rx) * rx * rx * padRate;
      ly += Math.sign(ry) * ry * ry * padRate * 0.75;
    }
    if (this.invertY) ly = -ly;
    this.look.x = this.gameplayEnabled ? lx : 0;
    this.look.y = this.gameplayEnabled ? ly : 0;
    this.mouseDX = 0;
    this.mouseDY = 0;

    for (const a of ACTIONS) {
      if (this.raw(a)) this.holdTimes.set(a, (this.holdTimes.get(a) ?? 0) + dt);
      else this.holdTimes.set(a, 0);
    }
  }

  private pollPad() {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    let pad: Gamepad | null = null;
    for (const p of pads) if (p && p.connected) { pad = p; break; }
    const prevButtons = this.padState.buttons;
    if (!pad) {
      this.padState = { buttons: [], axes: [] };
      for (let i = 0; i < prevButtons.length; i++) this.down.delete('B' + i);
      return;
    }
    const buttons = pad.buttons.map((b) => (b.pressed || b.value > 0.5 ? 1 : 0));
    const axes = [...pad.axes];
    let activity = false;
    for (let i = 0; i < buttons.length; i++) {
      const code = 'B' + i;
      if (buttons[i] && !prevButtons[i]) {
        activity = true;
        if (this.captureCb) {
          const cb = this.captureCb;
          this.captureCb = null;
          cb(code);
          continue;
        }
        this.down.add(code);
        this.pressedNow.add(code);
      } else if (!buttons[i]) this.down.delete(code);
    }
    if (axes.some((v) => Math.abs(v) > 0.4)) activity = true;
    if (activity) {
      this.lastDevice = 'pad';
      if (this.locked) this.releaseLock();
    }
    this.padState = { buttons, axes };
  }

  private raw(a: Action): boolean {
    const b = this.bindings[a];
    for (const c of b.kb) if (this.curDown.has(c)) return true;
    for (const c of b.pad) if (this.curDown.has(c)) return true;
    return false;
  }

  private rawPressed(a: Action): boolean {
    const b = this.bindings[a];
    for (const c of b.kb) if (this.pressedNow.has(c)) return true;
    for (const c of b.pad) if (this.pressedNow.has(c)) return true;
    return false;
  }

  /** True while held (gameplay-gated). */
  held(a: Action): boolean {
    if (!this.gameplayEnabled && !UI_ACTIONS.has(a)) return false;
    return this.raw(a);
  }
  /** True on the frame the action was pressed (gameplay-gated). */
  pressed(a: Action): boolean {
    if (!this.gameplayEnabled && !UI_ACTIONS.has(a)) return false;
    return this.rawPressed(a);
  }
  /** True on the frame the action was released (gameplay-gated). */
  released(a: Action): boolean {
    if (!this.gameplayEnabled && !UI_ACTIONS.has(a)) return false;
    const b = this.bindings[a];
    const was = [...b.kb, ...b.pad].some((c) => this.prevDown.has(c));
    return was && !this.raw(a);
  }
  holdTime(a: Action): number {
    return this.holdTimes.get(a) ?? 0;
  }
  /** Ungated press check for UI code. */
  uiPressed(a: Action): boolean {
    return this.rawPressed(a);
  }
  /** Raw physical code press check (UI navigation). */
  codePressed(code: string): boolean {
    return this.pressedNow.has(code);
  }
  codeHeld(code: string): boolean {
    return this.curDown.has(code);
  }
  consumeWheel(): number {
    const w = this.wheel;
    this.wheel = 0;
    return w;
  }
  clearAll() {
    this.down.clear();
    this.prevDown.clear();
    this.curDown.clear();
    this.pressedNow.clear();
    this.frameDown.clear();
    this.mouseDX = this.mouseDY = 0;
  }
  padConnected(): boolean {
    return this.padState.buttons.length > 0;
  }
  rumble(intensity: number, ms: number) {
    const pads = navigator.getGamepads ? navigator.getGamepads() : [];
    for (const p of pads) {
      const act = (p as unknown as { vibrationActuator?: { playEffect?: (t: string, o: object) => Promise<unknown> } } | null)?.vibrationActuator;
      act?.playEffect?.('dual-rumble', { duration: ms, strongMagnitude: intensity, weakMagnitude: intensity * 0.6 })?.catch?.(() => undefined);
    }
  }
  /** Human-readable primary binding for prompts, matching the last-used device. */
  label(a: Action): string {
    const b = this.bindings[a];
    if (this.lastDevice === 'pad' && b.pad.length) return bindingLabel(b.pad[0]);
    return bindingLabel(b.kb[0] ?? b.pad[0] ?? '');
  }
}

const UI_ACTIONS = new Set<Action>(['pause', 'debug', 'skip', 'inventory', 'map', 'journal', 'skills']);

function deadzone(x: number, y: number, dz: number): [number, number] {
  const m = Math.hypot(x, y);
  if (m < dz) return [0, 0];
  const s = Math.min(1, (m - dz) / (1 - dz)) / m;
  return [x * s, y * s];
}
