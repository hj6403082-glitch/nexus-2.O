'use client';
import { useEffect, useRef } from 'react';
import { shockSignal } from '@/stores/nexus';
import { sfx } from '@/animations/sfx';

// The liquid layer: slow aurora blobs that drift behind the scene and lean
// toward the pointer, a gooey metaball cursor trail, and a pointer-tracked
// highlight on every glass surface (the --mx/--my variables used by liquid.css).
const TRAIL = 6;
export function LiquidLayer() {
  const lead = useRef<HTMLDivElement>(null), trail = useRef<(HTMLSpanElement | null)[]>([]);
  useEffect(() => {
    const target = { x: innerWidth / 2, y: innerHeight / 2 }, points = Array.from({ length: TRAIL }, () => ({ ...target }));
    let frame = 0, idle = 0;
    const fine = matchMedia('(pointer: fine)').matches, reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;
    const move = (e: PointerEvent) => {
      target.x = e.clientX; target.y = e.clientY; idle = 0;
      document.documentElement.style.setProperty('--px-n', (e.clientX / innerWidth).toFixed(3));
      document.documentElement.style.setProperty('--py-n', (e.clientY / innerHeight).toFixed(3));
      const glass = (e.target as Element | null)?.closest?.('.liquid-glass, .small-control, .module-card, .control-dock, .form-switcher, .assistant-panel, .dialog, .bottom-strip button');
      if (glass instanceof HTMLElement) { const r = glass.getBoundingClientRect(); glass.style.setProperty('--mx', `${e.clientX - r.left}px`); glass.style.setProperty('--my', `${e.clientY - r.top}px`); }
    };
    const down = (e: PointerEvent) => {
      if (reduced) return;
      const ring = document.createElement('i'); ring.className = 'liquid-ripple'; ring.style.left = `${e.clientX}px`; ring.style.top = `${e.clientY}px`;
      document.body.appendChild(ring); ring.addEventListener('animationend', () => ring.remove(), { once: true });
    };
    const draw = () => {
      idle++;
      points.forEach((p, i) => { const lead = i ? points[i - 1] : target, k = i ? .32 : .24; p.x += (lead.x - p.x) * k; p.y += (lead.y - p.y) * k; });
      trail.current.forEach((el, i) => { if (el) { el.style.transform = `translate(${points[i].x}px, ${points[i].y}px) scale(${1 - i * .12})`; } });
      if (lead.current) lead.current.style.opacity = idle > 90 ? '0' : '1';
      frame = requestAnimationFrame(draw);
    };
    // Double-click empty space: a shockwave throws the spheres outward.
    const shock = (e: MouseEvent) => {
      if (!(e.target instanceof HTMLCanvasElement)) return;
      shockSignal.at = performance.now(); sfx.shock();
      const ring = document.createElement('i'); ring.className = 'liquid-ripple shock'; ring.style.left = `${e.clientX}px`; ring.style.top = `${e.clientY}px`;
      document.body.appendChild(ring); ring.addEventListener('animationend', () => ring.remove(), { once: true });
    };
    addEventListener('pointermove', move, { passive: true }); addEventListener('pointerdown', down, { passive: true }); addEventListener('dblclick', shock);
    if (fine && !reduced) frame = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(frame); removeEventListener('pointermove', move); removeEventListener('pointerdown', down); removeEventListener('dblclick', shock); };
  }, []);
  return <>
    <div className="liquid-aurora" aria-hidden="true"><i /><i /><i /><i className="follow" /></div>
    <svg className="liquid-defs" aria-hidden="true" width="0" height="0"><defs><filter id="liquid-goo"><feGaussianBlur in="SourceGraphic" stdDeviation="7" result="b" /><feColorMatrix in="b" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 22 -9" /></filter></defs></svg>
    <div ref={lead} className="liquid-cursor" aria-hidden="true">{Array.from({ length: TRAIL }, (_, i) => <span key={i} ref={el => { trail.current[i] = el; }} />)}</div>
  </>;
}
