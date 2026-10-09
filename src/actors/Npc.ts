import * as THREE from 'three';
import { dampAngle, distXZ, yawTo } from '../core/MathUtil';
import { G_NPC, G_PLAYER, G_WORLD, G_INVISIBLE, type CharacterBody, type Physics } from '../physics/Physics';
import { HumanModel } from './human/HumanModel';
import { LOOKS } from './human/Looks';
import type { NpcPlacement } from '../world/Zone';
import { buildSentinelBody, RobotModel, robotMaterials } from './enemies/RobotModel';
import { robotClips } from './enemies/EnemyAnims';
import type { Animator } from './human/Animator';

// Non-player characters: survivors in the plaza, the echo child Nia and the maintenance robot BOLT.

export class Npc {
  readonly id: string;
  readonly place: NpcPlacement;
  readonly root = new THREE.Group();
  human: HumanModel | null = null;
  robot: RobotModel | null = null;
  body: CharacterBody | null = null;
  readonly position = new THREE.Vector3();
  yaw: number;
  talking = false;
  private talkTarget: THREE.Vector3 | null = null;
  private routeIdx = 0;
  private waitT = 0;
  private reactCd = 0;
  visible = true;
  private ghostMats: THREE.Material[] = [];
  boltActive = false;

  constructor(place: NpcPlacement, physics: Physics) {
    this.id = place.id;
    this.place = place;
    this.position.copy(place.pos);
    this.yaw = place.yaw;
    if (place.id === 'bolt') {
      this.robot = new RobotModel(1.55, robotMaterials(0x9a7a2a, 0x2a2a2e, 0xffc24a, 2.2), 'robot', (m) => buildSentinelBody(m, false));
      this.root.add(this.robot.root);
      this.robot.animator.loco.combatIdle = robotClips('sentinel').stance;
    } else {
      const look = LOOKS[place.id];
      this.human = new HumanModel(look, { lods: 2, faceSize: 256, lodDistances: [12, 30] });
      this.root.add(this.human.root);
      if (place.echoOnly) this.makeGhost();
    }
    this.body = physics.createCharacter(place.pos, 0.35, place.id === 'nia' ? 1.2 : 1.7, G_NPC, G_WORLD | G_INVISIBLE | G_PLAYER);
    if (place.echoOnly) this.body.collider.setEnabled(false);
    this.applyBehaviour();
    this.sync();
  }

  get animator(): Animator {
    return (this.human?.animator ?? this.robot!.animator)!;
  }

  private makeGhost() {
    if (!this.human) return;
    const mat = new THREE.MeshBasicMaterial({ color: new THREE.Color(0x7fb8ff).multiplyScalar(0.55), transparent: true, opacity: 0.55, blending: THREE.AdditiveBlending, depthWrite: false });
    this.ghostMats.push(mat);
    for (const m of this.human.meshes) {
      m.material = mat;
      m.castShadow = false;
    }
  }

  applyBehaviour() {
    const clips = this.human?.anims.clips ?? this.robot?.anims.clips;
    if (!clips) return;
    if (this.id === 'bolt') {
      if (this.boltActive) {
        this.robot!.animator.setState(null, 0.4);
        this.robot!.animator.combatStance = 0;
      } else this.robot!.animator.setState(this.robot!.anims.clips.sit, 0.01);
      return;
    }
    const b = this.place.behaviour;
    if (b === 'wander') {
      this.animator.setState(null, 0.3);
      return;
    }
    const clip = clips[b];
    if (clip) this.animator.setState(clip, 0.4);
  }

  startTalk(playerPos: THREE.Vector3) {
    this.talking = true;
    this.talkTarget = playerPos.clone();
    if (this.human) this.animator.setState(this.human.anims.clips.talk, 0.4);
  }

  endTalk() {
    this.talking = false;
    this.talkTarget = null;
    this.applyBehaviour();
  }

  react() {
    if (this.reactCd > 0 || !this.human || this.talking) return;
    this.reactCd = 8;
    this.animator.play(this.human.anims.clips.npc_react, { fadeIn: 0.1 });
  }

  setVisible(v: boolean) {
    this.visible = v;
    this.root.visible = v;
  }

  update(dt: number, playerPos: THREE.Vector3 | null, echoActive: boolean) {
    this.reactCd -= dt;
    if (this.place.echoOnly) this.setVisible(echoActive);
    const a = this.animator;
    let speed = 0;
    if (this.talking && this.talkTarget) {
      this.yaw = dampAngle(this.yaw, yawTo(this.position, this.talkTarget), 5, dt);
    } else if (this.place.behaviour === 'wander' && this.place.route && this.place.route.length > 1) {
      const target = this.place.route[this.routeIdx];
      const d = distXZ(this.position, target);
      if (this.waitT > 0) {
        this.waitT -= dt;
      } else if (d < 0.4) {
        this.routeIdx = (this.routeIdx + 1) % this.place.route.length;
        this.waitT = 1.5 + Math.random() * 3;
      } else {
        speed = 1.1;
        const dir = new THREE.Vector3().subVectors(target, this.position).setY(0).normalize();
        this.yaw = dampAngle(this.yaw, Math.atan2(dir.x, dir.z), 4, dt);
        const v = dir.multiplyScalar(speed * dt);
        if (this.body && this.body.collider.isEnabled()) {
          this.body.move(v.setY(-0.05));
          this.position.copy(this.body.position);
        } else this.position.add(v);
      }
    } else if (this.boltActive && this.robot) {
      // BOLT walks a small perimeter loop around the camp.
      const t = performance.now() / 1000;
      const center = this.place.pos;
      const target = new THREE.Vector3(center.x + Math.cos(t * 0.15) * 3, center.y, center.z + Math.sin(t * 0.15) * 3);
      const dir = target.sub(this.position).setY(0);
      if (dir.length() > 0.2) {
        speed = 0.9;
        dir.normalize();
        this.yaw = dampAngle(this.yaw, Math.atan2(dir.x, dir.z), 3, dt);
        this.body?.move(dir.multiplyScalar(speed * dt).setY(-0.05));
        if (this.body) this.position.copy(this.body.position);
      }
    } else if (playerPos && distXZ(playerPos, this.position) < 3.5 && this.place.behaviour !== 'npc_work') {
      // Glance at the player when they come close.
      const rel = Math.atan2(Math.sin(yawTo(this.position, playerPos) - this.yaw), Math.cos(yawTo(this.position, playerPos) - this.yaw));
      a.lookYaw = Math.max(-1, Math.min(1, rel));
    } else a.lookYaw = 0;
    a.speed = speed;
    this.sync();
    this.human?.update(dt);
    this.robot?.update(dt);
  }

  private sync() {
    this.root.position.copy(this.position);
    this.root.rotation.y = this.yaw;
  }

  dispose() {
    this.body?.dispose();
    this.human?.dispose();
    this.robot?.dispose();
    for (const m of this.ghostMats) m.dispose();
    this.root.removeFromParent();
  }
}
