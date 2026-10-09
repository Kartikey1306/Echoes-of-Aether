import * as THREE from 'three';
import { damp, dampAngle } from '../core/MathUtil';
import { HumanModel } from '../actors/human/HumanModel';
import type { Look } from '../actors/human/HumanBuilder';
import { bakeEnvironment, createSky } from '../render/Environment';
import { getMaterial } from '../render/Materials';
import { Weather } from '../render/Weather';
import type { Game } from '../game/Game';
import type { CharacterId } from '../game/GameState';
import { Physics } from '../physics/Physics';
import { LevelBuilder } from './kit/LevelBuilder';
import * as P from './kit/Props';

// Main menu / character select backdrop: a rooftop above the Fallen District in the rain.

export class MenuScene {
  readonly scene = new THREE.Scene();
  private root = new THREE.Group();
  kael!: HumanModel;
  lyra!: HumanModel;
  private weather!: Weather;
  private time = 0;
  private mode: 'menu' | 'charselect' | 'designer' = 'menu';
  /** Designer camera framing. */
  focus: 'body' | 'face' = 'body';
  selected: CharacterId = 'kael';
  private spin = 0;
  private spinVel = 0;
  private spots: Record<CharacterId, THREE.SpotLight | null> = { kael: null, lyra: null };
  private monCore!: THREE.Mesh;
  grade = { exposure: 1.1, contrast: 1.08, saturation: 0.95, lift: [0, 0.006, 0.018] as [number, number, number], gain: [0.98, 1, 1.05] as [number, number, number], bloomThreshold: 0.88 };
  private physics = new Physics();
  private camPos = new THREE.Vector3();
  private camLook = new THREE.Vector3();

  constructor(private game: Game) {
    this.scene.add(this.root);
  }

  async build() {
    const S = this.scene;
    const b = new LevelBuilder(this.root, this.physics);
    const skyCfg = { top: 0x04070c, horizon: 0x1c2636, bottom: 0x05070a, glow: 0x40304a, glowStrength: 0.6, storm: true };
    const sky = createSky(skyCfg);
    S.add(sky);
    S.environment = bakeEnvironment(this.game.rs.renderer, skyCfg, [{ dir: new THREE.Vector3(0.3, 0.2, -1), color: 0x5fd8ff, size: 5, intensity: 2 }]);
    S.environmentIntensity = 0.6;
    S.fog = new THREE.FogExp2(0x0c1219, 0.012);
    const hemi = new THREE.HemisphereLight(0x405674, 0x0a0a0d, 0.7);
    S.add(hemi);
    const moon = new THREE.DirectionalLight(0x9ab4dc, 1.1);
    moon.position.set(-20, 30, 10);
    moon.castShadow = true;
    S.add(moon, moon.target);
    // Rooftop
    b.box(0, -0.25, 0, 20, 0.5, 16, 'concrete_wet');
    b.box(0, 0.45, -8.1, 20, 0.9, 0.3, 'concrete_dark');
    b.box(-10.1, 0.45, 0, 0.3, 0.9, 16, 'concrete_dark');
    P.acUnit(b, -6, 0, 4, 0.3);
    P.vent(b, 6.5, 0, 5);
    P.antenna(b, -8, 0, -6, 7);
    P.waterTank(b, 7, 0, -5);
    b.box(0, -10.5, 0, 20, 20, 16, 'concrete_dark', { collide: false });
    // City below/around
    const r = (s: number) => {
      const x = Math.sin(s * 91.7) * 43758.5;
      return x - Math.floor(x);
    };
    // The city sits ~22 m below the rooftop.
    const cityRoot = new THREE.Group();
    cityRoot.position.y = -22;
    this.root.add(cityRoot);
    const cb = new LevelBuilder(cityRoot, this.physics);
    for (let i = 0; i < 40; i++) {
      const ang = -Math.PI * 0.95 + (i / 40) * Math.PI * 0.9;
      const dist = 40 + r(i) * 70;
      const x = Math.cos(ang) * dist, z = Math.sin(ang) * dist - 10;
      const h = 10 + r(i + 7) * 42;
      P.building(cb, x, z, 10 + r(i + 3) * 10, 10 + r(i + 5) * 10, h, 700 + i, { lit: 0.1, faces: ['s', 'e', 'w', 'n'], collide: false });
    }
    for (let i = 0; i < 6; i++) P.streetLight(cb, -20 + i * 12, -30, 0, { light: false });
    cb.box(0, -0.2, -40, 260, 0.4, 160, 'asphalt', { collide: false });
    cb.finalize();
    // Distant monument with glowing core
    b.cyl(14, -8, -70, 1.2, 2.0, 30, 'metal_dark', 6, { collide: false });
    this.monCore = new THREE.Mesh(new THREE.IcosahedronGeometry(2.4, 3), getMaterial('aether'));
    this.monCore.position.set(14, 7, -70);
    S.add(this.monCore);
    const ml = new THREE.PointLight(0x5fd8ff, 300, 80, 1.6);
    ml.position.set(14, 7, -70);
    S.add(ml);
    b.glowSprite(14, 7, -70, 26, 0x5fd8ff, 0.8);
    // Character select platforms
    for (const [x, c] of [[-1.3, 'kael'], [1.3, 'lyra']] as [number, CharacterId][]) {
      b.cyl(x, 0.06, 1.5, 0.9, 0.95, 0.12, 'metal_dark', 32, { collide: false });
      b.cyl(x, 0.125, 1.5, 0.92, 0.92, 0.01, c === 'kael' ? 'emit_cyan' : 'emit_violet', 48, { collide: false, open: true });
      const spot = new THREE.SpotLight(c === 'kael' ? 0xbfe2ff : 0xd8c8ff, 0, 10, 0.45, 0.6, 1.4);
      spot.position.set(x + 0.4, 5.5, 4.5);
      spot.target.position.set(x, 1, 1.5);
      S.add(spot, spot.target);
      this.spots[c] = spot;
    }
    b.finalize();
    // Characters
    this.kael = new HumanModel(this.game.lookFor('kael'), { lods: 1, faceSize: 512 });
    this.lyra = new HumanModel(this.game.lookFor('lyra'), { lods: 1, faceSize: 512 });
    S.add(this.kael.root, this.lyra.root);
    this.weather = new Weather({ rain: 1, wind: new THREE.Vector2(2, 0.6), lightning: true, lightningInterval: [9, 20], splashHeight: 0.02 }, this.game.settings.data.graphics.effects);
    this.weather.skyMat = sky.material as THREE.ShaderMaterial;
    this.weather.flashLights.push({ light: hemi, base: hemi.intensity, boost: 3 }, { light: moon, base: moon.intensity, boost: 2.5 });
    S.add(this.weather.group);
    this.enter('menu');
    await this.game.rs.compile(S, this.game.rs.camera);
  }

  /** Swap a protagonist's model for a new look (Character Designer). */
  setLook(c: CharacterId, look: Look) {
    const old = c === 'kael' ? this.kael : this.lyra;
    const m = new HumanModel(look, { lods: 1, faceSize: 512 });
    m.root.position.copy(old.root.position);
    m.root.rotation.y = old.root.rotation.y;
    m.animator.combatStance = old.animator.combatStance;
    this.scene.add(m.root);
    old.dispose();
    if (c === 'kael') this.kael = m;
    else this.lyra = m;
  }

  enter(mode: 'menu' | 'charselect' | 'designer') {
    this.mode = mode;
    this.selected = this.game.selectedCharacter;
    this.spin = 0;
    if (mode === 'menu') {
      // Standing at the parapet, looking out at the monument.
      this.kael.root.position.set(-0.6, 0, -6.4);
      this.kael.root.rotation.y = Math.PI + 0.25;
      this.lyra.root.position.set(0.7, 0, -6.1);
      this.lyra.root.rotation.y = Math.PI - 0.1;
      this.kael.animator.combatStance = 0;
      this.lyra.animator.combatStance = 0;
      for (const s of Object.values(this.spots)) if (s) s.intensity = 0;
    } else {
      this.kael.root.visible = this.lyra.root.visible = true;
      this.kael.root.position.set(-1.3, 0.12, 1.5);
      this.lyra.root.position.set(1.3, 0.12, 1.5);
      this.kael.root.rotation.y = 0.15;
      this.lyra.root.rotation.y = -0.15;
    }
    this.weather.flashScale = this.game.settings.data.accessibility.flashIntensity;
  }

  select(c: CharacterId) {
    this.selected = c;
    this.spin = 0;
    this.spinVel = 0;
  }

  rotate(delta: number) {
    this.spinVel += delta;
  }

  update(dt: number) {
    this.time += dt;
    const t = this.time;
    this.weather.update(dt, this.game.rs.camera);
    this.monCore.rotation.y += dt * 0.2;
    this.monCore.scale.setScalar(1 + Math.sin(t * 1.6) * 0.05);
    this.kael.update(dt);
    this.lyra.update(dt);
    const cam = this.game.rs.camera;
    let pos: THREE.Vector3, look: THREE.Vector3;
    if (this.mode === 'menu') {
      // Slow lateral dolly behind the two protagonists.
      const s = Math.sin(t * 0.05);
      pos = new THREE.Vector3(3.2 + s * 1.6, 2.1 + Math.sin(t * 0.07) * 0.2, -1.2 + Math.cos(t * 0.04) * 0.6);
      look = new THREE.Vector3(1 + s * 2.5, 1.8, -20);
    } else {
      const x = this.selected === 'kael' ? -1.3 : 1.3;
      const active0 = this.selected === 'kael' ? this.kael : this.lyra;
      if (this.mode === 'designer') {
        const hgt = active0.height;
        // Keep the character in the left part of the screen (the panel is on the right).
        if (this.focus === 'face') {
          pos = new THREE.Vector3(x + 0.26, hgt * 0.91 + 0.14, 2.85);
          look = new THREE.Vector3(x + 0.26, hgt * 0.9 + 0.13, 1.5);
        } else {
          pos = new THREE.Vector3(x + 0.75, 1.15, 5.2);
          look = new THREE.Vector3(x + 0.75, 1.0, 1.5);
        }
      } else {
        pos = new THREE.Vector3(x * 0.55, 1.45, 5.3);
        look = new THREE.Vector3(x * 0.85, 1.05, 1.5);
      }
      this.spin += this.spinVel * dt;
      this.spinVel *= Math.exp(-3 * dt);
      const active = this.selected === 'kael' ? this.kael : this.lyra;
      const other = this.selected === 'kael' ? this.lyra : this.kael;
      active.root.rotation.y = dampAngle(active.root.rotation.y, (this.selected === 'kael' ? 0.2 : -0.2) + this.spin, 8, dt);
      other.root.rotation.y = dampAngle(other.root.rotation.y, this.selected === 'kael' ? -0.35 : 0.35, 4, dt);
      active.animator.combatStance = 1;
      other.animator.combatStance = 0;
      for (const c of ['kael', 'lyra'] as CharacterId[]) {
        const sp = this.spots[c];
        if (sp) sp.intensity = damp(sp.intensity, c === this.selected ? 70 : 12, 6, dt);
      }
    }
    this.camPos.lerp(pos, 1 - Math.exp(-3 * dt));
    this.camLook.lerp(look, 1 - Math.exp(-3 * dt));
    if (this.camPos.lengthSq() === 0) {
      this.camPos.copy(pos);
      this.camLook.copy(look);
    }
    cam.position.copy(this.camPos);
    cam.lookAt(this.camLook);
    cam.fov = this.mode === 'menu' ? 50 : this.mode === 'designer' ? (this.focus === 'face' ? 30 : 36) : 34;
    if (this.mode === 'designer') {
      // Only the edited character is shown in the designer.
      this.kael.root.visible = this.selected === 'kael';
      this.lyra.root.visible = this.selected === 'lyra';
    }
    cam.updateProjectionMatrix();
    this.game.rs.setPost({ flash: this.weather.flash * 0.35, echo: 0, damage: 0 });
  }
}
