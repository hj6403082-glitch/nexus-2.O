'use client';
import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { cardMatrices } from '@/stores/form';
import { formSignal } from '@/stores/form';
import { ambientSignal, thermalSignal } from './environment';

// Dynamic floor caustics (Phase 8, Objective 5). A single shader plane laid on
// the ground grid renders animated refractive dispersion plus soft shadow
// blooms beneath each floating panel. Panel ground positions are fed in as
// uniforms (projected from the live card matrices), so the blooms track the
// cards as they orbit, gather and fling. Ambient mic level brightens the
// caustics; thermal load tints them toward cyan.
const vertex = `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.); }`;
const fragment = `precision highp float;
varying vec2 vUv;
uniform float uTime; uniform float uAmbient; uniform float uThermal; uniform float uFade;
uniform vec2 uCards[10]; uniform float uCardCount;
// Cheap value-noise caustic bands.
float hash(vec2 p){ return fract(sin(dot(p, vec2(41.3,289.1)))*43758.5453); }
float noise(vec2 p){ vec2 i=floor(p),f=fract(p); f=f*f*(3.-2.*f); float a=hash(i),b=hash(i+vec2(1,0)),c=hash(i+vec2(0,1)),d=hash(i+vec2(1,1)); return mix(mix(a,b,f.x),mix(c,d,f.x),f.y); }
void main(){
  vec2 uv = vUv * 2.0 - 1.0;          // -1..1 across the plane
  vec2 p = uv * 6.0;
  // Two drifting caustic layers; their interference makes the ripples.
  float t = uTime * 0.35;
  float c = 0.0;
  c += noise(p + vec2(t, -t*0.7));
  c += noise(p*1.9 - vec2(t*0.6, t));
  c = pow(abs(sin(c*3.14159 + t)), 3.0);
  // Refractive dispersion: sample the caustic at slightly offset positions per
  // channel so the bands fringe red/blue like light through glass.
  float disp = 0.04 + 0.03*uThermal;
  float r = pow(abs(sin((noise(p+vec2(disp,0.)) + noise(p*1.9))*3.14159 + t)),3.0);
  float b = pow(abs(sin((noise(p-vec2(disp,0.)) + noise(p*1.9))*3.14159 + t)),3.0);
  vec3 caustic = vec3(r, c, b);
  // Base cobalt, pushed toward cyan with thermal load.
  vec3 tint = mix(vec3(0.16,0.40,0.78), vec3(0.10,0.72,0.86), uThermal);
  vec3 col = caustic * tint;
  // Soft shadow blooms under each panel: a bright, soft disc that darkens the
  // grid slightly at its rim (a contact shadow) and glows at its core.
  float bloom = 0.0; float shadow = 0.0;
  for(int i=0;i<10;i++){
    if(float(i) >= uCardCount) break;
    float d = distance(uv, uCards[i]);
    bloom += smoothstep(0.42, 0.0, d);
    shadow += smoothstep(0.62, 0.30, d) * (1.0 - smoothstep(0.30, 0.0, d));
  }
  col += tint * bloom * (0.35 + 0.45*uAmbient);
  col -= vec3(0.05,0.08,0.12) * clamp(shadow,0.,1.5);
  // Fade out at the plane edges so there is no hard border.
  float edge = smoothstep(1.0, 0.55, length(uv));
  float alpha = clamp((c*0.5 + bloom*0.7) * edge, 0.0, 1.0) * uFade * (0.5 + 0.5*uAmbient);
  gl_FragColor = vec4(max(col,0.0), alpha);
}`;

export function FloorCaustics({ time }: { time: React.RefObject<number> }) {
  const material = useRef<THREE.ShaderMaterial>(null);
  const mesh = useRef<THREE.Mesh>(null);
  const uniforms = useMemo(() => ({
    uTime: { value: 0 }, uAmbient: { value: 0 }, uThermal: { value: 0 }, uFade: { value: 1 },
    uCards: { value: Array.from({ length: 10 }, () => new THREE.Vector2()) },
    uCardCount: { value: 10 },
  }), []);
  const temp = useMemo(() => new THREE.Vector3(), []);
  useFrame(() => {
    if (!material.current) return;
    const u = material.current.uniforms;
    u.uTime.value = time.current;
    u.uAmbient.value = ambientSignal.level;
    u.uThermal.value = thermalSignal.load;
    // Fade the caustics out while NEXUS dissolves into the human form.
    u.uFade.value = 1 - formSignal.dissolve;
    if (mesh.current) mesh.current.visible = formSignal.dissolve < 0.98;
    // Project each card's world position onto the floor plane (XZ → plane UV).
    const cards = u.uCards.value as THREE.Vector2[];
    for (let i = 0; i < 10; i++) {
      temp.setFromMatrixPosition(cardMatrices[i]);
      // The plane is 24 wide, centred at x=0,z=-3.5 (matches the floor ring).
      cards[i].set(temp.x / 12, -(temp.z + 3.5) / 12);
    }
  });
  return <mesh ref={mesh} rotation={[-Math.PI / 2, 0, 0]} position={[0, -2.57, -3.5]}>
    <planeGeometry args={[24, 24]} />
    <shaderMaterial ref={material} uniforms={uniforms} vertexShader={vertex} fragmentShader={fragment} transparent depthWrite={false} blending={THREE.AdditiveBlending} toneMapped={false} />
  </mesh>;
}
