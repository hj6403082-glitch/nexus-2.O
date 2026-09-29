'use client';
import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Grid } from '@react-three/drei';
import * as THREE from 'three';
import { useWorld, worlds } from '@/stores/world';
import { formSignal } from '@/stores/form';
export function Atmosphere({ motionTime }: { motionTime: React.RefObject<number> }) {
  const world = worlds[useWorld(s => s.index)];
  const dust = useRef<THREE.Points>(null);
  const room = useRef<THREE.Group>(null);
  const positions = useMemo(() => {
    const a = new Float32Array(240 * 3); let seed = 83;
    const random = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    for (let i = 0; i < a.length; i += 3) { a[i] = (random() - .5) * 35; a[i + 1] = random() * 9 - 3; a[i + 2] = random() * -28; }
    return a;
  }, []);
  useFrame(() => { if (dust.current) dust.current.rotation.y = Math.sin(motionTime.current * .015) * .12; if (room.current) room.current.visible = formSignal.dissolve < .98; });
  return <>
    <color attach="background" args={[world.fog]} />
    <fog attach="fog" args={[world.fog, 12, 38]} />
    <ambientLight intensity={.45} color="#8fbbdc" />
    <pointLight position={[0, 6, 2]} intensity={25} color={world.light} />
    <group ref={room}><Grid position={[0, -2.6, -3]} infiniteGrid cellSize={1} sectionSize={5} cellThickness={.45} sectionThickness={.7} cellColor="#142c40" sectionColor={world.grid} fadeDistance={35} fadeStrength={2} />
    <points ref={dust}><bufferGeometry><bufferAttribute attach="attributes-position" args={[positions, 3]} /></bufferGeometry><pointsMaterial color="#79a8c0" size={.018} transparent opacity={.32} depthWrite={false} sizeAttenuation /></points>
    {[[-8, 1, -12], [8, 2, -16], [0, 5, -22]].map((p, i) => <mesh key={i} position={p as [number, number, number]} rotation={[0, 0, (i - 1) * .25]}><planeGeometry args={[.03, 22]} /><meshBasicMaterial color="#7bb7ec" transparent opacity={.08} depthWrite={false} blending={THREE.AdditiveBlending} /></mesh>)}
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2.58, -3.5]}><ringGeometry args={[4.95, 4.97, 160]} /><meshBasicMaterial color="#446782" transparent opacity={.28} /></mesh>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -2.575, -3.5]}><ringGeometry args={[5.2, 5.205, 160]} /><meshBasicMaterial color="#668398" transparent opacity={.3} /></mesh>
  </group></>;
}
