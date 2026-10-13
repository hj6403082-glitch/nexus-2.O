'use client';
import { useEffect, useRef, useState } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { useForm, formSignal, cardMatrices } from '@/stores/form';
import { useNexus } from '@/stores/nexus';
import { voiceSignal } from '@/stores/assistant';
import { bakeBust, type BakedSurface } from './bake';
import { captureSources } from './capture';
import { FormTimeline, envelopes } from './timeline';
import { humanFragment, humanVertex } from './shaders';
import { stepSpring } from '@/animations/spring';
import { gazeSignal } from './gaze';
import { fftSignal } from '@/ai/audio';
import { createFerrofluid, type Ferrofluid } from './ferrofluid';
export function HumanForm() {
  const { gl, camera } = useThree();
  const target = useForm(s => s.target);
  const timeline = useRef(new FormTimeline()), surface = useRef<BakedSurface | null>(null);
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null);
  const material = useRef<THREE.ShaderMaterial>(null), building = useRef(false), mounted = useRef(true);
  const gaze = useRef({ x: 0, y: 0 }), headX = useRef({ value: 0, velocity: 0 }), headY = useRef({ value: 0, velocity: 0 });
  const ferro = useRef<Ferrofluid | null>(null);
  const uniforms = useRef({ uCards: { value: cardMatrices }, uTime: { value: 0 }, uPixelRatio: { value: 1 }, uSize: { value: .013 }, uHead: { value: new THREE.Vector2() }, uJaw: { value: 0 }, uBands: { value: new Float32Array(8) }, uFlare: { value: .55 }, uDisplace: { value: null as THREE.Texture | null }, uComputeSize: { value: 0 } });
  useEffect(() => {
    mounted.current = true;
    const move = (e: PointerEvent) => { gaze.current = { x: (e.clientX / innerWidth - .5) * .25, y: (e.clientY / innerHeight - .5) * .13 }; };
    window.addEventListener('pointermove', move);
    return () => { mounted.current = false; window.removeEventListener('pointermove', move); };
  }, []);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  useEffect(() => () => { ferro.current?.dispose(); ferro.current = null; }, []);
  useEffect(() => {
    timeline.current.target = target;
    if (target !== 'human' || building.current || useForm.getState().ready) return;
    building.current = true;
    const report = (progress: string) => { if (mounted.current) useForm.setState({ progress }); };
    const count = surface.current?.count ?? (useNexus.getState().quality === 'high' ? 14000 : 9000);
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
        for (let i = 0; i < 2; i++) { const at = count - 1 - i; baked.positions.set([i ? -.116 : .116, .74, .37], at * 3); baked.normals.set([0, 0, 1], at * 3); captured.seeds[at] = 2; }
        g.setAttribute('aSeed', new THREE.BufferAttribute(captured.seeds, 1));
        uniforms.current.uSize.value = count > 10000 ? .019 : .024;
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
        setGeometry(g); useForm.setState({ ready: true, progress: '' });
      } catch (error) {
        if (mounted.current) useForm.setState({ target: 'spatial', error: error instanceof Error ? error.message : 'Human form could not start. Please retry.', progress: '' });
      } finally { building.current = false; }
    })();
  }, [target, gl, camera]);
  useFrame((_, delta) => {
    const time = timeline.current.step(delta, useForm.getState().ready), e = envelopes(time);
    Object.assign(formSignal, { time, dim: e.dim, dissolve: e.dissolve, presence: e.presence });
    if (useForm.getState().phase !== timeline.current.phase) useForm.setState({ phase: timeline.current.phase, ...(timeline.current.phase === 'NORMAL' ? { ready: false } : {}) });
    document.documentElement.style.setProperty('--form-dissolve', String(e.dissolve));
    document.documentElement.style.setProperty('--form-presence', String(e.presence));
    if (material.current) {
      material.current.uniforms.uTime.value = time;
      material.current.uniforms.uPixelRatio.value = gl.getPixelRatio();
      // Webcam gaze (FaceMesh) drives the neck when a face is tracked; the
      // pointer is the fallback. Scaled into a natural neck range.
      const targetX = e.presence ? (gazeSignal.active ? gazeSignal.yaw * .32 : gaze.current.x) : 0;
      const targetY = e.presence ? (gazeSignal.active ? gazeSignal.pitch * .2 : gaze.current.y) : 0;
      const yaw = stepSpring(headX.current, targetX, delta, 45, 15);
      const pitch = stepSpring(headY.current, targetY, delta, 45, 15);
      material.current.uniforms.uHead.value.set(yaw, pitch);
      // Speaking jaw from the voice envelope; low FFT band adds cymatic ripple.
      material.current.uniforms.uJaw.value = Math.max(voiceSignal.level, fftSignal.bands[0] * .8);
      for (let i = 0; i < 8; i++) material.current.uniforms.uBands.value[i] = fftSignal.bands[i];
      material.current.uniforms.uFlare.value = gazeSignal.active ? 1 : .55;
      // Advance the ferrofluid GPGPU simulation and hand its texture to the shader.
      if (ferro.current) {
        ferro.current.step(delta, Math.max(voiceSignal.level, fftSignal.level), e.presence > 0.1);
        material.current.uniforms.uDisplace.value = ferro.current.texture;
      }
    }
  }, -2);
  return geometry ? <points geometry={geometry} frustumCulled={false}><shaderMaterial ref={material} uniforms={uniforms.current} vertexShader={humanVertex} fragmentShader={humanFragment} transparent={false} depthWrite depthTest toneMapped={false} /></points> : null;
}
