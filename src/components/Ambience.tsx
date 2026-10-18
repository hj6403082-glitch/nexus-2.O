'use client';
import { useEffect } from 'react';
// Pointer-reactive depth: writes smoothed --px/--py (-1…1) so light, grid and
// HUD layers parallax against each other. One rAF loop, idle when settled.
export function Ambience() {
  useEffect(() => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const root = document.documentElement; let tx = 0, ty = 0, x = 0, y = 0, frame = 0;
    const tick = () => {
      x += (tx - x) * .07; y += (ty - y) * .07;
      root.style.setProperty('--px', x.toFixed(4)); root.style.setProperty('--py', y.toFixed(4));
      frame = Math.abs(tx - x) + Math.abs(ty - y) > .0005 ? requestAnimationFrame(tick) : 0;
    };
    const move = (e: PointerEvent) => { tx = e.clientX / innerWidth * 2 - 1; ty = e.clientY / innerHeight * 2 - 1; if (!frame) frame = requestAnimationFrame(tick); };
    window.addEventListener('pointermove', move, { passive: true });
    return () => { window.removeEventListener('pointermove', move); cancelAnimationFrame(frame); };
  }, []);
  return <div className="ambience" aria-hidden="true"><div className="ambience-spot" /><div className="ambience-grid" /><div className="ambience-scan" /><div className="hud-frame"><i /><i /><i /><i /></div></div>;
}
