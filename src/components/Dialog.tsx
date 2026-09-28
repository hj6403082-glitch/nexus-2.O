'use client';
import { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { motion as animated } from 'framer-motion';
import { motion } from '@/animations/spring';
export function Dialog({ title, onClose, children, className = '' }: { title: string; onClose: () => void; children: React.ReactNode; className?: string }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    const frame = requestAnimationFrame(() => ref.current?.querySelector<HTMLElement>('input,button')?.focus());
    const trap = (e: KeyboardEvent) => {
      if (e.key === 'Escape') { e.preventDefault(); onClose(); }
      if (e.key !== 'Tab') return;
      const items = ref.current?.querySelectorAll<HTMLElement>('button:not([disabled]),a,input,select,textarea,[tabindex="0"]');
      if (!items?.length) return;
      const first = items[0], last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
      if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
    };
    document.addEventListener('keydown', trap);
    return () => { cancelAnimationFrame(frame); document.removeEventListener('keydown', trap); previous?.focus(); };
  }, [onClose]);
  return <div className="dialog-shade" onClick={e => { if (e.target === e.currentTarget) onClose(); }}><animated.div ref={ref} role="dialog" aria-modal="true" aria-label={title} className={`dialog ${className}`} initial={{ opacity: 0, y: 22, scale: .97 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 10 }} transition={{ type: 'spring', ...motion.arriving }}><div className="dialog-heading"><span className="eyebrow">{title}</span><button className="icon-button" onClick={onClose} aria-label="Close panel"><X size={18} /></button></div>{children}</animated.div></div>;
}
