'use client';
import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import { Html } from '@react-three/drei';
import * as THREE from 'three';
import { useProject } from '@/stores/project';
import { stepSpring } from '@/animations/spring';
import { formSignal } from '@/stores/form';
// The island floats ahead and slightly above the orbit, far enough to read as
// its own place. Presence springs 0→1 on enter and back on exit; at 0 the
// group is hidden so a project never-entered costs nothing.
const CENTRE: [number, number, number] = [0, .35, -5.2];
export function ProjectWorld({ time }: { time: React.RefObject<number> }) {
  const world = useProject(s => s.world);
  const focused = useProject(s => s.focused);
  const group = useRef<THREE.Group>(null);
  const rings = useRef<THREE.Group>(null);
  const shards = useRef<THREE.Group>(null);
  const html = useRef<HTMLDivElement>(null);
  const presence = useRef({ value: 0, velocity: 0 });
  const color = useMemo(() => new THREE.Color(), []);
  // Shard seats are fixed per world so the arrangement is recognisably "this
  // project", recomputed only when the world changes.
  const seats = useMemo(() => {
    if (!world) return [] as { angle: number; radius: number; y: number; size: number }[];
    const out = [];
    for (let i = 0; i < world.shards; i++) {
      const a = (i / world.shards) * Math.PI * 2 + world.phase;
      out.push({ angle: a, radius: 1.5 + ((world.seed >> i) & 3) * .22, y: Math.sin(a * 1.7 + world.phase) * .5, size: .05 + ((world.seed >> (i + 4)) & 3) * .018 });
    }
    return out;
  }, [world]);
  useFrame((_, dt) => {
    if (!group.current) return;
    const target = focused && formSignal.dissolve < .5 ? 1 : 0;
    const p = stepSpring(presence.current, target, dt, 70, 18);
    group.current.visible = p > .002;
    if (!group.current.visible) return;
    const bob = world ? Math.sin(time.current * world.bob + world.phase) * .12 : 0;
    group.current.position.set(CENTRE[0], CENTRE[1] + bob, CENTRE[2]);
    group.current.scale.setScalar(.2 + p * .8);
    group.current.rotation.y = (1 - p) * .6;
    if (rings.current && world) { rings.current.rotation.z = time.current * world.spin; rings.current.rotation.x = world.tilt; }
    if (shards.current) shards.current.rotation.y = time.current * .08;
    if (html.current) html.current.style.opacity = String(p * (1 - formSignal.dissolve));
  });
  if (!world) return null;
  color.set(world.accent);
  return <group ref={group} visible={false}>
    {/* Glass platform the project stands on. */}
    <mesh rotation={[-Math.PI / 2, 0, 0]}><circleGeometry args={[1.35, 72]} /><meshStandardMaterial color="#0c1a28" metalness={.7} roughness={.25} transparent opacity={.55} emissive={color} emissiveIntensity={.12} /></mesh>
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, .002, 0]}><ringGeometry args={[1.3, 1.34, 96]} /><meshBasicMaterial color={color} transparent opacity={.5} /></mesh>
    {/* Counter-rotating halo rings. */}
    <group ref={rings}>{Array.from({ length: world.rings }, (_, i) => <mesh key={i} rotation={[Math.PI / 2, 0, 0]} position={[0, .1 + i * .16, 0]}><torusGeometry args={[1.55 + i * .28, .012, 6, 120]} /><meshStandardMaterial color={color} metalness={.9} roughness={.2} transparent opacity={.4 - i * .07} emissive={color} emissiveIntensity={.5} /></mesh>)}</group>
    {/* Light shards orbiting the island. */}
    <group ref={shards}>{seats.map((s, i) => <mesh key={i} position={[Math.cos(s.angle) * s.radius, s.y, Math.sin(s.angle) * s.radius]}><boxGeometry args={[s.size, s.size * 3, s.size]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={.9} transparent opacity={.85} /></mesh>)}</group>
    {/* Title placard, billboarded toward the camera. */}
    <Html transform position={[0, 1.15, 0]} distanceFactor={5} zIndexRange={[15, 0]}><div ref={html} className="project-world-plate" style={{ borderColor: `${world.accent}66`, pointerEvents: 'none' }}><span className="eyebrow" style={{ color: world.accent }}>PROJECT WORLD</span><strong>{focused?.title}</strong>{focused?.detail && <p>{focused.detail.slice(0, 120)}</p>}</div></Html>
  </group>;
}
