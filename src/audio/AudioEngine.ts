import * as THREE from 'three';
import { Log } from '../core/Log';

// Procedural audio: mixer buses, synthesized SFX (positional), generative music, ambience beds.
// MASTER -> MUSIC / SFX / VOICE / UI / AMBIENCE

export type Bus = 'master' | 'music' | 'sfx' | 'voice' | 'ui' | 'ambience';
export type MusicMood = 'menu' | 'explore' | 'combat' | 'boss' | 'sidequest' | 'tension' | 'ending' | 'silence';
export type AmbienceId = 'rain_city' | 'metro_drip' | 'facility_hum' | 'vault_hum' | 'wind_roof' | 'core_drone' | 'none';

type Recipe = (a: AudioEngine, out: AudioNode, t: number, vol: number) => number; // returns duration

const UI_SOUNDS = new Set(['ui_hover', 'ui_click', 'ui_back', 'quest_accept', 'quest_complete', 'save', 'load', 'error_ui', 'checkpoint', 'item', 'lore', 'toast']);

export class AudioEngine {
  ctx: AudioContext | null = null;
  private buses: Partial<Record<Bus, GainNode>> = {};
  private volumes: Record<Bus, number> = { master: 0.85, music: 0.6, sfx: 0.8, voice: 0.9, ui: 0.6, ambience: 0.7 };
  private noise: AudioBuffer | null = null;
  private pink: AudioBuffer | null = null;
  private brown: AudioBuffer | null = null;
  private listenerPos = new THREE.Vector3();
  private active = new Map<string, number>();
  private music: MusicPlayer | null = null;
  private amb: Ambience | null = null;
  private wantMood: MusicMood = 'silence';
  private wantAmb: AmbienceId = 'none';
  private lastPlay = new Map<string, number>();
  unlocked = false;
  /** Stats for the debug overlay. */
  stats = { voices: 0, mood: 'silence' as string, amb: 'none' as string, played: 0 };

  /** Must be called from a user gesture (browser autoplay policy). */
  unlock() {
    if (this.ctx) {
      if (this.ctx.state === 'suspended') void this.ctx.resume();
      return;
    }
    try {
      this.ctx = new AudioContext({ latencyHint: 'interactive' });
    } catch (e) {
      Log.warn('audio', 'WebAudio unavailable', e);
      return;
    }
    const c = this.ctx;
    const comp = c.createDynamicsCompressor();
    comp.threshold.value = -14;
    comp.knee.value = 10;
    comp.ratio.value = 4;
    comp.attack.value = 0.004;
    comp.release.value = 0.2;
    comp.connect(c.destination);
    const master = c.createGain();
    master.connect(comp);
    this.buses.master = master;
    for (const b of ['music', 'sfx', 'voice', 'ui', 'ambience'] as Bus[]) {
      const g = c.createGain();
      g.connect(master);
      this.buses[b] = g;
    }
    this.applyVolumes();
    this.noise = this.makeNoise('white');
    this.pink = this.makeNoise('pink');
    this.brown = this.makeNoise('brown');
    this.music = new MusicPlayer(this, this.buses.music!);
    this.amb = new Ambience(this, this.buses.ambience!);
    this.unlocked = true;
    this.setMusic(this.wantMood, true);
    this.setAmbience(this.wantAmb);
    Log.info('audio', 'unlocked', c.sampleRate);
  }

  bus(b: Bus) {
    return this.buses[b]!;
  }

  setVolume(b: Bus, v: number) {
    this.volumes[b] = v;
    this.applyVolumes();
  }

  setVolumes(v: Partial<Record<Bus, number>>) {
    Object.assign(this.volumes, v);
    this.applyVolumes();
  }

  getVolume(b: Bus) {
    return this.volumes[b];
  }

  private applyVolumes() {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    for (const [b, g] of Object.entries(this.buses) as [Bus, GainNode][]) {
      const v = this.volumes[b];
      g.gain.setTargetAtTime(v * v, t, 0.03);
    }
  }

  /** Duck music/ambience under dialogue. */
  duck(on: boolean) {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    const m = this.volumes.music, a = this.volumes.ambience;
    this.buses.music!.gain.setTargetAtTime(m * m * (on ? 0.45 : 1), t, 0.25);
    this.buses.ambience!.gain.setTargetAtTime(a * a * (on ? 0.6 : 1), t, 0.25);
  }

  private makeNoise(kind: 'white' | 'pink' | 'brown'): AudioBuffer {
    const c = this.ctx!;
    const len = c.sampleRate * 2;
    const buf = c.createBuffer(1, len, c.sampleRate);
    const d = buf.getChannelData(0);
    let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0, last = 0;
    for (let i = 0; i < len; i++) {
      const w = Math.random() * 2 - 1;
      if (kind === 'white') d[i] = w;
      else if (kind === 'pink') {
        b0 = 0.99886 * b0 + w * 0.0555179; b1 = 0.99332 * b1 + w * 0.0750759; b2 = 0.969 * b2 + w * 0.153852;
        b3 = 0.8665 * b3 + w * 0.3104856; b4 = 0.55 * b4 + w * 0.5329522; b5 = -0.7616 * b5 - w * 0.016898;
        d[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11;
        b6 = w * 0.115926;
      } else {
        last = (last + 0.02 * w) / 1.02;
        d[i] = last * 3.5;
      }
    }
    return buf;
  }

  noiseSrc(kind: 'white' | 'pink' | 'brown' = 'white', loop = false): AudioBufferSourceNode {
    const s = this.ctx!.createBufferSource();
    s.buffer = kind === 'white' ? this.noise! : kind === 'pink' ? this.pink! : this.brown!;
    s.loop = loop;
    if (!loop) s.loopStart = 0;
    return s;
  }

  setListener(pos: THREE.Vector3, forward: THREE.Vector3, up: THREE.Vector3) {
    this.listenerPos.copy(pos);
    const c = this.ctx;
    if (!c) return;
    const l = c.listener;
    const t = c.currentTime;
    if (l.positionX) {
      l.positionX.setTargetAtTime(pos.x, t, 0.02);
      l.positionY.setTargetAtTime(pos.y, t, 0.02);
      l.positionZ.setTargetAtTime(pos.z, t, 0.02);
      l.forwardX.setTargetAtTime(forward.x, t, 0.02);
      l.forwardY.setTargetAtTime(forward.y, t, 0.02);
      l.forwardZ.setTargetAtTime(forward.z, t, 0.02);
      l.upX.setTargetAtTime(up.x, t, 0.02);
      l.upY.setTargetAtTime(up.y, t, 0.02);
      l.upZ.setTargetAtTime(up.z, t, 0.02);
    } else {
      (l as unknown as { setPosition: (x: number, y: number, z: number) => void }).setPosition(pos.x, pos.y, pos.z);
    }
  }

  /** Play a synthesized sound. Positional when `pos` is given. */
  play(id: string, pos?: THREE.Vector3, vol = 1) {
    const c = this.ctx;
    if (!c || c.state !== 'running') return;
    const recipe = RECIPES[id];
    if (!recipe) {
      Log.warn('audio', 'unknown sfx', id);
      return;
    }
    // Rate-limit identical sounds and cap concurrency.
    const now = c.currentTime;
    const minGap = id === 'footstep' ? 0.06 : id.startsWith('ui_') ? 0.03 : 0.025;
    if (now - (this.lastPlay.get(id) ?? -1) < minGap) return;
    const count = this.active.get(id) ?? 0;
    if (count >= (id === 'footstep' || id === 'hit' ? 6 : 4)) return;
    if (pos && pos.distanceTo(this.listenerPos) > 70) return;
    this.lastPlay.set(id, now);
    const bus = UI_SOUNDS.has(id) ? this.buses.ui! : this.buses.sfx!;
    let out: AudioNode = bus;
    let panner: PannerNode | null = null;
    if (pos) {
      panner = c.createPanner();
      panner.panningModel = 'equalpower';
      panner.distanceModel = 'inverse';
      panner.refDistance = 3;
      panner.rolloffFactor = 1.1;
      panner.maxDistance = 70;
      panner.positionX.value = pos.x;
      panner.positionY.value = pos.y;
      panner.positionZ.value = pos.z;
      panner.connect(bus);
      out = panner;
    }
    const dur = recipe(this, out, now + 0.005, vol);
    this.active.set(id, count + 1);
    this.stats.voices++;
    this.stats.played++;
    setTimeout(() => {
      this.active.set(id, Math.max(0, (this.active.get(id) ?? 1) - 1));
      this.stats.voices = Math.max(0, this.stats.voices - 1);
      panner?.disconnect();
    }, (dur + 0.2) * 1000);
  }

  setMusic(mood: MusicMood, immediate = false) {
    this.wantMood = mood;
    this.stats.mood = mood;
    this.music?.setMood(mood, immediate);
  }

  setAmbience(id: AmbienceId) {
    this.wantAmb = id;
    this.stats.amb = id;
    this.amb?.set(id);
  }

  thunder(intensity: number, delay: number) {
    if (!this.ctx) return;
    setTimeout(() => this.amb?.thunder(intensity), delay * 1000);
  }

  update() {
    this.music?.tick();
  }

  // ---- Synthesis helpers used by recipes
  env(g: GainNode, t: number, a: number, peak: number, d: number, sustain = 0, r = 0.05) {
    g.gain.setValueAtTime(0.0001, t);
    g.gain.linearRampToValueAtTime(peak, t + a);
    g.gain.exponentialRampToValueAtTime(Math.max(0.0001, sustain || peak * 0.001), t + a + d);
    if (sustain) g.gain.exponentialRampToValueAtTime(0.0001, t + a + d + r);
  }
  osc(type: OscillatorType, f: number, t: number, dur: number, out: AudioNode, peak: number, a = 0.005, f2?: number) {
    const c = this.ctx!;
    const o = c.createOscillator();
    o.type = type;
    o.frequency.setValueAtTime(f, t);
    if (f2 !== undefined) o.frequency.exponentialRampToValueAtTime(Math.max(1, f2), t + dur);
    const g = c.createGain();
    this.env(g, t, a, peak, dur);
    o.connect(g).connect(out);
    o.start(t);
    o.stop(t + a + dur + 0.05);
    return o;
  }
  noiseBurst(t: number, dur: number, out: AudioNode, peak: number, filter: BiquadFilterType, f: number, f2?: number, q = 1, kind: 'white' | 'pink' | 'brown' = 'white', a = 0.003) {
    const c = this.ctx!;
    const s = this.noiseSrc(kind);
    const bq = c.createBiquadFilter();
    bq.type = filter;
    bq.frequency.setValueAtTime(f, t);
    if (f2 !== undefined) bq.frequency.exponentialRampToValueAtTime(Math.max(20, f2), t + dur);
    bq.Q.value = q;
    const g = c.createGain();
    this.env(g, t, a, peak, dur);
    s.connect(bq).connect(g).connect(out);
    s.start(t, Math.random() * Math.max(0, 1.9 - dur - a));
    s.stop(t + a + dur + 0.05);
  }
}

const rnd = (a: number, b: number) => a + Math.random() * (b - a);

// ---------------------------------------------------------------------------- SFX recipes
const RECIPES: Record<string, Recipe> = {
  footstep: (a, o, t, v) => { a.noiseBurst(t, 0.07, o, 0.18 * v, 'bandpass', rnd(500, 900), 200, 1.2, 'pink'); a.noiseBurst(t + 0.01, 0.1, o, 0.06 * v, 'highpass', 3000, 6000, 0.7); return 0.12; },
  land: (a, o, t, v) => { a.osc('sine', 90, t, 0.18, o, 0.4 * v, 0.002, 40); a.noiseBurst(t, 0.18, o, 0.25 * v, 'lowpass', 1200, 200, 1, 'pink'); return 0.2; },
  jump: (a, o, t, v) => { a.noiseBurst(t, 0.18, o, 0.12 * v, 'bandpass', 600, 1800, 1.5, 'pink'); return 0.2; },
  swing_light: (a, o, t, v) => { a.noiseBurst(t, 0.16, o, 0.22 * v, 'bandpass', 1400, 4200, 2.2, 'white', 0.02); a.osc('sine', 700, t, 0.12, o, 0.04 * v, 0.01, 1300); return 0.2; },
  swing_heavy: (a, o, t, v) => { a.noiseBurst(t, 0.22, o, 0.3 * v, 'bandpass', 700, 2600, 1.6, 'pink', 0.03); a.osc('sawtooth', 160, t, 0.2, o, 0.05 * v, 0.02, 420); return 0.25; },
  hit: (a, o, t, v) => { a.noiseBurst(t, 0.09, o, 0.45 * v, 'bandpass', 2400, 800, 1.2); a.osc('sine', 140, t, 0.12, o, 0.4 * v, 0.002, 60); a.osc('triangle', rnd(900, 1300), t, 0.15, o, 0.08 * v, 0.001, 600); return 0.18; },
  hit_heavy: (a, o, t, v) => { a.noiseBurst(t, 0.2, o, 0.6 * v, 'lowpass', 3000, 300, 1, 'pink'); a.osc('sine', 110, t, 0.3, o, 0.7 * v, 0.002, 35); a.osc('square', 420, t, 0.12, o, 0.06 * v, 0.001, 140); return 0.32; },
  enemy_hit_metal: (a, o, t, v) => { for (const f of [820, 1370, 2210]) a.osc('sine', f * rnd(0.95, 1.05), t, 0.25, o, 0.07 * v, 0.001); a.noiseBurst(t, 0.05, o, 0.2 * v, 'highpass', 2500); return 0.28; },
  enemy_hit_player: (a, o, t, v) => { a.osc('sine', 80, t, 0.2, o, 0.5 * v, 0.002, 40); a.noiseBurst(t, 0.12, o, 0.3 * v, 'lowpass', 1800, 300, 1, 'pink'); return 0.22; },
  shield_hit: (a, o, t, v) => { a.osc('sawtooth', 1600, t, 0.12, o, 0.06 * v, 0.001, 700); a.osc('sine', 2400, t, 0.18, o, 0.08 * v, 0.001, 1800); return 0.2; },
  shield_break: (a, o, t, v) => { a.noiseBurst(t, 0.4, o, 0.3 * v, 'highpass', 3000, 9000, 0.8); a.osc('sawtooth', 900, t, 0.4, o, 0.1 * v, 0.002, 120); return 0.45; },
  player_hurt: (a, o, t, v) => { a.osc('sine', 120, t, 0.25, o, 0.45 * v, 0.002, 55); a.noiseBurst(t, 0.15, o, 0.25 * v, 'lowpass', 900, 200, 1, 'brown'); return 0.27; },
  player_death: (a, o, t, v) => { a.osc('sawtooth', 220, t, 1.4, o, 0.12 * v, 0.02, 40); a.osc('sine', 110, t, 1.6, o, 0.3 * v, 0.02, 30); a.noiseBurst(t, 1.2, o, 0.15 * v, 'lowpass', 2000, 100, 1, 'pink', 0.05); return 1.7; },
  dash: (a, o, t, v) => { a.noiseBurst(t, 0.22, o, 0.3 * v, 'bandpass', 400, 3000, 1.2, 'pink', 0.01); a.osc('sine', 300, t, 0.2, o, 0.1 * v, 0.005, 1200); a.osc('triangle', 1200, t + 0.03, 0.15, o, 0.05 * v, 0.005, 2400); return 0.26; },
  step: (a, o, t, v) => { a.noiseBurst(t, 0.16, o, 0.25 * v, 'bandpass', 900, 3500, 1.4, 'pink', 0.01); a.osc('sine', 600, t, 0.14, o, 0.08 * v, 0.005, 1600); return 0.2; },
  pulse: (a, o, t, v) => { a.osc('sine', 70, t, 0.8, o, 0.9 * v, 0.003, 28); a.noiseBurst(t, 0.6, o, 0.5 * v, 'lowpass', 2400, 120, 1, 'pink'); a.osc('sawtooth', 220, t, 0.5, o, 0.08 * v, 0.003, 60); for (const f of [880, 1320, 1760]) a.osc('sine', f, t + 0.05, 0.9, o, 0.03 * v, 0.05, f * 1.5); return 1; },
  echo: (a, o, t, v) => { for (const [i, f] of [523, 659, 784, 1046].entries()) a.osc('sine', f, t + i * 0.06, 1.4, o, 0.07 * v, 0.2); a.noiseBurst(t, 1.2, o, 0.06 * v, 'bandpass', 3000, 6000, 3, 'white', 0.5); return 1.6; },
  charge: (a, o, t, v) => { a.osc('sawtooth', 120, t, 0.35, o, 0.06 * v, 0.05, 520); a.osc('sine', 240, t, 0.35, o, 0.08 * v, 0.05, 1040); return 0.4; },
  ult_charge: (a, o, t, v) => { a.osc('sawtooth', 80, t, 0.9, o, 0.12 * v, 0.1, 640); a.osc('sine', 160, t, 0.9, o, 0.12 * v, 0.1, 1280); a.noiseBurst(t, 0.9, o, 0.1 * v, 'bandpass', 500, 5000, 2, 'pink', 0.3); return 1; },
  ult_impact: (a, o, t, v) => { a.osc('sine', 55, t, 1.6, o, 1.0 * v, 0.003, 22); a.noiseBurst(t, 1.4, o, 0.7 * v, 'lowpass', 5000, 80, 0.8, 'pink'); a.osc('sawtooth', 330, t, 0.8, o, 0.1 * v, 0.003, 50); for (const f of [660, 990, 1320, 1980]) a.osc('sine', f, t + 0.1, 1.8, o, 0.04 * v, 0.1); return 1.9; },
  bolt: (a, o, t, v) => { a.osc('square', 1400, t, 0.12, o, 0.08 * v, 0.001, 300); a.osc('sine', 2200, t, 0.08, o, 0.08 * v, 0.001, 800); a.noiseBurst(t, 0.05, o, 0.1 * v, 'highpass', 4000); return 0.15; },
  drone_shot: (a, o, t, v) => { a.osc('sawtooth', 900, t, 0.16, o, 0.08 * v, 0.001, 180); a.osc('square', 600, t, 0.1, o, 0.04 * v, 0.001, 200); return 0.18; },
  drone_charge: (a, o, t, v) => { a.osc('sine', 600, t, 0.5, o, 0.07 * v, 0.02, 1800); return 0.55; },
  drone_dive: (a, o, t, v) => { a.osc('sawtooth', 300, t, 0.8, o, 0.05 * v, 0.1, 900); a.noiseBurst(t, 0.8, o, 0.08 * v, 'bandpass', 800, 2400, 2, 'pink', 0.2); return 0.9; },
  drone_death: (a, o, t, v) => { a.osc('sawtooth', 900, t, 1.2, o, 0.08 * v, 0.01, 80); a.noiseBurst(t, 0.6, o, 0.15 * v, 'highpass', 2000, 500, 1); return 1.3; },
  explosion: (a, o, t, v) => { a.noiseBurst(t, 1.0, o, 0.8 * v, 'lowpass', 4000, 90, 0.7, 'pink'); a.osc('sine', 60, t, 0.9, o, 0.8 * v, 0.002, 25); a.noiseBurst(t + 0.05, 0.6, o, 0.15 * v, 'highpass', 3000, 1000, 0.7); return 1.1; },
  slam: (a, o, t, v) => { a.osc('sine', 65, t, 0.5, o, 0.9 * v, 0.002, 28); a.noiseBurst(t, 0.45, o, 0.5 * v, 'lowpass', 1600, 80, 1, 'brown'); a.noiseBurst(t, 0.2, o, 0.2 * v, 'bandpass', 2000, 600, 1); return 0.55; },
  sentinel_death: (a, o, t, v) => { a.osc('sawtooth', 160, t, 1.2, o, 0.1 * v, 0.01, 40); for (const f of [420, 610]) a.osc('square', f, t, 0.5, o, 0.03 * v, 0.01, f * 0.4); return 1.3; },
  enemy_telegraph: (a, o, t, v) => { a.osc('square', 520, t, 0.08, o, 0.05 * v, 0.002); a.osc('square', 520, t + 0.12, 0.08, o, 0.05 * v, 0.002); a.osc('sawtooth', 110, t, 0.5, o, 0.06 * v, 0.1, 220); return 0.55; },
  enemy_stagger: (a, o, t, v) => { for (const f of [300, 470, 690]) a.osc('triangle', f, t, 0.5, o, 0.08 * v, 0.002, f * 0.7); return 0.55; },
  shield_block: (a, o, t, v) => { a.osc('sine', 1800, t, 0.25, o, 0.08 * v, 0.001, 1200); a.osc('triangle', 900, t, 0.2, o, 0.06 * v, 0.001); a.noiseBurst(t, 0.06, o, 0.15 * v, 'highpass', 5000); return 0.28; },
  pickup: (a, o, t, v) => { for (const [i, f] of [880, 1108, 1318, 1760].entries()) a.osc('sine', f, t + i * 0.045, 0.3, o, 0.07 * v, 0.004); return 0.5; },
  powerup_shard: (a, o, t, v) => { for (const [i, f] of [523, 784, 1046, 1568].entries()) a.osc('triangle', f, t + i * 0.05, 0.6, o, 0.07 * v, 0.01); a.osc('sawtooth', 130, t, 0.5, o, 0.05 * v, 0.02, 520); return 0.8; },
  powerup_phase: (a, o, t, v) => { for (const [i, f] of [466, 698, 932].entries()) a.osc('sine', f, t + i * 0.07, 0.7, o, 0.08 * v, 0.02, f * 1.5); return 0.9; },
  powerup_overcharge: (a, o, t, v) => { a.osc('sawtooth', 220, t, 0.5, o, 0.08 * v, 0.01, 880); a.osc('square', 440, t + 0.1, 0.4, o, 0.04 * v, 0.01, 1760); return 0.6; },
  powerup_shield: (a, o, t, v) => { for (const f of [392, 494, 587]) a.osc('sine', f, t, 0.8, o, 0.07 * v, 0.06); return 0.9; },
  powerup_echo: (a, o, t, v) => { for (const [i, f] of [1046, 784, 1318, 988].entries()) a.osc('sine', f, t + i * 0.08, 0.9, o, 0.05 * v, 0.05); return 1.2; },
  reveal: (a, o, t, v) => { for (const [i, f] of [659, 880, 1318].entries()) a.osc('sine', f, t + i * 0.09, 1.0, o, 0.06 * v, 0.08); return 1.2; },
  interact: (a, o, t, v) => { a.osc('sine', 880, t, 0.08, o, 0.08 * v, 0.003); a.osc('sine', 1320, t + 0.07, 0.1, o, 0.06 * v, 0.003); return 0.2; },
  terminal: (a, o, t, v) => { for (let i = 0; i < 6; i++) a.osc('square', rnd(900, 2400), t + i * 0.05, 0.03, o, 0.03 * v, 0.001); return 0.35; },
  door: (a, o, t, v) => { a.osc('sawtooth', 70, t, 1.2, o, 0.1 * v, 0.1, 50); a.noiseBurst(t, 1.2, o, 0.12 * v, 'bandpass', 300, 200, 2, 'brown', 0.2); a.osc('sine', 40, t + 1.1, 0.3, o, 0.3 * v, 0.002); return 1.5; },
  respawn: (a, o, t, v) => { for (const [i, f] of [392, 523, 659].entries()) a.osc('sine', f, t + i * 0.1, 0.8, o, 0.08 * v, 0.05); return 1.1; },
  error: (a, o, t, v) => { a.osc('square', 140, t, 0.1, o, 0.06 * v, 0.002); a.osc('square', 110, t + 0.11, 0.12, o, 0.06 * v, 0.002); return 0.25; },
  metal_impact: (a, o, t, v) => { for (const f of [240, 410, 790]) a.osc('triangle', f * rnd(0.9, 1.1), t, 0.6, o, 0.08 * v, 0.001); return 0.6; },
  cinematic_whoosh: (a, o, t, v) => { a.noiseBurst(t, 1.4, o, 0.25 * v, 'bandpass', 200, 2000, 1, 'pink', 0.7); a.osc('sine', 50, t, 1.6, o, 0.2 * v, 0.5, 35); return 1.8; },
  ui_hover: (a, o, t, v) => { a.osc('sine', 1800, t, 0.03, o, 0.04 * v, 0.001); return 0.05; },
  ui_click: (a, o, t, v) => { a.osc('sine', 1200, t, 0.05, o, 0.08 * v, 0.001); a.osc('sine', 1800, t + 0.03, 0.06, o, 0.05 * v, 0.001); return 0.1; },
  ui_back: (a, o, t, v) => { a.osc('sine', 1100, t, 0.05, o, 0.07 * v, 0.001); a.osc('sine', 700, t + 0.04, 0.07, o, 0.06 * v, 0.001); return 0.12; },
  error_ui: (a, o, t, v) => { a.osc('square', 180, t, 0.12, o, 0.05 * v, 0.002); return 0.15; },
  quest_accept: (a, o, t, v) => { a.osc('triangle', 587, t, 0.25, o, 0.1 * v, 0.005); a.osc('triangle', 880, t + 0.12, 0.4, o, 0.1 * v, 0.005); return 0.6; },
  quest_complete: (a, o, t, v) => { for (const [i, f] of [523, 659, 784, 1046, 1318].entries()) a.osc('triangle', f, t + i * 0.08, 0.7, o, 0.08 * v, 0.005); a.osc('sine', 262, t, 1.2, o, 0.08 * v, 0.05); return 1.4; },
  save: (a, o, t, v) => { a.osc('sine', 660, t, 0.15, o, 0.07 * v, 0.005); a.osc('sine', 990, t + 0.1, 0.25, o, 0.07 * v, 0.005); return 0.4; },
  load: (a, o, t, v) => { a.osc('sine', 990, t, 0.15, o, 0.06 * v, 0.005); a.osc('sine', 660, t + 0.1, 0.25, o, 0.06 * v, 0.005); return 0.4; },
  checkpoint: (a, o, t, v) => { a.osc('sine', 784, t, 0.3, o, 0.06 * v, 0.01); a.osc('sine', 1175, t + 0.1, 0.4, o, 0.05 * v, 0.01); return 0.55; },
  item: (a, o, t, v) => { a.osc('triangle', 1046, t, 0.2, o, 0.07 * v, 0.003); a.osc('triangle', 1568, t + 0.06, 0.3, o, 0.06 * v, 0.003); return 0.4; },
  lore: (a, o, t, v) => { a.osc('sine', 440, t, 0.6, o, 0.06 * v, 0.05); a.osc('sine', 554, t + 0.15, 0.6, o, 0.05 * v, 0.05); return 0.8; },
  toast: (a, o, t, v) => { a.osc('sine', 1318, t, 0.08, o, 0.04 * v, 0.003); return 0.1; },
};

export const SFX_IDS = Object.keys(RECIPES);

// ---------------------------------------------------------------------------- Music
interface MoodDef { bpm: number; chords: number[][]; pad: number; bass: number; arp: number; perc: number; pulse: number; root: number; bright: number }

const MOODS: Record<Exclude<MusicMood, 'silence'>, MoodDef> = {
  // Chords as semitone offsets from root (MIDI). Layers are 0..1 levels.
  menu: { bpm: 64, root: 50, chords: [[0, 3, 7, 10, 14], [-4, 0, 3, 7, 10], [-7, -3, 0, 3, 7], [-5, -1, 2, 5, 9]], pad: 0.9, bass: 0.35, arp: 0.25, perc: 0, pulse: 0.15, bright: 0.4 },
  explore: { bpm: 76, root: 50, chords: [[0, 3, 7, 10], [-4, 0, 3, 7], [3, 7, 10, 14], [-2, 2, 5, 9]], pad: 0.7, bass: 0.4, arp: 0.4, perc: 0.12, pulse: 0.25, bright: 0.5 },
  combat: { bpm: 128, root: 45, chords: [[0, 3, 7], [-4, 0, 3], [-2, 2, 5], [-5, -1, 2]], pad: 0.45, bass: 0.9, arp: 0.6, perc: 0.85, pulse: 0.6, bright: 0.65 },
  boss: { bpm: 140, root: 43, chords: [[0, 3, 6], [1, 4, 8], [0, 3, 7], [-2, 1, 5]], pad: 0.6, bass: 1.0, arp: 0.7, perc: 1.0, pulse: 0.8, bright: 0.7 },
  sidequest: { bpm: 84, root: 55, chords: [[0, 4, 7, 11], [5, 9, 12, 16], [-3, 0, 4, 7], [2, 5, 9, 12]], pad: 0.6, bass: 0.35, arp: 0.5, perc: 0.15, pulse: 0.2, bright: 0.7 },
  tension: { bpm: 90, root: 41, chords: [[0, 1, 7], [0, 3, 8], [-1, 2, 7], [0, 1, 6]], pad: 0.8, bass: 0.6, arp: 0.15, perc: 0.3, pulse: 0.55, bright: 0.25 },
  ending: { bpm: 70, root: 52, chords: [[0, 4, 7, 11, 14], [5, 9, 12, 16], [-3, 0, 4, 7, 11], [7, 11, 14, 17]], pad: 1.0, bass: 0.4, arp: 0.5, perc: 0, pulse: 0.1, bright: 0.8 },
};

const midi = (n: number) => 440 * Math.pow(2, (n - 69) / 12);

class MusicPlayer {
  private mood: MusicMood = 'silence';
  private track: GainNode | null = null;
  private def: MoodDef | null = null;
  private nextBeat = 0;
  private beat = 0;
  private filter: BiquadFilterNode;
  private delay: DelayNode;
  constructor(private a: AudioEngine, private out: GainNode) {
    const c = a.ctx!;
    this.filter = c.createBiquadFilter();
    this.filter.type = 'lowpass';
    this.filter.frequency.value = 6000;
    this.delay = c.createDelay(1.5);
    this.delay.delayTime.value = 0.42;
    const fb = c.createGain();
    fb.gain.value = 0.32;
    const wet = c.createGain();
    wet.gain.value = 0.25;
    this.filter.connect(out);
    this.delay.connect(fb).connect(this.delay);
    this.delay.connect(wet).connect(out);
  }

  setMood(m: MusicMood, immediate: boolean) {
    if (m === this.mood) return;
    const c = this.a.ctx!;
    const t = c.currentTime;
    if (this.track) {
      const old = this.track;
      old.gain.cancelScheduledValues(t);
      old.gain.setValueAtTime(old.gain.value, t);
      old.gain.linearRampToValueAtTime(0, t + (immediate ? 0.3 : 2.5));
      setTimeout(() => old.disconnect(), 3000);
    }
    this.mood = m;
    if (m === 'silence') {
      this.track = null;
      this.def = null;
      return;
    }
    this.def = MOODS[m];
    const g = c.createGain();
    g.gain.setValueAtTime(0, t);
    g.gain.linearRampToValueAtTime(1, t + (immediate ? 0.8 : 2.5));
    g.connect(this.filter);
    g.connect(this.delay);
    this.track = g;
    this.nextBeat = t + 0.1;
    this.beat = 0;
  }

  tick() {
    const c = this.a.ctx;
    if (!c || !this.def || !this.track) return;
    const d = this.def;
    const spb = 60 / d.bpm / 2; // eighth notes
    while (this.nextBeat < c.currentTime + 0.25) {
      this.schedule(this.beat, this.nextBeat, spb, d, this.track);
      this.nextBeat += spb;
      this.beat++;
    }
  }

  private schedule(b: number, t: number, spb: number, d: MoodDef, out: GainNode) {
    const a = this.a;
    const c = a.ctx!;
    const barLen = 16; // eighths per chord (2 bars of 4/4)
    const chord = d.chords[Math.floor(b / barLen) % d.chords.length];
    const inBar = b % barLen;
    // Pad: on chord change, long detuned saw chord through a lowpass.
    if (inBar === 0 && d.pad > 0) {
      const dur = spb * barLen;
      const lp = c.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.setValueAtTime(400 + d.bright * 900, t);
      lp.frequency.linearRampToValueAtTime(700 + d.bright * 1600, t + dur * 0.5);
      lp.frequency.linearRampToValueAtTime(400 + d.bright * 900, t + dur);
      lp.connect(out);
      for (const n of chord) {
        for (const det of [-7, 7]) {
          const o = c.createOscillator();
          o.type = 'sawtooth';
          o.frequency.value = midi(d.root + 12 + n);
          o.detune.value = det;
          const g = c.createGain();
          g.gain.setValueAtTime(0.0001, t);
          g.gain.linearRampToValueAtTime(0.018 * d.pad, t + dur * 0.3);
          g.gain.linearRampToValueAtTime(0.012 * d.pad, t + dur * 0.8);
          g.gain.linearRampToValueAtTime(0.0001, t + dur + 0.4);
          o.connect(g).connect(lp);
          o.start(t);
          o.stop(t + dur + 0.5);
        }
      }
    }
    // Bass
    if (d.bass > 0 && (inBar % 4 === 0 || (d.perc > 0.5 && inBar % 2 === 0))) {
      const n = d.root - 12 + chord[0];
      const o = c.createOscillator();
      o.type = d.perc > 0.5 ? 'sawtooth' : 'triangle';
      o.frequency.value = midi(n);
      const lp = c.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.value = d.perc > 0.5 ? 420 : 260;
      const g = c.createGain();
      a.env(g, t, 0.01, 0.12 * d.bass, spb * (d.perc > 0.5 ? 1.6 : 3.5));
      o.connect(lp).connect(g).connect(out);
      o.start(t);
      o.stop(t + spb * 4);
    }
    // Arpeggio / plucks
    if (d.arp > 0) {
      const pattern = [0, 2, 1, 3, 2, 1, 3, 2];
      const play = d.perc > 0.5 ? true : (inBar % 2 === 0 && Math.random() < 0.75);
      if (play) {
        const n = d.root + 24 + chord[pattern[inBar % 8] % chord.length];
        const o = c.createOscillator();
        o.type = 'triangle';
        o.frequency.value = midi(n);
        const g = c.createGain();
        a.env(g, t, 0.003, 0.03 * d.arp, spb * 1.4);
        o.connect(g).connect(out);
        o.start(t);
        o.stop(t + spb * 2);
      }
    }
    // Pulse (sub tick)
    if (d.pulse > 0 && inBar % 2 === 1) {
      const o = c.createOscillator();
      o.type = 'sine';
      o.frequency.value = midi(d.root + chord[0]);
      const g = c.createGain();
      a.env(g, t, 0.002, 0.02 * d.pulse, spb * 0.5);
      o.connect(g).connect(out);
      o.start(t);
      o.stop(t + spb);
    }
    // Percussion
    if (d.perc > 0) {
      if (inBar % 4 === 0) {
        a.osc('sine', 120, t, 0.18, out, 0.35 * d.perc, 0.001, 42);
      }
      if (inBar % 8 === 4) a.noiseBurst(t, 0.12, out, 0.12 * d.perc, 'bandpass', 1800, 900, 0.8);
      if (d.perc > 0.5 || inBar % 2 === 0) a.noiseBurst(t, 0.03, out, 0.04 * d.perc, 'highpass', 7000);
    }
  }
}

// ---------------------------------------------------------------------------- Ambience
class Ambience {
  private nodes: AudioNode[] = [];
  private gain: GainNode | null = null;
  private cur: AmbienceId = 'none';
  private timer: number | null = null;
  constructor(private a: AudioEngine, private out: GainNode) {}

  set(id: AmbienceId) {
    if (id === this.cur) return;
    this.cur = id;
    const c = this.a.ctx!;
    const t = c.currentTime;
    if (this.gain) {
      const g = this.gain;
      const nodes = this.nodes;
      g.gain.setTargetAtTime(0, t, 0.6);
      setTimeout(() => {
        for (const n of nodes) {
          try { (n as AudioScheduledSourceNode).stop?.(); } catch { /* already stopped */ }
          n.disconnect();
        }
        g.disconnect();
      }, 3000);
    }
    if (this.timer) clearInterval(this.timer);
    this.nodes = [];
    this.gain = null;
    if (id === 'none') return;
    const g = c.createGain();
    g.gain.setValueAtTime(0, t);
    g.gain.setTargetAtTime(1, t, 0.8);
    g.connect(this.out);
    this.gain = g;
    const loopNoise = (kind: 'white' | 'pink' | 'brown', type: BiquadFilterType, f: number, q: number, vol: number, lfo = 0) => {
      const s = this.a.noiseSrc(kind, true);
      const bq = c.createBiquadFilter();
      bq.type = type;
      bq.frequency.value = f;
      bq.Q.value = q;
      const gg = c.createGain();
      gg.gain.value = vol;
      s.connect(bq).connect(gg).connect(g);
      s.start(t, Math.random());
      this.nodes.push(s, bq, gg);
      if (lfo > 0) {
        const o = c.createOscillator();
        o.frequency.value = lfo;
        const og = c.createGain();
        og.gain.value = vol * 0.6;
        o.connect(og).connect(gg.gain);
        o.start(t);
        this.nodes.push(o, og);
      }
    };
    const drone = (f: number, vol: number, type: OscillatorType = 'sine') => {
      const o = c.createOscillator();
      o.type = type;
      o.frequency.value = f;
      const gg = c.createGain();
      gg.gain.value = vol;
      const lp = c.createBiquadFilter();
      lp.type = 'lowpass';
      lp.frequency.value = 300;
      o.connect(lp).connect(gg).connect(g);
      o.start(t);
      this.nodes.push(o, gg, lp);
    };
    const sporadic = (fn: () => void, ms: number) => {
      this.timer = window.setInterval(() => {
        if (c.state === 'running') fn();
      }, ms);
    };
    switch (id) {
      case 'rain_city':
        loopNoise('pink', 'lowpass', 2800, 0.5, 0.22);
        loopNoise('white', 'highpass', 5000, 0.4, 0.04);
        loopNoise('brown', 'lowpass', 300, 0.7, 0.12, 0.07);
        sporadic(() => { if (Math.random() < 0.5) this.a.osc('sine', 1800 + Math.random() * 2400, c.currentTime, 0.04, g, 0.01, 0.001); }, 120);
        break;
      case 'metro_drip':
        loopNoise('brown', 'lowpass', 180, 0.8, 0.22, 0.05);
        drone(48, 0.04);
        sporadic(() => {
          if (Math.random() < 0.35) {
            const f = 900 + Math.random() * 1200;
            this.a.osc('sine', f, c.currentTime, 0.18, g, 0.025, 0.001, f * 0.5);
          }
        }, 400);
        break;
      case 'facility_hum':
        drone(60, 0.035, 'sawtooth');
        drone(120, 0.015);
        loopNoise('pink', 'bandpass', 600, 0.6, 0.06, 0.1);
        sporadic(() => { if (Math.random() < 0.15) for (let i = 0; i < 3; i++) this.a.osc('square', 1200 + Math.random() * 1500, c.currentTime + i * 0.06, 0.03, g, 0.006, 0.001); }, 900);
        break;
      case 'vault_hum':
        drone(41, 0.06);
        drone(61.7, 0.03, 'triangle');
        loopNoise('brown', 'lowpass', 220, 0.8, 0.14, 0.03);
        sporadic(() => { if (Math.random() < 0.25) this.a.noiseBurst(c.currentTime, 0.12, g, 0.04, 'highpass', 3000, 6000, 0.6); }, 700);
        break;
      case 'wind_roof':
        loopNoise('pink', 'bandpass', 500, 0.7, 0.3, 0.09);
        loopNoise('white', 'bandpass', 1400, 1.5, 0.05, 0.13);
        loopNoise('pink', 'lowpass', 2400, 0.5, 0.1);
        break;
      case 'core_drone':
        drone(36.7, 0.08);
        drone(55, 0.05, 'triangle');
        drone(73.4, 0.03, 'sawtooth');
        loopNoise('brown', 'lowpass', 160, 0.8, 0.12, 0.04);
        loopNoise('white', 'bandpass', 3200, 4, 0.015, 0.2);
        break;
    }
  }

  thunder(intensity: number) {
    const g = this.gain;
    if (!g || !this.a.ctx) return;
    const t = this.a.ctx.currentTime;
    this.a.noiseBurst(t, 3.5, g, 0.5 * intensity, 'lowpass', 600, 60, 0.7, 'brown', 0.08);
    this.a.noiseBurst(t + 0.2, 2.5, g, 0.25 * intensity, 'lowpass', 1400, 120, 0.6, 'pink', 0.3);
  }
}
