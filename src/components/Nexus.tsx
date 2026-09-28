'use client';
import dynamic from 'next/dynamic';
import { Component, useEffect, useRef, useState, type ReactNode } from 'react';
import { AnimatePresence, MotionConfig } from 'framer-motion';
import { Hud } from './Hud';
import { HelpPanel, Launcher, ModulePanel } from './Panels';
import { ModuleCard } from './ModuleCard';
import { modules, wrapIndex } from '@/lib/modules';
import { handSignal, useNexus } from '@/stores/nexus';
import { useHandTracking } from '@/gestures/useHandTracking';
import { useControls } from '@/hooks/useControls';
import { useAudio } from '@/hooks/useAudio';
import { useAssistant } from '@/stores/assistant';
import { useAssistantController } from '@/ai/useAssistantController';
import { Assistant, WakeWave } from './Assistant';
import { FormControls } from './FormControls';
import { useForm } from '@/stores/form';
const Scene = dynamic(() => import('@/rendering/SpatialScene'), { ssr: false });
class RenderBoundary extends Component<{ children: ReactNode; fallback: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { useNexus.setState({ renderer: 'fallback', gpu: 'Unavailable' }); }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}
function FlatOrbit() {
  const index = useNexus(s => s.index);
  return <div className="flat-orbit"><ModuleCard module={modules[wrapIndex(index)]} ordinal={wrapIndex(index)} active /></div>;
}
function HandCursor() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { let frame = 0; const draw = () => { if (ref.current) { ref.current.style.transform = `translate(${handSignal.x * innerWidth}px, ${handSignal.y * innerHeight}px)`; ref.current.style.opacity = handSignal.visible ? '1' : '0'; ref.current.dataset.pinch = String(handSignal.pinching); } frame = requestAnimationFrame(draw); }; frame = requestAnimationFrame(draw); return () => cancelAnimationFrame(frame); }, []);
  return <div ref={ref} className="hand-cursor" aria-hidden="true"><span /><i /></div>;
}
export function Nexus() {
  const [ready, setReady] = useState(false);
  const renderer = useNexus(s => s.renderer), expanded = useNexus(s => s.expanded), help = useNexus(s => s.help), launcher = useNexus(s => s.launcher);
  const { start, stop } = useHandTracking(); const toggleAudio = useAudio(); useControls();
  const assistant = useAssistantController();
  const formPhase = useForm(s => s.phase);
  useEffect(() => {
    try { const canvas = document.createElement('canvas'); if (!canvas.getContext('webgl2')) useNexus.setState({ renderer: 'fallback', gpu: 'Unavailable' }); }
    catch { useNexus.setState({ renderer: 'fallback', gpu: 'Unavailable' }); }
    useNexus.getState().log('NEXUS 01 · spatial core initialized'); useNexus.getState().log('Orbit locked · input controls ready');
    const query = matchMedia('(prefers-reduced-motion: reduce)');
    const reduced = () => { if (query.matches) useNexus.setState({ drift: false }); }; reduced(); query.addEventListener('change', reduced);
    setReady(true); return () => query.removeEventListener('change', reduced);
  }, []);
  const tracking = () => { const status = useNexus.getState().tracking; if (['loading', 'searching', 'tracking'].includes(status)) stop(); else void start(); };
  return <MotionConfig reducedMotion="user"><main className={`nexus ${expanded ? 'has-panel' : ''} ${formPhase !== 'NORMAL' ? 'form-embodied' : ''}`}><div className="atmospheric-light" aria-hidden="true" /><div className="scene" aria-label="Spatial module orbit">{ready && (renderer === 'fallback' ? <FlatOrbit /> : <RenderBoundary fallback={<FlatOrbit />}><Scene /></RenderBoundary>)}</div><div className="scene-vignette" aria-hidden="true" /><WakeWave /><Hud onTracking={tracking} onAudio={() => void toggleAudio()} onAI={() => useAssistant.getState().wake()} /><FormControls controller={assistant} /><HandCursor /><AnimatePresence>{expanded && !help && !launcher && <ModulePanel key="module" />}{help && <HelpPanel key="help" />}{launcher && <Launcher key="launcher" />}</AnimatePresence><Assistant controller={assistant} /><div className="sr-only" aria-live="polite">{expanded ? `${expanded} focused` : 'Spatial orbit ready'}</div></main></MotionConfig>;
}
