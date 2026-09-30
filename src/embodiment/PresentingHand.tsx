'use client';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import { useForm } from '@/stores/form';
import { useNexus } from '@/stores/nexus';
import { bakeBust } from './bake';
import { handField, panelAnchor, fingers, fingerForPoint } from './hand';
import { smooth } from './timeline';
import { humanFragment } from './shaders';
const vertex = `attribute vec3 aNormal;attribute float seed;attribute float finger;uniform float rise;uniform float reveal;uniform float ratio;uniform float curl;uniform vec3 origin;
varying vec3 vColor;varying vec3 vView;varying float vRadius;varying float vVisibility;
mat3 bend(float angle){float c=cos(angle),s=sin(angle);return mat3(1.,0.,0.,0.,c,s,0.,-s,c);}
void main(){vec3 p=position;vec3 n=normalize(aNormal);
${fingers.map((f, i) => `if(abs(finger-${i.toFixed(1)})<.1){
 float weight=smoothstep(.22,.32,position.y);
 vec3 tip=vec3(${(f.x * 1.16).toFixed(4)},${(.16 + f.length * .68).toFixed(4)},.014);
 vec3 mid=vec3(${(f.x * 1.09).toFixed(4)},${(.16 + f.length * .36).toFixed(4)},.007);
 float distal=smoothstep(tip.y-.025,tip.y+.025,position.y)*curl*.45;
 p=tip+bend(distal)*(p-tip);n=bend(distal)*n;
 float middle=smoothstep(mid.y-.025,mid.y+.025,position.y)*curl*.65;
 p=mid+bend(middle)*(p-mid);n=bend(middle)*n;
 vec3 root=vec3(${f.x.toFixed(4)},.22,0.);
 p=root+bend(curl*weight)*(p-root);n=bend(curl*weight)*n;
}`).join('\n')}
p=p*.65+origin+vec3(0.,-1.4+rise*1.4,0.);
float key=clamp(dot(n,normalize(vec3(-.5,.7,1.))),0.,1.);
float edge=clamp(max(abs(position.x)/.5,(position.y+1.4)/2.5),0.,1.);
vColor=mix(vec3(.025,.10,.20),vec3(.3,.62,.82),key);vVisibility=step(edge*.7+seed*.3,reveal);vRadius=.017;
vec4 mv=modelViewMatrix*vec4(p,1.);vView=mv.xyz;gl_Position=projectionMatrix*mv;gl_PointSize=clamp(.034*ratio*700./max(.2,-mv.z),1.,24.);}`;
export function PresentingHand() {
  const { gl, camera, size } = useThree(), phase = useForm(s => s.phase), expanded = useNexus(s => s.expanded);
  const [geometry, setGeometry] = useState<THREE.BufferGeometry | null>(null), building = useRef(false), time = useRef(10), mounted = useRef(true);
  const uniforms = useMemo(() => ({ rise: { value: 0 }, reveal: { value: 0 }, ratio: { value: 1 }, curl: { value: 0 }, origin: { value: new THREE.Vector3() } }), []);
  const anchor = useMemo(() => new THREE.Vector3(), []);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => { if (phase === 'HUMANOID_ACTIVE' && expanded) time.current = 0; }, [expanded, phase, geometry]);
  useEffect(() => {
    if (phase !== 'HUMANOID_ACTIVE' || geometry || building.current) return;
    building.current = true;
    void bakeBust(gl, 4500, () => {}, handField).then(surface => {
      if (!mounted.current) return; const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(surface.positions, 3)); g.setAttribute('aNormal', new THREE.BufferAttribute(surface.normals, 3));
      const seed = new Float32Array(surface.count); for (let i = 0; i < seed.length; i++) seed[i] = ((i * 7919) % 10007) / 10007;
      g.setAttribute('seed', new THREE.BufferAttribute(seed, 1)); setGeometry(g);
      const joints = new Float32Array(surface.count);
      for (let i = 0; i < joints.length; i++) joints[i] = fingerForPoint(surface.positions[i * 3], surface.positions[i * 3 + 1]);
      g.setAttribute('finger', new THREE.BufferAttribute(joints, 1));
    }).catch(() => { /* The readable DOM panel remains available if baking fails. */ }).finally(() => { building.current = false; });
  }, [phase, geometry, gl]);
  useEffect(() => () => geometry?.dispose(), [geometry]);
  useFrame((_, dt) => {
    if (geometry) time.current = Math.min(10, time.current + Math.max(0, Math.min(dt, 1))); const t = time.current;
    const rise = smooth(0, 1.2, t) * (1 - smooth(2.5, 3.8, t));
    uniforms.rise.value = rise; uniforms.reveal.value = phase === 'HUMANOID_ACTIVE' && expanded ? smooth(0, .5, t) * (1 - smooth(3.1, 3.8, t)) : 0; uniforms.ratio.value = gl.getPixelRatio();
    uniforms.curl.value = .12 + .65 * (1 - rise);
    // Derive the rig from viewport coordinates so the hand survives narrow previews.
    anchor.set(.52, -.44, .5).unproject(camera).sub(camera.position).normalize();
    const distance = (3 - camera.position.z) / anchor.z;
    uniforms.origin.value.copy(camera.position).addScaledVector(anchor, distance);
    anchor.copy(uniforms.origin.value).add(new THREE.Vector3(0, .45 - 1.4 + rise * 1.4, 0)).project(camera);
    panelAnchor.x = (anchor.x + 1) * size.width / 2; panelAnchor.y = (1 - anchor.y) * size.height / 2; panelAnchor.lift = geometry && t < 2.5 ? rise : 0;
  });
  return geometry ? <points geometry={geometry} frustumCulled={false}><shaderMaterial uniforms={uniforms} vertexShader={vertex} fragmentShader={humanFragment} depthWrite depthTest toneMapped={false} /></points> : null;
}
