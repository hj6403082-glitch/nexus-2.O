'use client';
import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { motion as animated } from 'framer-motion';
import { motion } from '@/animations/spring';
import { stepSpring } from '@/animations/spring';
import { useForm } from '@/stores/form';
import { panelAnchor } from '@/embodiment/hand';
export function Dialog({ title, onClose, children, className = '' }: { title: string; onClose: () => void; children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  const embodied = useForm(s => s.phase === 'HUMANOID_ACTIVE') && className === 'module-panel';
  useEffect(() => {
    if (!embodied) return;
    let frame = 0, last = performance.now(); const x = { value: 0, velocity: 0 }, y = { value: 0, velocity: 0 };
    const draw = (now: number) => { const element = ref.current; const dt = Math.min(.05, (now - last) / 1000); last = now;
      if (element) { const held = panelAnchor.lift > 0 && innerWidth > 800; const dx = held ? panelAnchor.x - (innerWidth - 24 - element.offsetWidth / 2) : 0; const dy = held ? panelAnchor.y - element.offsetHeight / 2 - innerHeight / 2 : 0; element.style.translate = `${stepSpring(x, dx, dt, 65, 17)}px ${stepSpring(y, dy, dt, 65, 17)}px`; }
      frame = requestAnimationFrame(draw);
    }; frame = requestAnimationFrame(draw); return () => { cancelAnimationFrame(frame); if (ref.current) ref.current.style.translate = ''; };
  }, [embodied]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const frame = requestAnimationFrame(() => ref.current?.querySelector<HTMLElement>('input,button')?.focus());
    const trap = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
      if (e.key !== 'Tab' || embodied) return;
      const items = ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]),a,input,select,textarea,[tabindex="0"]');
      if (!items?.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', trap);
    return () => { cancelAnimationFrame(frame); document.removeEventListener('keydown', trap); previous?.focus(); };
  }, [onClose, embodied]);
  return <div className="dialog-shade" onClick={e => { if (e.target === e.currentTarget) onClose(); }}><animated.div ref={ref} role="dialog" aria-modal={!embodied} aria-label={title} className={`dialog ${className}`} initial={{ opacity: 0, y: 22, scale: .97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10 }} transition={{ type: 'spring', ...motion.arriving }}><div className="dialog-heading"><span className="eyebrow">{title}</span><button className="icon-button" onClick={onClose} aria-label="Close panel"><X size={18} /></button></div>{children}</animated.div></div>;
}
