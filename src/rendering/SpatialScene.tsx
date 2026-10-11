'use client';
import { Suspense, useCallback, useEffect, useRef } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import { Bloom, EffectComposer } from '@react-three/postprocessing';
import * as THREE from 'three';
import { Atmosphere } from './Atmosphere';
import { WorldGrade } from './WorldGrade';
import { WorldGeometry } from './WorldGeometry';
import { ProjectWorld } from './ProjectWorld';
import { WeatherEffects } from './WeatherEffects';
import { presentation, presentationEnvelopes } from '@/animations/presentation';
import { ModuleCard } from '@/components/ModuleCard';
import { modules, wrapIndex, type NexusModule } from '@/lib/modules';
import { handSignal, useNexus } from '@/stores/nexus';
import { stepSpring } from '@/animations/spring';
import { HumanForm } from '@/embodiment/HumanForm';
import { PresentingHand } from '@/embodiment/PresentingHand';
import { cardMatrices, formSignal, useForm } from '@/stores/form';
import { clusterMembers, clusterTarget, prismTarget } from './cluster';
import { cardTint, type CardTint } from './gold';
import { useProject } from '@/stores/project';
import { composeShot } from './camera';
import { stepEnvironment } from './environment';
import { FloorCaustics } from './FloorCaustics';
import { attachBend, createBendUniforms, driveBend } from './cardBend';
import { flungSlot } from './flick';

const moduleIds = modules.map(m => m.id);
const EMPTY: string[] = [];
function Card({ module, ordinal, angle, time }: { module: NexusModule; ordinal: number; angle: React.RefObject<number>; time: React.RefObject<number> }) {
  const group = useRef<THREE.Group>(null);
  const html = useRef<HTMLDivElement>(null);
  const index = useNexus(s => s.index), expanded = useNexus(s => s.expanded);
  const active = wrapIndex(index) === ordinal;
  const dragX = useRef({ value: 0, velocity: 0 }), dragY = useRef({ value: 0, velocity: 0 });
  const hover = useRef({ value: 0, velocity: 0 });
  const gather = useRef({ value: 0, velocity: 0 });
  const recede = useRef({ value: 0, velocity: 0 });
  const slot = useRef<[number, number, number]>([0, 2, -1.4]);
  const material = useRef<THREE.MeshStandardMaterial | null>(null);
  const bend = useRef(createBendUniforms());
  const fling = useRef({ value: 0, velocity: 0 });
  const tint = useRef<CardTint>({ color: new THREE.Color(), intensity: 0 });
  const setMaterial = useCallback((m: THREE.MeshStandardMaterial | null) => { material.current = m; if (m) attachBend(m, bend.current); }, []);
  useFrame((frameState, dt) => {
    if (!group.current) return;
    const a = ordinal * Math.PI * 2 / modules.length - angle.current;
    const state = useNexus.getState();
    // Dragging any grouped card carries the whole group with it.
    const grabbed = state.dragging === module.id || (state.grouped && state.dragging !== null && state.selected.includes(module.id) && state.selected.includes(state.dragging));
    const hx = stepSpring(dragX.current, grabbed ? (handSignal.x - .5) * 8 : 0, dt);
    const hy = stepSpring(dragY.current, grabbed ? (.5 - handSignal.y) * 5 : 0, dt);
    const raised = stepSpring(hover.current, state.hovered === module.id ? .12 : 0, dt, 140, 23);
    // Grouping lerps this card off its orbit slot into the cluster grid; a card
    // that leaves the group keeps its last slot and springs back (split = orbit
    // spring in reverse).
    const members = state.grouped ? clusterMembers(state.selected, moduleIds) : EMPTY;
    const rank = members.indexOf(module.id);
    // Data convergence arranges the group into a rotating 3D prism; otherwise a
    // flat gather grid.
    if (rank >= 0) slot.current = state.prism ? prismTarget(rank, members.length) : clusterTarget(rank, members.length);
    const g = stepSpring(gather.current, rank >= 0 ? 1 : 0, dt, 90, 20);
    let [cx, cy, cz] = slot.current;
    // The data prism rotates slowly for cross-analysis.
    if (state.prism && rank >= 0) {
      const spin = frameState.clock.elapsedTime * .3, cxr = cx, czr = cz + 1.4;
      cx = cxr * Math.cos(spin) + czr * Math.sin(spin);
      cz = -cxr * Math.sin(spin) + czr * Math.cos(spin) - 1.4;
    }
    // A flicked card flings out to a dimmed outer orbit ring; recall springs it
    // back. `fl` is the eased amount it has travelled to the outer ring.
    const flung = state.flung.includes(module.id);
    const fl = stepSpring(fling.current, flung ? 1 : 0, dt, 70, 16);
    const outer = flungSlot(ordinal, a);
    // Depth expansion scales the orbit radius out (workspace grows).
    const radius = 5.2 * state.depth;
    let ox = Math.sin(a) * radius + hx, oy = (Math.sin(time.current * .4 + ordinal) - Math.sin(ordinal)) * .08 + hy + raised, oz = Math.cos(a) * radius - 3.5;
    ox += (outer[0] - ox) * fl; oy += (outer[1] - oy) * fl; oz += (outer[2] - oz) * fl;
    group.current.position.set(ox + (cx - ox) * g, oy + (cy - oy) * g, oz + (cz - oz) * g);
    group.current.rotation.y = Math.sin(a) * .18 * (1 - g) + fl * .4;
    group.current.rotation.z = fl * Math.sin(ordinal) * .25;
    // Tension bending: bow the card toward the fingertip while it is dragged.
    const gx = THREE.MathUtils.clamp(hx * .35, -1.5, 1.5), gy = THREE.MathUtils.clamp(hy * .35, -1.8, 1.8);
    driveBend(bend.current, grabbed, gx, gy, dragX.current.velocity, dragY.current.velocity, dt);
    group.current.updateWorldMatrix(true, false);
    cardMatrices[ordinal].copy(group.current.matrixWorld);
    const frontal = Math.cos(a);
    // Entering a project world recedes the whole orbit so the floating island
    // is the subject; leaving it springs the orbit back.
    const rec = stepSpring(recede.current, useProject.getState().focused ? 1 : 0, dt, 60, 18);
    // Flung cards dim as they recede into the outer orbit ring.
    const dim = 1 - fl * .62;
    const fade = (1 - formSignal.dissolve) * (1 - rec) * dim;
    group.current.visible = (frontal > .1 || g > .02 || fl > .02) && (!expanded || (presentation.active && presentation.module === module.id && presentation.time < 1.5)) && fade > .006;
    if (html.current) { html.current.style.opacity = String(Math.max(.25, (frontal + 1) / 2) * fade); html.current.style.display = group.current.visible ? '' : 'none'; }
    if (material.current) {
      const warned = state.warnings.includes(module.id);
      cardTint(module.accent, frontal, warned, tint.current);
      material.current.emissive.copy(tint.current.color);
      material.current.emissiveIntensity = tint.current.intensity * (1 - rec) * dim;
      material.current.opacity = .55 * fade;
    }
  });
  return <group ref={group} scale={.72}>
    {/* Tessellated face so the tension-bend vertex shader stays smooth. */}
    <mesh><boxGeometry args={[3.03, 3.66, .045, 24, 28, 1]} /><meshStandardMaterial ref={setMaterial} color="#0b1724" metalness={.65} roughness={.27} transparent opacity={.55} emissive={module.accent} emissiveIntensity={.05} /></mesh>
    <Html transform wrapperClass="spatial-card-root" position={[0, 0, .04]} distanceFactor={4} zIndexRange={[20, 0]}><div ref={html}><ModuleCard module={module} active={active} ordinal={ordinal} /></div></Html>
  </group>;
}
function World() {
  const angle = useRef(2 * Math.PI * 2 / modules.length);
  const orbit = useRef({ value: angle.current, velocity: 0 });
  const drift = useRef({ value: 0, velocity: 0 });
  const time = useRef(0);
  const zoom = useRef({ value: 1, velocity: 0 });
  const groupAmt = useRef({ value: 0, velocity: 0 }), projectAmt = useRef({ value: 0, velocity: 0 });
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
    stepEnvironment(dt); // advance eased bridge-load for the thermal grade
    angle.current = stepSpring(orbit.current, state.index * Math.PI * 2 / modules.length, dt, 65, 17);
    const amount = stepSpring(drift.current, state.drift && !state.frozen && useForm.getState().phase === 'NORMAL' ? 1 : 0, dt, 18, 9);
    time.current += Math.min(dt, .05) * amount;
    // Cinematic shot composed from smooth amounts; all zero at boot (LOCKED,
    // nothing grouped or focused) so time=0 keeps the camera exactly stationary.
    const normal = useForm.getState().phase === 'NORMAL';
    const approach = presentation.active ? presentationEnvelopes(presentation.time).approach : 0;
    const grouped = stepSpring(groupAmt.current, normal && state.grouped ? 1 : 0, dt, 50, 16);
    const project = stepSpring(projectAmt.current, normal && useProject.getState().focused ? 1 : 0, dt, 45, 16);
    const shot = composeShot({ approach, grouped, project, arc: time.current * .25 });
    const baseZ = 10 + (1 - stepSpring(zoom.current, normal ? handSignal.zoom : 1, dt)) * 3 - (presentation.active ? presentationEnvelopes(presentation.time).push * .35 : 0);
    camera.position.set(Math.sin(time.current * .12) * .06 + shot.dx, .65 + Math.sin(time.current * .15) * .035 + shot.dy, baseZ + shot.dz);
    camera.lookAt(shot.lx, shot.ly, shot.lz);
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
  return <><HumanForm /><PresentingHand /><WorldGeometry time={time} /><ProjectWorld time={time} /><WeatherEffects time={time} /><Atmosphere motionTime={time} /><FloorCaustics time={time} />{modules.map((module, i) => <Card key={module.id} module={module} ordinal={i} angle={angle} time={time} />)}
    <EffectComposer multisampling={0}><Bloom intensity={quality === 'high' ? .35 : 0} luminanceThreshold={.85} mipmapBlur /><WorldGrade /></EffectComposer>
  </>;
}
export default function SpatialScene() {
  return <Canvas camera={{ position: [0, .65, 10], fov: 45, near: .1, far: 70 }} dpr={[1, 1.5]} gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}><Suspense fallback={null}><World /></Suspense></Canvas>;
}
