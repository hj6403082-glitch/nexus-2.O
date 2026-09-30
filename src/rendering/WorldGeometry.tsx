'use client';
import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { useWorld } from '@/stores/world';
import { formSignal } from '@/stores/form';
const oceanVertex = `uniform float time;varying float crest;void main(){vec3 p=position;p.z+=sin(p.x*.55+time*.22)*.07+cos(p.y*.4+time*.16)*.08;crest=p.z;gl_Position=projectionMatrix*modelViewMatrix*vec4(p,1.);}`;
const oceanFragment = `varying float crest;void main(){gl_FragColor=vec4(mix(vec3(.012,.05,.075),vec3(.035,.12,.17),clamp(crest*4.+.5,0.,1.)),.8);}`;
export function WorldGeometry({ time }: { time: React.RefObject<number> }) {
  const index = useWorld(s => s.index), group = useRef<THREE.Group>(null);
  const uniforms = useMemo(() => ({ time: { value: 0 } }), []);
  useFrame(() => { uniforms.time.value = time.current; if (group.current) group.current.visible = formSignal.dissolve < .98; });
  return <group ref={group}>
    {index === 0 && <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2.64, -4]}><circleGeometry args={[20, 96]} /><meshStandardMaterial color="#10202d" metalness={.5} roughness={.65} /></mesh>}
    {index === 1 && [-12,-8,8,12].map(x => <mesh key={x} position={[x, 2, -14]}><boxGeometry args={[.07, 12, .07]} /><meshBasicMaterial color="#555fa0" transparent opacity={.35} /></mesh>)}
    {index === 2 && [9,13,17].map(radius => <mesh key={radius} position={[0, -2.5, -10]} rotation={[Math.PI / 2, 0, 0]}><torusGeometry args={[radius, .025, 6, 100, Math.PI]} /><meshStandardMaterial color="#5e9dad" metalness={.9} roughness={.2} transparent opacity={.25} /></mesh>)}
    {index === 3 && [-12,-8,-4,0,4,8,12].map(x => <group key={x} position={[x, -2.65, -9]}><mesh><boxGeometry args={[3.8, .10, 18]} /><meshStandardMaterial color="#282b29" metalness={.7} roughness={.65} /></mesh><mesh position={[1.85,.07,0]}><boxGeometry args={[.022,.012,18]} /><meshBasicMaterial color="#8f815c" /></mesh></group>)}
    {index === 4 && <mesh position={[0,-2.68,-9]} rotation={[-Math.PI/2,0,0]}><planeGeometry args={[50,50,90,90]} /><shaderMaterial uniforms={uniforms} vertexShader={oceanVertex} fragmentShader={oceanFragment} transparent /></mesh>}
    {index === 5 && [-8,-13,-19].map((z, i) => <mesh key={z} position={[0,1,z]}><planeGeometry args={[45,16]} /><meshBasicMaterial color="#657885" transparent opacity={.025 + i*.012} depthWrite={false} /></mesh>)}
  </group>;
}
