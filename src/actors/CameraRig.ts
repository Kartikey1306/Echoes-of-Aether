import * as THREE from 'three';
import { clamp, damp, dampAngle, wrapAngle } from '../core/MathUtil';
import type { Physics } from '../physics/Physics';

// Third-person orbit camera with collision, shoulder offset, aim mode, lock-on and shake.

export class CameraRig {
  readonly camera: THREE.PerspectiveCamera;
  /** Heading: the camera looks along (sin h, 0, cos h). */
  heading = Math.PI;
  pitch = 0.18;
  distance = 4.3;
  private curDist = 4.3;
  shoulder = 0.42;
  private curShoulder = 0.42;
  pivotHeight = 1.55;
  private curPivotH = 1.55;
  baseFov = 62;
  private fov = 62;
  aiming = false;
  sprinting = false;
  lockTarget: THREE.Vector3 | null = null;
  private trauma = 0;
  shakeScale = 1;
  private shakeT = 0;
  readonly pivot = new THREE.Vector3();
  private smoothFocus = new THREE.Vector3();
  private initialized = false;
  cinematic: { pos: THREE.Vector3; look: THREE.Vector3; fov: number } | null = null;
  /** Extra zoom-out for big fights. */
  combatZoom = 0;
  private curCombatZoom = 0;
  indoor = false;

  constructor(camera: THREE.PerspectiveCamera) {
    this.camera = camera;
  }

  /** Forward/right vectors on the ground plane for camera-relative movement. */
  forward(out = new THREE.Vector3()) {
    return out.set(Math.sin(this.heading), 0, Math.cos(this.heading));
  }
  right(out = new THREE.Vector3()) {
    return out.set(-Math.cos(this.heading), 0, Math.sin(this.heading));
  }
  lookDir(out = new THREE.Vector3()) {
    const cp = Math.cos(this.pitch);
    return out.set(Math.sin(this.heading) * cp, -Math.sin(this.pitch), Math.cos(this.heading) * cp);
  }

  addTrauma(t: number) {
    this.trauma = Math.min(1, this.trauma + t);
  }

  snapBehind(yaw: number) {
    this.heading = yaw;
    this.pitch = 0.18;
    this.initialized = false;
  }

  update(dt: number, look: { x: number; y: number }, focus: THREE.Vector3, physics: Physics) {
    if (this.cinematic) {
      const c = this.cinematic;
      this.camera.position.copy(c.pos);
      this.camera.lookAt(c.look);
      if (Math.abs(this.camera.fov - c.fov) > 0.01) {
        this.camera.fov = c.fov;
        this.camera.updateProjectionMatrix();
      }
      this.applyShake(dt);
      this.initialized = false;
      return;
    }
    // Input
    this.heading = wrapAngle(this.heading - look.x);
    this.pitch = clamp(this.pitch + look.y, -0.85, 1.15);
    if (this.lockTarget) {
      const dx = this.lockTarget.x - focus.x, dz = this.lockTarget.z - focus.z;
      const want = Math.atan2(dx, dz);
      this.heading = dampAngle(this.heading, want, 6, dt);
      const dist = Math.hypot(dx, dz);
      const wantPitch = clamp(0.25 - (this.lockTarget.y - focus.y - 1.2) / Math.max(4, dist) * 0.6, -0.1, 0.6);
      this.pitch = damp(this.pitch, wantPitch, 2.5, dt);
    }
    // Smooth focus (critically damped feel; tighter vertically to avoid jitter on stairs)
    if (!this.initialized) {
      this.smoothFocus.copy(focus);
      this.curDist = this.distance;
      this.initialized = true;
    }
    this.smoothFocus.x = damp(this.smoothFocus.x, focus.x, 18, dt);
    this.smoothFocus.z = damp(this.smoothFocus.z, focus.z, 18, dt);
    this.smoothFocus.y = damp(this.smoothFocus.y, focus.y, 10, dt);

    const wantDist = this.aiming ? 1.9 : this.distance + this.curCombatZoom + (this.indoor ? -0.4 : 0);
    const wantShoulder = this.aiming ? 0.62 : this.shoulder;
    const wantPivot = this.aiming ? 1.62 : this.pivotHeight;
    const wantFov = this.aiming ? 50 : this.baseFov + (this.sprinting ? 7 : 0);
    this.curCombatZoom = damp(this.curCombatZoom, this.combatZoom, 2, dt);
    this.curShoulder = damp(this.curShoulder, wantShoulder, 10, dt);
    this.curPivotH = damp(this.curPivotH, wantPivot, 10, dt);
    this.fov = damp(this.fov, wantFov, 6, dt);

    const right = this.right(new THREE.Vector3());
    this.pivot.copy(this.smoothFocus).setY(this.smoothFocus.y + this.curPivotH);
    // Shoulder offset with collision so the pivot never sits inside a wall.
    const sh = physics.raycast(this.pivot, right, this.curShoulder + 0.25);
    const shoulder = sh ? Math.max(0, sh.distance - 0.25) : this.curShoulder;
    this.pivot.addScaledVector(right, shoulder);

    const dir = this.lookDir(new THREE.Vector3());
    const back = dir.clone().negate();
    const hit = physics.raycast(this.pivot, back, wantDist + 0.3);
    const allowed = hit ? Math.max(0.55, hit.distance - 0.3) : wantDist;
    // Pull in fast, ease out slowly.
    this.curDist = allowed < this.curDist ? damp(this.curDist, allowed, 30, dt) : damp(this.curDist, allowed, 3.5, dt);
    this.camera.position.copy(this.pivot).addScaledVector(back, this.curDist);
    this.camera.lookAt(this.pivot.clone().addScaledVector(dir, 6));
    if (Math.abs(this.camera.fov - this.fov) > 0.01) {
      this.camera.fov = this.fov;
      this.camera.updateProjectionMatrix();
    }
    this.applyShake(dt);
  }

  private applyShake(dt: number) {
    this.trauma = Math.max(0, this.trauma - dt * 1.6);
    if (this.trauma <= 0 || this.shakeScale <= 0) return;
    this.shakeT += dt * 40;
    const s = this.trauma * this.trauma * this.shakeScale;
    const n = (o: number) => Math.sin(this.shakeT * (1.1 + o) + o * 17) * Math.cos(this.shakeT * 0.7 + o * 3);
    this.camera.rotateX(n(1) * 0.03 * s);
    this.camera.rotateY(n(2) * 0.03 * s);
    this.camera.rotateZ(n(3) * 0.04 * s);
  }

  /** Point under the screen centre (for aiming): raycast from the camera. */
  aimPoint(physics: Physics, maxDist = 80): THREE.Vector3 {
    const dir = new THREE.Vector3();
    this.camera.getWorldDirection(dir);
    const hit = physics.raycast(this.camera.position, dir, maxDist);
    return hit ? hit.point : this.camera.position.clone().addScaledVector(dir, maxDist);
  }
}
