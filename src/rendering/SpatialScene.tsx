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
import { ModuleBubble } from '@/components/ModuleCard';
import { modules, wrapIndex, type NexusModule } from '@/lib/modules';
import { dragSignal, handSignal, shockSignal, useNexus } from '@/stores/nexus';
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
import { CoreOrb } from './CoreOrb';

const moduleIds = modules.map(m => m.id);
const sphereGeometry = new THREE.SphereGeometry(1.05, 48, 32), coreGeometry = new THREE.SphereGeometry(.3, 24, 16);
// The module spheres hang off the central orb on invisible tethers.
const ORB = new THREE.Vector3(0, .6, -3.5);
// Pointer position in normalised device coordinates, tracked over the whole
// window (the HTML bubbles sit above the canvas and would hide it from R3F).
const pointer = { x: 9, y: 9 };
if (typeof window !== 'undefined') addEventListener('pointermove', e => { pointer.x = e.clientX / innerWidth * 2 - 1; pointer.y = -(e.clientY / innerHeight * 2 - 1); }, { passive: true });
const projected = new THREE.Vector3();
const reducedMotion = () => typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
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
  const tether = useRef<{ p: THREE.Vector3 | null; v: THREE.Vector3 }>({ p: null, v: new THREE.Vector3() });
  const core = useRef<THREE.MeshBasicMaterial>(null);
  const shockSeen = useRef(0);
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
    // Spheres circle the orb on a gently tilted ring, each at its own height.
    const radius = 4.3 * state.depth;
    // Mouse drag pulls the sphere toward the pointer; others part around the cursor.
    const mouse = dragSignal.id === module.id, mx = mouse ? dragSignal.dx * 9 : 0, my = mouse ? -dragSignal.dy * 6 : 0;
    let px = 0, py = 0;
    if (tether.current.p && !mouse && state.hovered !== module.id) {
      projected.copy(tether.current.p).project(frameState.camera);
      const ddx = projected.x - pointer.x, ddy = projected.y - pointer.y, d = Math.hypot(ddx, ddy * .6);
      if (d < .28 && d > .0001) { const push = (1 - d / .28) * .55; px = ddx / d * push; py = ddy / d * push; }
    }
    let ox = Math.sin(a) * radius + hx + mx + px, oz = Math.cos(a) * radius + ORB.z;
    let oy = ORB.y - .05 - Math.cos(a) * .95 + Math.sin(ordinal * 2.4) * .18 + (Math.sin(time.current * .4 + ordinal) - Math.sin(ordinal)) * .08 + hy + my + py + raised;
    ox += (outer[0] - ox) * fl; oy += (outer[1] - oy) * fl; oz += (outer[2] - oz) * fl;
    // Liquid float: every card bobs and sways on its own slow current.
    const t = frameState.clock.elapsedTime, float = (reducedMotion() ? 0 : 1) * (1 - g) * (1 - fl);
    oy += (Math.sin(t * .8 + ordinal * 1.7) * .11 + Math.sin(t * 1.9 + ordinal) * .025) * float;
    oy += Math.sin(t * .6) * .08 * float; // ride the orb's own bob
    // Invisible tether: each sphere chases its place through a soft, slightly
    // bouncy spring (so it lags and swings), and can never drift further from
    // the orb than its string allows; let go and it swings back.
    const target = new THREE.Vector3(ox + (cx - ox) * g, oy + (cy - oy) * g, oz + (cz - oz) * g), tie = tether.current, step = Math.min(dt, .05);
    if (!tie.p) tie.p = target.clone();
    // A double-click shockwave flings every sphere outward; the strings reel them back.
    if (shockSignal.at !== shockSeen.current) { shockSeen.current = shockSignal.at; tie.v.add(tie.p.clone().sub(ORB).setY(.4).normalize().multiplyScalar(9 + Math.sin(ordinal * 3.1) * 2)); }
    tie.v.addScaledVector(target.clone().sub(tie.p), 34 * step).multiplyScalar(Math.max(0, 1 - 6.5 * step));
    tie.p.addScaledVector(tie.v, step);
    const rope = radius + 1.7, off = tie.p.clone().sub(ORB);
    if (g < .02 && fl < .02 && off.length() > rope) { off.setLength(rope); tie.p.copy(ORB).add(off); tie.v.multiplyScalar(.5); }
    group.current.position.copy(tie.p);
    group.current.rotation.set(Math.sin(t * .7 + ordinal * 2.1) * .04 * float, fl * .4 + Math.sin(t * .5 + ordinal * 2.3) * .05 * float, fl * Math.sin(ordinal) * .25);
    group.current.scale.setScalar(.6 * (1 + (active ? .18 : 0) + raised * .8));
    if (core.current) core.current.opacity = (.22 + Math.sin(t * 2.1 + ordinal) * .08 + (active ? .14 : 0)) * (1 - formSignal.dissolve);
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
    group.current.visible = (frontal > -.6 || g > .02 || fl > .02) && (!expanded || (presentation.active && presentation.module === module.id && presentation.time < 1.5)) && fade > .006;
    if (html.current) { html.current.style.opacity = String(THREE.MathUtils.smoothstep(frontal, -.45, .35) * fade); html.current.style.display = group.current.visible ? '' : 'none'; }
    if (material.current) {
      const warned = state.warnings.includes(module.id);
      cardTint(module.accent, frontal, warned, tint.current);
      material.current.emissive.copy(tint.current.color);
      material.current.emissiveIntensity = tint.current.intensity * (1 - rec) * dim;
      material.current.opacity = .55 * fade;
    }
  });
  return <group ref={group} scale={.72}>
    <mesh geometry={coreGeometry}><meshBasicMaterial ref={core} color={module.accent} transparent opacity={.6} blending={THREE.AdditiveBlending} depthWrite={false} toneMapped={false} /></mesh>
    {/* Tessellated face so the tension-bend vertex shader stays smooth. */}
    <mesh geometry={sphereGeometry}><meshStandardMaterial ref={setMaterial} color="#0d2c20" metalness={.35} roughness={.12} transparent opacity={.42} emissive={module.accent} emissiveIntensity={.05} depthWrite={false} /></mesh>
    <Html transform wrapperClass="spatial-card-root" position={[0, 0, 1.06]} distanceFactor={4} zIndexRange={[20, 0]}><div ref={html}><ModuleBubble module={module} active={active} ordinal={ordinal} /></div></Html>
  </group>;
}
function World() {
  const angle = useRef(2 * Math.PI * 2 / modules.length);
  const orbit = useRef({ value: angle.current, velocity: 0 });
  const drift = useRef({ value: 0, velocity: 0 });
  const time = useRef(0);
  const zoom = useRef({ value: 1, velocity: 0 });
  const groupAmt = useRef({ value: 0, velocity: 0 }), projectAmt = useRef({ value: 0, velocity: 0 });
  const lookX = useRef({ value: 0, velocity: 0 }), lookY = useRef({ value: 0, velocity: 0 });
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
  useFrame((frameState, dt) => {
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
    // Gentle parallax: the camera leans toward the pointer so the space feels alive.
    const still = normal && !presentation.active && !state.dragging;
    const px = stepSpring(lookX.current, still ? frameState.pointer.x * .45 : 0, dt, 22, 10), py = stepSpring(lookY.current, still ? frameState.pointer.y * .22 : 0, dt, 22, 10);
    camera.position.set(Math.sin(time.current * .12) * .06 + shot.dx + px, .65 + Math.sin(time.current * .15) * .035 + shot.dy + py, baseZ + shot.dz);
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
  return <><HumanForm /><CoreOrb /><PresentingHand /><WorldGeometry time={time} /><ProjectWorld time={time} /><WeatherEffects time={time} /><Atmosphere motionTime={time} /><FloorCaustics time={time} />{modules.map((module, i) => <Card key={module.id} module={module} ordinal={i} angle={angle} time={time} />)}
    <EffectComposer multisampling={0}><Bloom intensity={quality === 'high' ? .35 : 0} luminanceThreshold={.85} mipmapBlur /><WorldGrade /></EffectComposer>
  </>;
}
export default function SpatialScene() {
  return <Canvas camera={{ position: [0, .65, 10], fov: 45, near: .1, far: 70 }} dpr={[1, 1.5]} gl={{ antialias: true, alpha: true, powerPreference: 'high-performance' }}><Suspense fallback={null}><World /></Suspense></Canvas>;
}
