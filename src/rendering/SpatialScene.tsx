'use client';
import { Suspense, useEffect, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Html, RoundedBox } from '@react-three/drei';
import { Bloom, EffectComposer } from '@react-three/postprocessing';
import * as THREE from 'three';
import { Atmosphere } from './Atmosphere';
import { WorldGrade } from './WorldGrade';
import { WorldGeometry } from './WorldGeometry';
import { presentation, presentationEnvelopes } from '@/animations/presentation';
import { ModuleCard } from '@/components/ModuleCard';
import { modules, wrapIndex, type NexusModule } from '@/lib/modules';
import { handSignal, useNexus } from '@/stores/nexus';
import { stepSpring } from '@/animations/spring';
import { HumanForm } from '@/embodiment/HumanForm';
import { PresentingHand } from '@/embodiment/PresentingHand';
import { cardMatrices, formSignal, useForm } from '@/stores/form';

function Card({ module, ordinal, angle, time }: { module: NexusModule; ordinal: number; angle: React.RefObject<number>; time: React.RefObject<number> }) {
  const group = useRef<THREE.Group>(null);
  const html = useRef<HTMLDivElement>(null);
  const index = useNexus(s => s.index), expanded = useNexus(s => s.expanded);
  const active = wrapIndex(index) === ordinal;
  const dragX = useRef({ value: 0, velocity: 0 }), dragY = useRef({ value: 0, velocity: 0 });
  const hover = useRef({ value: 0, velocity: 0 });
  const material = useRef<THREE.MeshStandardMaterial>(null);
  useFrame((_, dt) => {
    if (!group.current) return;
    const a = ordinal * Math.PI * 2 / modules.length - angle.current;
    const state = useNexus.getState(), grabbed = state.dragging === module.id;
    const hx = stepSpring(dragX.current, grabbed ? (handSignal.x - .5) * 8 : 0, dt);
    const hy = stepSpring(dragY.current, grabbed ? (.5 - handSignal.y) * 5 : 0, dt);
    const raised = stepSpring(hover.current, state.hovered === module.id ? .12 : 0, dt, 140, 23);
    group.current.position.set(Math.sin(a) * 5.2 + hx, (Math.sin(time.current * .4 + ordinal) - Math.sin(ordinal)) * .08 + hy + raised, Math.cos(a) * 5.2 - 3.5);
    group.current.rotation.y = Math.sin(a) * .18;
    group.current.updateWorldMatrix(true, false);
    cardMatrices[ordinal].copy(group.current.matrixWorld);
    const frontal = Math.cos(a);
    group.current.visible = frontal > .1 && !expanded && formSignal.dissolve < .999;
    if (html.current) { html.current.style.opacity = String(Math.max(.25, (frontal + 1) / 2) * (1 - formSignal.dissolve)); html.current.style.display = group.current.visible ? '' : 'none'; }
    if (material.current) { const centered = Math.pow(Math.max(0, frontal), 24); material.current.emissive.set(centered > .5 ? '#948257' : module.accent); material.current.emissiveIntensity = .04 + centered * .06; material.current.opacity = .55 * (1 - formSignal.dissolve); }
  });
  return <group ref={group} scale={.72}>
    <RoundedBox args={[3.03, 3.66, .045]} radius={.08} smoothness={4}><meshStandardMaterial ref={material} color="#0b1724" metalness={.65} roughness={.27} transparent opacity={.55} emissive={module.accent} emissiveIntensity={.05} /></RoundedBox>
    <Html transform wrapperClass="spatial-card-root" position={[0, 0, .04]} distanceFactor={4} zIndexRange={[20, 0]}><div ref={html}><ModuleCard module={module} active={active} ordinal={ordinal} /></div></Html>
  </group>;
}
function World() {
  const angle = useRef(2 * Math.PI * 2 / modules.length);
  const orbit = useRef({ value: angle.current, velocity: 0 });
  const drift = useRef({ value: 0, velocity: 0 });
  const time = useRef(0);
  const zoom = useRef({ value: 1, velocity: 0 });
  const frameCount = useRef(0), sampleTime = useRef(0), lowSamples = useRef(0);
  const { camera, gl, setDpr } = useThree();
  const quality = useNexus(s => s.quality);
  useEffect(() => {
    const context = gl.getContext();
    const ext = context.getExtension('WEBGL_debug_renderer_info');
    const gpu = ext ? String(context.getParameter(ext.UNMASKED_RENDERER_WEBGL)) : 'WebGL 2';
    useNexus.setState({ gpu, renderer: 'webgl' });
    const lost = (event: Event) => { event.preventDefault(); useNexus.setState({ renderer: 'fallback' }); };
    gl.domElement.addEventListener('webglcontextlost', lost);
    return () => gl.domElement.removeEventListener('webglcontextlost', lost);
  }, [gl]);
  useFrame((_, dt) => {
    const state = useNexus.getState();
    angle.current = stepSpring(orbit.current, state.index * Math.PI * 2 / modules.length, dt, 65, 17);
    const amount = stepSpring(drift.current, state.drift && !state.frozen && useForm.getState().phase === 'NORMAL' ? 1 : 0, dt, 18, 9);
    time.current += Math.min(dt, .05) * amount;
    // With LOCKED at boot, time is exactly 0 and camera is exactly stationary.
    camera.position.x = Math.sin(time.current * .12) * .06;
    camera.position.y = .65 + Math.sin(time.current * .15) * .035;
    camera.position.z = 10 + (1 - stepSpring(zoom.current, useForm.getState().phase === 'NORMAL' ? handSignal.zoom : 1, dt)) * 3 - (presentation.active ? presentationEnvelopes(presentation.time).push * .35 : 0);
    camera.lookAt(0, .2, -2);
    if (document.hidden || dt > .25) { frameCount.current = 0; sampleTime.current = 0; lowSamples.current = 0; if (state.fps) useNexus.setState({ fps: 0 }); return; }
    frameCount.current++; sampleTime.current += dt;
    if (sampleTime.current >= 1.5) {
      const fps = Math.round(frameCount.current / sampleTime.current);
      useNexus.setState({ fps });
      if (fps < 38 && useForm.getState().phase === 'NORMAL') lowSamples.current++; else lowSamples.current = 0;
      if (lowSamples.current >= 3 && state.quality === 'high') { useNexus.setState({ quality: 'low' }); setDpr(1); state.log('Adaptive render · reduced effects'); }
      frameCount.current = 0; sampleTime.current = 0;
    }
  });
  return <><HumanForm /><PresentingHand /><WorldGeometry time={time} /><Atmosphere motionTime={time} />{modules.map((module, i) => <Card key={module.id} module={module} ordinal={i} angle={angle} time={time} />)}
    <EffectComposer multisampling={0}><Bloom intensity={quality === 'high' ? .35 : 0} luminanceThreshold={.85} mipmapBlur /><WorldGrade /></EffectComposer>
  </>;
}
export default function SpatialScene() {
  return <Canvas camera={{ position: [0, .65, 10], fov: 45, near: .1, far: 70 }} dpr={[1, 1.5]} gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}><Suspense fallback={null}><World /></Suspense></Canvas>;
}
