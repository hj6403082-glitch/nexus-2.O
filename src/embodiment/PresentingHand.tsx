'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { useForm } from '@/stores/form';
import { useNexus } from '@/stores/nexus';
import { bakeBust } from './bake';
import { handField, panelAnchor } from './hand';
import { smooth } from './timeline';
import { humanFragment } from './shaders';
const vertex = `attribute vec3 aNormal;attribute float seed;uniform float rise;uniform float reveal;uniform float ratio;
varying vec3 vColor;varying vec3 vView;varying float vRadius;varying float vVisibility;
void main(){vec3 p=position*.65;p+=vec3(1.45,-2.8+rise*2.15,3.);
vec3 n=normalize(aNormal);float key=clamp(dot(n,normalize(vec3(-.5,.7,1.))),0.,1.);
vColor=mix(vec3(.025,.10,.20),vec3(.3,.62,.82),key);vVisibility=step(seed,reveal);vRadius=.017;
vec4 mv=modelViewMatrix*vec4(p,1.);vView=mv.xyz;gl_Position=projectionMatrix*mv;gl_PointSize=clamp(.034*ratio*700./max(.2,-mv.z),1.,24.);}`;
export function PresentingHand() {
  const { gl, camera, size } = useThree(), phase = useForm(s => s.phase), expanded = useNexus(s => s.expanded);
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null), building = useRef(false), time = useRef(10), mounted = useRef(true);
  const uniforms = useMemo(() => ({ rise: { value: 0 }, reveal: { value: 0 }, ratio: { value: 1 } }), []);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (phase === 'HUMANOID_ACTIVE' && expanded) time.current = 0; }, [expanded, phase]);
  useEffect(() => {
    if (phase !== 'HUMANOID_ACTIVE' || geometry || building.current) return;
    building.current = true;
    void bakeBust(gl, 4500, () => {}, handField).then(surface => {
      if (!mounted.current) return; const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(surface.positions, 3)); g.setAttribute('aNormal', new THREE.BufferAttribute(surface.normals, 3));
      const seed = new Float32Array(surface.count); for (let i = 0; i < seed.length; i++) seed[i] = ((i * 7919) % 10007) / 10007;
      g.setAttribute('seed', new THREE.BufferAttribute(seed, 1)); setGeometry(g);
    }).catch(() => { /* The readable DOM panel remains available if baking fails. */ }).finally(() => { building.current = false; });
  }, [phase, geometry, gl]);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  useFrame((_, dt) => {
    time.current = Math.min(10, time.current + Math.min(dt, .05)); const t = time.current;
    const rise = smooth(0, 1.2, t) * (1 - smooth(2.5, 3.8, t));
    uniforms.rise.value = rise; uniforms.reveal.value = phase === 'HUMANOID_ACTIVE' && expanded ? smooth(0, .5, t) * (1 - smooth(3.1, 3.8, t)) : 0; uniforms.ratio.value = gl.getPixelRatio();
    const anchor = new THREE.Vector3(1.45, -.1 + rise * .5, 3).project(camera);
    panelAnchor.x = (anchor.x + 1) * size.width / 2; panelAnchor.y = (1 - anchor.y) * size.height / 2; panelAnchor.lift = geometry && t < 2.5 ? rise : 0;
  });
  return geometry ? <points geometry={geometry} frustumCulled={false}><shaderMaterial uniforms={uniforms} vertexShader={vertex} fragmentShader={humanFragment} depthWrite depthTest toneMapped={false} /></points> : null;
}
