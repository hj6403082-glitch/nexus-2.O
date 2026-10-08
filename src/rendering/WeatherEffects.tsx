'use client';
import { useEffect, useMemo, type RefObject } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useWorld } from '@/stores/world';
import { formSignal } from '@/stores/form';

export function WeatherEffects({ time }: { time: RefObject<number> }) {
  const code = useWorld(s => s.weatherCode);
  const rain = (code >= 51 && code <= 67) || (code >= 80 && code <= 82) || code >= 95;
  const geometry = useMemo(() => {
    const positions = new Float32Array(320 * 6);
    for (let i = 0; i < 320; i++) {
      const x = ((i * 83) % 317) / 317 * 22 - 11;
      const y = ((i * 137) % 311) / 311 * 14 - 7;
      const z = -3 - ((i * 53) % 307) / 307 * 12;
      positions.set([x, y, z, x, y, z], i * 6);
    }
    const result = new THREE.BufferGeometry(); result.setAttribute('position', new THREE.BufferAttribute(positions, 3));
    result.setAttribute('tip', new THREE.BufferAttribute(Float32Array.from({ length: 640 }, (_, i) => i % 2), 1)); return result;
  }, []);
  const uniforms = useMemo(() => ({ clock: { value: 0 }, opacity: { value: 0 } }), []);
  useEffect(() => () => geometry.dispose(), [geometry]);
  useFrame(() => { uniforms.clock.value = time.current; uniforms.opacity.value = rain ? .20 * (1 - formSignal.dissolve) : 0; });
  return <lineSegments geometry={geometry} frustumCulled={false}><shaderMaterial transparent depthWrite={false} uniforms={uniforms}
    vertexShader="uniform float clock; attribute float tip; void main(){vec3 p=position; p.y=mod(p.y-clock*2.8+7.,14.)-7.+tip*.19; p.x+=tip*.035; gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.); }"
    fragmentShader="uniform float opacity; void main(){gl_FragColor=vec4(.43,.65,.78,opacity);}"
  /></lineSegments>;
}
