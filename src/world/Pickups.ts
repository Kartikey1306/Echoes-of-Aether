import * as THREE from 'three';
import { getMaterial, glowTexture } from '../render/Materials';

// Procedural visuals for collectibles, powerups, quest items and caches.

export type PickupKind = 'fragment' | 'recording' | 'cache' | 'powerup' | 'quest' | 'item';

const POWERUP_COLORS: Record<string, number> = {
  aether_shard: 0x62d4ff,
  phase_core: 0x9a7bff,
  overcharge: 0xffb45e,
  shield_fragment: 0x7fe8c8,
  echo_fragment: 0xc39bff,
};

export function pickupColor(kind: PickupKind, powerup?: string): number {
  if (kind === 'powerup' && powerup) return POWERUP_COLORS[powerup] ?? 0x62d4ff;
  if (kind === 'fragment') return 0x5fd8ff;
  if (kind === 'recording') return 0x6fa8ff;
  if (kind === 'cache') return 0xa47dff;
  if (kind === 'quest') return 0xffc46a;
  return 0x9fe0ff;
}

function glowMat(color: number, k = 2.6) {
  return new THREE.MeshBasicMaterial({ color: new THREE.Color(color).multiplyScalar(k) });
}

export function buildPickupVisual(kind: PickupKind, powerup?: string): { group: THREE.Group; spin: THREE.Object3D; halo: THREE.Sprite; light: number } {
  const g = new THREE.Group();
  const spin = new THREE.Group();
  g.add(spin);
  const color = pickupColor(kind, powerup);
  const metal = getMaterial('metal_dark');
  switch (kind) {
    case 'fragment': {
      const c = new THREE.Mesh(new THREE.OctahedronGeometry(0.18, 0).scale(0.7, 1.6, 0.7), glowMat(color, 2.2));
      spin.add(c);
      for (let i = 0; i < 3; i++) {
        const s = new THREE.Mesh(new THREE.OctahedronGeometry(0.06, 0).scale(0.7, 1.8, 0.7), glowMat(0xa47dff, 2));
        const a = (i / 3) * Math.PI * 2;
        s.position.set(Math.cos(a) * 0.26, -0.05 + i * 0.05, Math.sin(a) * 0.26);
        s.rotation.z = 0.4;
        spin.add(s);
      }
      break;
    }
    case 'recording': {
      const core = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.09, 0.26, 12), glowMat(color, 2));
      const cap1 = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 0.05, 12), metal);
      cap1.position.y = 0.15;
      const cap2 = cap1.clone();
      cap2.position.y = -0.15;
      const ring = new THREE.Mesh(new THREE.TorusGeometry(0.2, 0.012, 6, 32), glowMat(color, 2.5));
      ring.rotation.x = Math.PI / 2;
      spin.add(core, cap1, cap2, ring);
      break;
    }
    case 'cache': {
      const box = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.45, 0.5), getMaterial('metal_painted'));
      box.position.y = -0.1;
      const lid = new THREE.Mesh(new THREE.BoxGeometry(0.84, 0.08, 0.54), metal);
      lid.position.y = 0.16;
      lid.name = 'lid';
      const strip = new THREE.Mesh(new THREE.BoxGeometry(0.82, 0.03, 0.52), glowMat(color, 2.4));
      strip.position.y = 0.1;
      g.add(box, lid, strip);
      break;
    }
    case 'powerup': {
      let core: THREE.Mesh;
      if (powerup === 'phase_core') {
        core = new THREE.Mesh(new THREE.SphereGeometry(0.16, 16, 12), glowMat(color));
        const r1 = new THREE.Mesh(new THREE.TorusGeometry(0.26, 0.015, 6, 32), glowMat(color, 2));
        const r2 = r1.clone();
        r2.rotation.x = Math.PI / 2;
        spin.add(r1, r2);
      } else if (powerup === 'overcharge') {
        core = new THREE.Mesh(new THREE.OctahedronGeometry(0.2, 0), glowMat(color));
        const cage = new THREE.Mesh(new THREE.OctahedronGeometry(0.3, 0), new THREE.MeshBasicMaterial({ color, wireframe: true }));
        spin.add(cage);
      } else if (powerup === 'shield_fragment') {
        core = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.24, 0.05, 6).rotateX(Math.PI / 2), glowMat(color, 2));
        const frame = new THREE.Mesh(new THREE.TorusGeometry(0.26, 0.02, 4, 6), metal);
        spin.add(frame);
      } else if (powerup === 'echo_fragment') {
        core = new THREE.Mesh(new THREE.IcosahedronGeometry(0.15, 0), glowMat(color));
        const ring = new THREE.Mesh(new THREE.TorusGeometry(0.28, 0.012, 6, 40), glowMat(0x8fd8ff, 2.5));
        ring.rotation.x = 1.2;
        spin.add(ring);
      } else {
        core = new THREE.Mesh(new THREE.OctahedronGeometry(0.12, 0).scale(1, 2.2, 1), glowMat(color));
        for (let i = 0; i < 4; i++) {
          const s = new THREE.Mesh(new THREE.OctahedronGeometry(0.06, 0).scale(1, 2.4, 1), glowMat(color, 2));
          s.position.set(Math.cos(i * 1.57) * 0.16, -0.08, Math.sin(i * 1.57) * 0.16);
          s.rotation.set(Math.cos(i) * 0.5, 0, Math.sin(i) * 0.5);
          spin.add(s);
        }
      }
      spin.add(core);
      const base = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.025, 6, 32), glowMat(color, 1.6));
      base.rotation.x = Math.PI / 2;
      base.position.y = -0.55;
      g.add(base);
      break;
    }
    case 'quest':
    case 'item': {
      const c = new THREE.Mesh(new THREE.BoxGeometry(0.22, 0.32, 0.14), getMaterial('metal'));
      const s = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.06, 0.15), glowMat(color, 2.2));
      s.position.y = 0.06;
      spin.add(c, s);
      break;
    }
  }
  const halo = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), color: new THREE.Color(color).multiplyScalar(0.9), blending: THREE.AdditiveBlending, depthWrite: false, transparent: true }));
  halo.scale.setScalar(kind === 'cache' ? 1.6 : 1.1);
  halo.position.y = kind === 'cache' ? 0.3 : 0;
  g.add(halo);
  g.traverse((o) => {
    const m = o as THREE.Mesh;
    if (m.isMesh) m.castShadow = false;
  });
  return { group: g, spin, halo, light: color };
}
