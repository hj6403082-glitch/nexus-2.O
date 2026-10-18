'use client';
import { useEffect, useState } from 'react';
const LINES = ['SPATIAL CORE', 'NEURAL LINK', 'PARTICLE FIELD', 'ORBIT'];
const GLYPHS = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789#%&@';
// Short cinematic start: the wordmark decodes while the systems come online,
// then the overlay irises open onto the orbit. Once per session; any key or
// click skips it; reduced motion skips it entirely.
export function BootSequence() {
  const [stage, setStage] = useState<'hidden' | 'run' | 'exit'>('hidden');
  const [word, setWord] = useState('NEXUS'), [online, setOnline] = useState(0);
  useEffect(() => {
    let seen = false; try { seen = sessionStorage.getItem('nexus-booted') === '1'; sessionStorage.setItem('nexus-booted', '1'); } catch { /* Storage blocked: still boot. */ }
    if (seen || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    setStage('run');
    const start = performance.now(); let frame = 0;
    const decode = () => {
      const t = (performance.now() - start) / 1100;
      setWord('NEXUS'.split('').map((c, i) => t * 6 > i + 1.4 ? c : GLYPHS[Math.floor(Math.random() * GLYPHS.length)]).join(''));
      if (t < 1) frame = requestAnimationFrame(decode); else setWord('NEXUS');
    };
    frame = requestAnimationFrame(decode);
    const timers = LINES.map((_, i) => setTimeout(() => setOnline(i + 1), 320 + i * 260));
    const exit = setTimeout(() => setStage('exit'), 1750), done = setTimeout(() => setStage('hidden'), 2500);
    const skip = () => { setStage('exit'); setTimeout(() => setStage('hidden'), 700); };
    window.addEventListener('keydown', skip, { once: true }); window.addEventListener('pointerdown', skip, { once: true });
    return () => { cancelAnimationFrame(frame); timers.forEach(clearTimeout); clearTimeout(exit); clearTimeout(done); window.removeEventListener('keydown', skip); window.removeEventListener('pointerdown', skip); };
  }, []);
  if (stage === 'hidden') return null;
  return <div className={`boot ${stage === 'exit' ? 'boot-exit' : ''}`} aria-hidden="true">
    <div className="boot-core"><i /><i /><i /><b /></div>
    <strong className="boot-word">{word}</strong>
    <small className="boot-sub">SPATIAL OPERATING SYSTEM</small>
    <ul className="boot-lines">{LINES.map((line, i) => <li key={line} data-on={i < online || undefined}><span>{line}</span><b>{i < online ? 'ONLINE' : '· · ·'}</b></li>)}</ul>
  </div>;
}
