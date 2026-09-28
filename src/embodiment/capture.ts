import * as THREE from 'three';
import { toCanvas } from 'html-to-image';
import { modules } from '@/lib/modules';
export type ParticleSources = { positions: Float32Array; colors: Float32Array; cards: Float32Array; seeds: Float32Array };
export async function captureSources(count: number, camera: THREE.Camera, report: (message: string) => void): Promise<ParticleSources> {
  report('Gathering your interface');
  const positions = new Float32Array(count * 3), colors = new Float32Array(count * 3), cards = new Float32Array(count), seeds = new Float32Array(count);
  let seed = 9183, cursor = 0;
  const random = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  const cardCount = Math.floor(count * .80 / 10);
  function fill(canvas: HTMLCanvasElement, amount: number, card: number, world: (x: number, y: number) => THREE.Vector3) {
    const context = canvas.getContext('2d', { willReadFrequently: true }); if (!context) throw new Error('Card rasterization is unavailable.');
    const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
    for (let i = 0; i < amount; i++) {
      let x = 0, y = 0, p = 0;
      for (let attempt = 0; attempt < 15; attempt++) {
        x = Math.floor(random() * canvas.width); y = Math.floor(random() * canvas.height); p = (y * canvas.width + x) * 4;
        const light = (data[p] + data[p + 1] + data[p + 2]) / 765;
        if (data[p + 3] > 80 && (random() < light * 1.8 || attempt === 14)) break;
      }
      const point = world(x / canvas.width, y / canvas.height); point.toArray(positions, cursor * 3);
      colors[cursor * 3] = data[p] / 255; colors[cursor * 3 + 1] = data[p + 1] / 255; colors[cursor * 3 + 2] = data[p + 2] / 255;
      cards[cursor] = card; seeds[cursor] = random(); cursor++;
    }
  }
  for (let i = 0; i < modules.length; i++) {
    const element = document.querySelector<HTMLElement>(`[data-module="${modules[i].id}"]`);
    if (!element) throw new Error('The spatial cards are not ready. Return to spatial mode and try again.');
    const canvas = await toCanvas(element, { width: 300, height: 362, pixelRatio: 1, skipFonts: true, backgroundColor: '#101b2b', style: { transform: 'none', display: 'flex', opacity: '1' } });
    fill(canvas, cardCount, i, (x, y) => new THREE.Vector3((x - .5) * 3, (.5 - y) * 3.62, .055));
  }
  const hud = [...document.querySelectorAll<HTMLElement>('.topbar,.system-stats,.workspace-heading,.system-log,.gesture-status,.orbit-controls,.bottom-strip')].filter(e => e.getBoundingClientRect().width > 0);
  const perHUD = Math.floor(count * .12 / Math.max(1, hud.length));
  for (const element of hud) {
    const box = element.getBoundingClientRect();
    const canvas = await toCanvas(element, { pixelRatio: 1, skipFonts: true, width: Math.ceil(box.width), height: Math.ceil(box.height), style: { position: 'relative', top: '0', left: '0', right: 'auto', bottom: 'auto', transform: 'none' } });
    fill(canvas, perHUD, 10, (x, y) => {
      const point = new THREE.Vector3((box.left + x * box.width) / innerWidth * 2 - 1, 1 - (box.top + y * box.height) / innerHeight * 2, .5).unproject(camera);
      const direction = point.sub(camera.position).normalize(); const distance = (1.8 - camera.position.z) / direction.z;
      return camera.position.clone().addScaledVector(direction, distance);
    });
  }
  // Floor and atmosphere join after the cards. Their coordinates remain in the
  // room; the same attribute buffer then carries them to the core and figure.
  while (cursor < count) {
    const ring = cursor % 2 === 0, angle = random() * Math.PI * 2;
    positions[cursor * 3] = ring ? Math.sin(angle) * 5 : (random() - .5) * 24;
    positions[cursor * 3 + 1] = ring ? -2.58 : random() * 8 - 2;
    positions[cursor * 3 + 2] = ring ? Math.cos(angle) * 5 - 3.5 : random() * -20;
    colors.set([.17, .29, .4], cursor * 3); cards[cursor] = 10; seeds[cursor] = random(); cursor++;
  }
  return { positions, colors, cards, seeds };
}
