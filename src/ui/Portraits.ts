import * as THREE from 'three';
import { HumanModel } from '../actors/human/HumanModel';
import { LOOKS } from '../actors/human/Looks';
import { Log } from '../core/Log';

// Portraits: DreamLayer art from public/art/portraits/<id>.png when present, otherwise rendered
// in-engine from the actual character model (head-and-shoulders, three-point lighting).

const cache: Record<string, string> = {};

export async function buildPortraits(renderer: THREE.WebGLRenderer, ids: string[], lookOf?: (id: string) => import('../actors/human/HumanBuilder').Look | null, skipArt = false): Promise<Record<string, string>> {
  const size = 256;
  const rt = new THREE.WebGLRenderTarget(size, size, { samples: 4, colorSpace: THREE.SRGBColorSpace });
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0x0b1016);
  const key = new THREE.DirectionalLight(0xfff0e0, 3);
  key.position.set(1.2, 2, 2.4);
  const rim = new THREE.DirectionalLight(0x6fc8ff, 2.6);
  rim.position.set(-2, 1.5, -2);
  const fill = new THREE.HemisphereLight(0x8090a8, 0x101012, 0.9);
  scene.add(key, rim, fill);
  const cam = new THREE.PerspectiveCamera(26, 1, 0.05, 20);
  const prevTarget = renderer.getRenderTarget();
  const prevTone = renderer.toneMapping;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  for (const id of ids) {
    // Prefer authored art (unless the look was customised).
    const art = `art/portraits/${id}.png`;
    if (!skipArt) try {
      const r = await fetch(art, { method: 'HEAD' });
      if (r.ok && (r.headers.get('content-type') ?? '').startsWith('image')) {
        cache[id] = art;
        continue;
      }
    } catch {
      /* fall through to render */
    }
    const look = lookOf?.(id) ?? LOOKS[id];
    if (!look) continue;
    try {
      const m = new HumanModel(look, { lods: 1, faceSize: 512 });
      m.animator.update(0.016);
      m.update(0.016);
      scene.add(m.root);
      m.root.updateMatrixWorld(true);
      const head = m.socketWorld('head', new THREE.Vector3());
      cam.position.set(head.x + 0.18, head.y + 0.02, head.z + 0.95);
      cam.lookAt(head.x, head.y - 0.06, head.z);
      renderer.setRenderTarget(rt);
      renderer.render(scene, cam);
      const px = new Uint8Array(size * size * 4);
      renderer.readRenderTargetPixels(rt, 0, 0, size, size, px);
      const c = document.createElement('canvas');
      c.width = c.height = size;
      const ctx = c.getContext('2d')!;
      const img = ctx.createImageData(size, size);
      for (let y = 0; y < size; y++) img.data.set(px.subarray((size - 1 - y) * size * 4, (size - y) * size * 4), y * size * 4);
      ctx.putImageData(img, 0, 0);
      // Subtle scanline grade for the comms-portrait look.
      ctx.fillStyle = 'rgba(95,212,240,0.05)';
      for (let y = 0; y < size; y += 3) ctx.fillRect(0, y, size, 1);
      cache[id] = c.toDataURL('image/jpeg', 0.85);
      scene.remove(m.root);
      m.dispose();
    } catch (e) {
      Log.warn('portraits', 'failed for', id, e);
    }
  }
  renderer.setRenderTarget(prevTarget);
  renderer.toneMapping = prevTone;
  rt.dispose();
  return cache;
}

export function portrait(id: string): string | null {
  return cache[id] ?? null;
}
