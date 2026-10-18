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
import { useAmbient } from '@/hooks/useAmbient';
import { useAssistant } from '@/stores/assistant';
import { useAssistantController } from '@/ai/useAssistantController';
import { Assistant, WakeWave } from './Assistant';
import { Presentation } from './Presentation';
import { WorldControls } from './WorldControls';
import { FormControls } from './FormControls';
import { useForm } from '@/stores/form';
import { useGazeTracking } from '@/embodiment/useGazeTracking';
import { useWorld } from '@/stores/world';
import { useProject } from '@/stores/project';
import { ProjectWorldBanner } from './ProjectWorldBanner';
import { AppShell } from './AppShell';
import { Ambience } from './Ambience';
import { BootSequence } from './BootSequence';
import { FormFX } from './FormFX';
import { LiquidLayer } from './LiquidLayer';
import { useTransitionSound } from '@/hooks/useTransitionSound';
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
  const label = useRef<HTMLElement>(null);
  useEffect(() => { let frame = 0, shown = 0; const draw = () => {
    if (ref.current) {
      const el = ref.current; el.style.transform = `translate(${handSignal.x * innerWidth}px, ${handSignal.y * innerHeight}px)`; el.style.opacity = handSignal.visible ? '1' : '0';
      el.dataset.pinch = String(handSignal.pinching); el.dataset.point = String(handSignal.pointing); el.style.setProperty('--dwell', handSignal.dwell.toFixed(3));
      // Each recognised gesture flashes its name beside the cursor with a ripple.
      if (handSignal.pulse !== shown) { shown = handSignal.pulse; if (label.current) label.current.textContent = handSignal.label; el.classList.remove('pulse'); void el.offsetWidth; el.classList.add('pulse'); }
    }
    frame = requestAnimationFrame(draw); }; frame = requestAnimationFrame(draw); return () => cancelAnimationFrame(frame); }, []);
  return <div ref={ref} className="hand-cursor" aria-hidden="true"><span /><i /><b className="dwell-ring" /><em className="gesture-label" ref={label} /></div>;
}
export function Nexus() {
  const [ready, setReady] = useState(false);
  const renderer = useNexus(s => s.renderer), expanded = useNexus(s => s.expanded), presenting = useNexus(s => s.presenting), pinned = useNexus(s => s.pinned), help = useNexus(s => s.help), launcher = useNexus(s => s.launcher);
  const inProject = useProject(s => !!s.focused);
  const { start, stop } = useHandTracking(); const toggleAudio = useAudio(); useControls(); useAmbient(); useTransitionSound();
  const assistant = useAssistantController();
  const gaze = useGazeTracking();
  const formPhase = useForm(s => s.phase);
  const aiLive = useAssistant(s => s.visible || s.status === 'Thinking' || s.status === 'Streaming' || s.status === 'Speaking');
  // Gaze tracking only makes sense while Zeno is embodied; stop it otherwise.
  useEffect(() => { if (formPhase === 'NORMAL') gaze.stop(); }, [formPhase, gaze]);
  useEffect(() => {
    try { const canvas = document.createElement('canvas'); if (!canvas.getContext('webgl2')) useNexus.setState({ renderer: 'fallback', gpu: 'Unavailable' }); }
    catch { useNexus.setState({ renderer: 'fallback', gpu: 'Unavailable' }); }
    useNexus.getState().log('ZENO 01 · spatial core initialized'); useNexus.getState().log('Orbit locked · input controls ready');
    const query = matchMedia('(prefers-reduced-motion: reduce)');
    const reduced = () => { if (query.matches) useNexus.setState({ drift: false }); }; reduced(); query.addEventListener('change', reduced);
    setReady(true); return () => query.removeEventListener('change', reduced);
  }, []);
  // Phase 4 AI Worlds: opening a module morphs the environment; closing restores
  // the base. While a project world is entered it owns the environment, so the
  // module morph stands down until the user exits it.
  useEffect(() => useNexus.subscribe((s, prev) => { if (s.expanded !== prev.expanded && !useProject.getState().focused) useWorld.getState().applyModule(s.expanded); }), []);
  const tracking = () => { const status = useNexus.getState().tracking; if (['loading', 'searching', 'tracking'].includes(status)) stop(); else void start(); };
  return <MotionConfig reducedMotion="user"><main className={`nexus ${expanded ? 'has-panel' : ''} ${formPhase !== 'NORMAL' ? 'form-embodied' : ''} ${inProject ? 'in-project' : ''} ${aiLive ? 'ai-live' : ''}`}><AppShell /><div className="titlebar-drag" aria-hidden="true" /><LiquidLayer /><div className="atmospheric-light" aria-hidden="true" /><div className="scene" aria-label="Spatial module orbit">{ready && (renderer === 'fallback' ? <FlatOrbit /> : <RenderBoundary fallback={<FlatOrbit />}><Scene /></RenderBoundary>)}</div><Ambience /><FormFX /><div className="scene-vignette" aria-hidden="true" /><WakeWave /><Hud onTracking={tracking} onAudio={() => void toggleAudio()} onAI={() => useAssistant.getState().wake()} /><FormControls controller={assistant} gaze={gaze} /><WorldControls /><ProjectWorldBanner /><Presentation /><HandCursor /><AnimatePresence>{pinned && formPhase === 'HUMANOID_ACTIVE' && !help && !launcher && <ModulePanel key="pinned" pinned />}{expanded && !presenting && !help && !launcher && <ModulePanel key="module" />}{help && <HelpPanel key="help" />}{launcher && <Launcher key="launcher" />}</AnimatePresence><Assistant controller={assistant} /><BootSequence /><div className="sr-only" aria-live="polite">{expanded ? `${expanded} focused` : 'Spatial orbit ready'}</div></main></MotionConfig>;
}
