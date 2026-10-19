'use client';
import { useEffect, useRef, useState } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { useForm, formSignal, cardMatrices } from '@/stores/form';
import { useNexus } from '@/stores/nexus';
import { voiceSignal } from '@/stores/assistant';
import { bakeBust, poissonSelect, type BakedSurface } from './bake';
import { buildNet } from './net';
import { captureSources } from './capture';
import { FORM_DURATION, FormTimeline, envelopes, smooth } from './timeline';
import { humanFragment, humanVertex, netFragment } from './shaders';
import { stepSpring } from '@/animations/spring';
import { gazeSignal } from './gaze';
import { fftSignal } from '@/ai/audio';
import { createFerrofluid, type Ferrofluid } from './ferrofluid';
const written = new Map<string, string>();
function cssVars(values: Record<string, number>) {
  for (const [key, value] of Object.entries(values)) {
    const text = value.toFixed(3); if (written.get(key) === text) continue;
    written.set(key, text); document.documentElement.style.setProperty(key, text);
  }
}
export function HumanForm() {
  const { gl, camera } = useThree();
  const target = useForm(s => s.target);
  const timeline = useRef(new FormTimeline()), surface = useRef<BakedSurface | null>(null);
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null), [net, setNet] = useState<THREE.BufferGeometry | null>(null);
  const material = useRef<THREE.ShaderMaterial>(null), underMaterial = useRef<THREE.ShaderMaterial>(null), netMaterial = useRef<THREE.ShaderMaterial>(null), building = useRef(false), mounted = useRef(true);
  const gaze = useRef({ x: 0, y: 0 }), headX = useRef({ value: 0, velocity: 0 }), headY = useRef({ value: 0, velocity: 0 });
  const ferro = useRef<Ferrofluid | null>(null);
  const dispersal = useRef({ value: 0, velocity: 0 }), jaw = useRef({ value: 0, velocity: 0 });
  const wide = useRef({ value: 0, velocity: 0 }), round = useRef({ value: 0, velocity: 0 }), eyeX = useRef({ value: 0, velocity: 0 }), eyeY = useRef({ value: 0, velocity: 0 });
  const saccade = useRef({ x: 0, y: 0, next: 0 });
  const uniforms = useRef({ uCards: { value: cardMatrices }, uTime: { value: 0 }, uPixelRatio: { value: 1 }, uSize: { value: .013 }, uHead: { value: new THREE.Vector2() }, uMouth: { value: new THREE.Vector2() }, uEye: { value: new THREE.Vector2() }, uJaw: { value: 0 }, uFlare: { value: .55 }, uReturn: { value: 0 }, uClock: { value: 0 }, uDisplace: { value: null as THREE.Texture | null }, uComputeSize: { value: 0 }, uUnder: { value: 0 }, uNet: { value: 0 } });
  const underUniforms = useRef(THREE.UniformsUtils.merge([uniforms.current, { uUnder: { value: 1 } }]));
  const netUniforms = useRef(THREE.UniformsUtils.merge([uniforms.current, { uNet: { value: 1 } }]));
  useEffect(() => {
    mounted.current = true;
    const move = (e: PointerEvent) => { gaze.current = { x: (e.clientX / innerWidth - .5) * .25, y: (e.clientY / innerHeight - .5) * .13 }; };
    window.addEventListener('pointermove', move);
    return () => { mounted.current = false; window.removeEventListener('pointermove', move); };
  }, []);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  useEffect(() => () => net?.dispose(), [net]);
  useEffect(() => () => { ferro.current?.dispose(); ferro.current = null; }, []);
  useEffect(() => {
    timeline.current.target = target;
    if (target !== 'human' || building.current || useForm.getState().ready) return;
    building.current = true;
    const report = (progress: string) => { if (mounted.current) useForm.setState({ progress }); };
    const count = surface.current?.count ?? (useNexus.getState().quality === 'high' ? 34000 : 22000);
    void (async () => {
      try {
        // The particle count is fixed from this point until the orbit returns.
        const [baked, captured] = await Promise.all([surface.current ?? bakeBust(gl, count, report), captureSources(count, camera, report)]);
        surface.current = baked;
        if (!mounted.current) return;
        const g = new THREE.BufferGeometry();
        // Reuse the same geometry for the complete forward and reverse journey.
        g.setAttribute('position', new THREE.BufferAttribute(baked.positions, 3));
        g.setAttribute('aNormal', new THREE.BufferAttribute(baked.normals, 3));
        g.setAttribute('aSource', new THREE.BufferAttribute(captured.positions, 3));
        g.setAttribute('aColor', new THREE.BufferAttribute(captured.colors, 3));
        g.setAttribute('aCard', new THREE.BufferAttribute(captured.cards, 1));
        // Eye lights are part of this buffer, not a separately animated mesh.
        for (let i = 0; i < 2; i++) { const at = count - 1 - i; baked.positions.set([i ? -.115 : .115, .752, .3], at * 3); baked.normals.set([0, 0, 1], at * 3); baked.occlusion[at] = 1; captured.seeds[at] = 2; }
        g.setAttribute('aAO', new THREE.BufferAttribute(baked.occlusion, 1));
        g.setAttribute('aSeed', new THREE.BufferAttribute(captured.seeds, 1));
        uniforms.current.uSize.value = .024 * Math.sqrt(20000 / count);
        // GPGPU ferrofluid: a square displacement field, one texel per particle.
        // Each particle gets its UV into that field; the shader samples it to
        // perturb the surface like magnetic fluid in zero-g.
        const side = Math.ceil(Math.sqrt(count));
        const compute = new Float32Array(count * 2);
        for (let i = 0; i < count; i++) { compute[i * 2] = ((i % side) + .5) / side; compute[i * 2 + 1] = (Math.floor(i / side) + .5) / side; }
        g.setAttribute('aCompute', new THREE.BufferAttribute(compute, 2));
        uniforms.current.uComputeSize.value = side;
        ferro.current?.dispose();
        try { ferro.current = createFerrofluid(gl, side, baked.positions, count); } catch { ferro.current = null; uniforms.current.uComputeSize.value = 0; }
        // The net: an even spread of knots across the face, each tied to its
        // nearest neighbours. Its lines share every attribute with the particles,
        // so the mouth, head turns and transitions move the net too.
        report('Weaving the net');
        const knots = await poissonSelect(baked.positions.subarray(0, (count - 2) * 3), useNexus.getState().quality === 'high' ? 6500 : 4800);
        const node = new Float32Array(count); for (const k of knots) node[k] = 1;
        g.setAttribute('aNode', new THREE.BufferAttribute(node, 1));
        const lines = new THREE.BufferGeometry();
        for (const [name, attribute] of Object.entries(g.attributes)) lines.setAttribute(name, attribute);
        lines.setIndex(new THREE.BufferAttribute(buildNet(baked.positions, knots, 4, .045), 1));
        if (!mounted.current) return;
        setNet(lines); setGeometry(g); useForm.setState({ ready: true, progress: '' });
      } catch (error) {
        if (mounted.current) useForm.setState({ target: 'spatial', error: error instanceof Error ? error.message : 'Human form could not start. Please retry.', progress: '' });
      } finally { building.current = false; }
    })();
  }, [target, gl, camera]);
  useFrame((state, delta) => {
    const time = timeline.current.step(delta, useForm.getState().ready), e = envelopes(time);
    // Returning disperses into motes instead of rewinding; a new forward request
    // mid-return pulls them straight back together.
    const returning = timeline.current.target === 'spatial' && time > 0;
    if (time === 0) Object.assign(dispersal.current, { value: 0, velocity: 0 });
    const scatter = THREE.MathUtils.clamp(stepSpring(dispersal.current, returning ? 1 : 0, Math.min(delta, .05), 120, 22), 0, 1);
    Object.assign(formSignal, { time, dim: e.dim, dissolve: e.dissolve, presence: e.presence, ignite: e.ignite, scan: e.scan, returning: scatter });
    if (useForm.getState().phase !== timeline.current.phase) useForm.setState({ phase: timeline.current.phase, ...(timeline.current.phase === 'NORMAL' ? { ready: false } : {}) });
    // Screen-space transition effects (FormFX) read these; only write changes.
    const wave = smooth(3.0, 4.9, time), forward = 1 - scatter;
    cssVars({ '--form-dissolve': e.dissolve, '--form-presence': e.presence, '--form-time': time / FORM_DURATION, '--form-ignite': e.ignite * forward,
      '--form-wave': wave, '--form-wave-o': wave * (1 - wave) * 4 * forward, '--form-scan': e.scan, '--form-scan-o': e.scan * (1 - e.scan) * 4 * forward,
      '--form-return-o': scatter * Math.sin(Math.PI * Math.min(1, time / FORM_DURATION)) });
    if (material.current) {
      material.current.uniforms.uTime.value = time;
      material.current.uniforms.uReturn.value = scatter;
      material.current.uniforms.uClock.value = state.clock.elapsedTime;
      material.current.uniforms.uPixelRatio.value = gl.getPixelRatio();
      // Webcam gaze (FaceMesh) drives the neck when a face is tracked; the
      // pointer is the fallback. Scaled into a natural neck range.
      const targetX = e.presence ? (gazeSignal.active ? gazeSignal.yaw * .32 : gaze.current.x) : 0;
      const targetY = e.presence ? (gazeSignal.active ? gazeSignal.pitch * .2 : gaze.current.y) : 0;
      const yaw = stepSpring(headX.current, targetX, delta, 45, 15);
      const pitch = stepSpring(headY.current, targetY, delta, 45, 15);
      material.current.uniforms.uHead.value.set(yaw, pitch);
      // Speaking jaw from the voice envelope; low FFT band adds cymatic ripple.
      // The mouth follows the voice envelope through a quick spring so syllables
      // open and close it naturally instead of snapping.
      const speech = Math.min(1, Math.max(voiceSignal.level, fftSignal.bands[0] * 1.1));
      material.current.uniforms.uJaw.value = THREE.MathUtils.clamp(stepSpring(jaw.current, speech, Math.min(delta, .05), 420, 30), 0, 1);
      // Lip shape: bright high-frequency sounds widen the mouth, low dark ones
      // round it. Without a spectrum (browser voice) a gentle pseudo-random
      // shape keeps the lips from moving like a hinge.
      const b = fftSignal.bands, t = state.clock.elapsedTime, dt = Math.min(delta, .05);
      const spectral = b[1] + b[2] + b[3] + b[4] > .02;
      const bright = spectral ? THREE.MathUtils.clamp(((b[3] + b[4]) - (b[1] + b[2])) * 2.5, -1, 1) : Math.sin(t * 7.3) * Math.sin(t * 2.9);
      material.current.uniforms.uMouth.value.set(stepSpring(wide.current, Math.max(0, bright) * speech, dt, 300, 26), stepSpring(round.current, Math.max(0, -bright) * speech, dt, 300, 26));
      // Eyes: small saccades every few seconds plus a hint of the pointer.
      if (t > saccade.current.next) saccade.current = { x: (Math.random() - .5) * .5, y: (Math.random() - .5) * .3, next: t + 1.2 + Math.random() * 2.8 };
      material.current.uniforms.uEye.value.set(stepSpring(eyeX.current, saccade.current.x + gaze.current.x * 1.5, dt, 900, 45), stepSpring(eyeY.current, saccade.current.y - gaze.current.y * 1.5, dt, 900, 45));
      material.current.uniforms.uFlare.value = gazeSignal.active ? 1 : .55;
      // Advance the ferrofluid GPGPU simulation and hand its texture to the shader.
      if (ferro.current) {
        // A low idle energy keeps the surface alive and the ignition surge ripples
        // it; speech no longer shakes the body (only the mouth moves).
        ferro.current.step(delta, .05 * e.presence + e.ignite * .5, e.presence > 0.1 || e.ignite > .05);
        material.current.uniforms.uDisplace.value = ferro.current.texture;
      }
      // The under-skin material mirrors every live value except its own flag.
      for (const mirror of [underMaterial.current?.uniforms, netMaterial.current?.uniforms]) if (mirror) for (const key in material.current.uniforms) if (key !== 'uUnder' && key !== 'uNet' && mirror[key]) mirror[key].value = material.current.uniforms[key].value;
    }
  }, -2);
  return geometry ? <>
    <points geometry={geometry} frustumCulled={false}><shaderMaterial ref={material} uniforms={uniforms.current} vertexShader={humanVertex} fragmentShader={humanFragment} transparent={false} depthWrite depthTest toneMapped={false} /></points>
    <points geometry={geometry} frustumCulled={false} renderOrder={-1}><shaderMaterial ref={underMaterial} uniforms={underUniforms.current} vertexShader={humanVertex} fragmentShader={humanFragment} transparent={false} depthWrite depthTest colorWrite={false} toneMapped={false} /></points>
    {net && <lineSegments geometry={net} frustumCulled={false} renderOrder={1}><shaderMaterial ref={netMaterial} uniforms={netUniforms.current} vertexShader={humanVertex} fragmentShader={netFragment} transparent depthWrite={false} depthTest blending={THREE.AdditiveBlending} toneMapped={false} /></lineSegments>}
  </> : null;
}
