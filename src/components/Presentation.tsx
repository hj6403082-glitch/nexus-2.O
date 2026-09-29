'use client';
import { useEffect, useRef } from 'react';
import { useNexus } from '@/stores/nexus';
import { useForm } from '@/stores/form';
import { presentation, presentationEnvelopes } from '@/animations/presentation';
export function Presentation() {
  const expanded = useNexus(s => s.expanded), ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!expanded || useForm.getState().phase !== 'NORMAL') { presentation.active = false; presentation.time = 2.4; return; }
    presentation.module = expanded; presentation.time = 0; presentation.active = true;
    let frame = 0, last = performance.now();
    const cancel = () => { presentation.time = 2.4; presentation.active = false; };
    const step = (now: number) => {
      presentation.time = Math.min(2.4, presentation.time + Math.min(.05, (now - last) / 1000)); last = now;
      const e = presentationEnvelopes(presentation.time);
      if (ref.current) { ref.current.style.opacity = String(e.target); ref.current.style.transform = `translate(-50%,-50%) scale(${1.3 - e.target * .3})`; ref.current.style.setProperty('--scan', `${e.scan * 100}%`); }
      if (presentation.time < 2.4 && presentation.active) frame = requestAnimationFrame(step); else { presentation.active = false; if (ref.current) ref.current.style.opacity = '0'; }
    };
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) cancel(); else frame = requestAnimationFrame(step);
    window.addEventListener('pointerdown', cancel); window.addEventListener('keydown', cancel);
    return () => { cancelAnimationFrame(frame); cancel(); window.removeEventListener('pointerdown', cancel); window.removeEventListener('keydown', cancel); };
  }, [expanded]);
  return <div ref={ref} className="presentation-bracket" aria-hidden="true"><i /><i /><i /><i /><div className="presentation-scan" /></div>;
}
