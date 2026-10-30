'use client';
import { useEffect, useRef } from 'react';
import { useForm } from '@/stores/form';
import { gazeSignal } from '@/embodiment/gaze';
// Live eye-contact readout for Human mode: says whether the webcam has found
// you, and a dot shows where NEXUS is looking. Reads the hot gaze signal on
// animation frames, so it never re-renders React while tracking.
const LABEL = { starting: 'Starting camera', searching: 'Looking for you', tracking: 'Eye contact' } as const;
export function GazeIndicator() {
  const status = useForm(s => s.gaze), dot = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    if (status !== 'tracking') return;
    let frame = 0;
    const draw = () => { if (dot.current) dot.current.style.transform = `translate(${gazeSignal.yaw * 14}px, ${gazeSignal.pitch * 14}px)`; frame = requestAnimationFrame(draw); };
    frame = requestAnimationFrame(draw); return () => cancelAnimationFrame(frame);
  }, [status]);
  if (status === 'off') return null;
  return <div className="gaze-indicator" data-status={status} role="status" aria-live="polite"><span className="gaze-reticle" aria-hidden="true"><span ref={dot} className="gaze-dot" /></span><span>{LABEL[status]}</span></div>;
}
