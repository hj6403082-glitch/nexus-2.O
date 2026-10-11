import * as THREE from 'three';
import { GPUComputationRenderer } from 'three/examples/jsm/misc/GPUComputationRenderer.js';

// GPGPU ferrofluid dynamics (Phase 8, Objective 3). A real FBO ping-pong
// simulation: each particle owns one texel of a square field holding its
// current 3D displacement offset. Every frame the sim integrates a curl-noise
// turbulence (magnetic fluid suspended in zero-g) that relaxes elastically back
// toward the baked surface, with amplitude driven by the live audio level so
// the whole mesh seethes when NEXUS speaks. The embodiment vertex shader
// samples this field and adds the offset to each particle's target position.
//
// Guarded by the caller: if the platform cannot compile the compute pass,
// construction throws and the humanoid simply renders without the shimmer.

const simulationFragment = /* glsl */ `
uniform float uDt; uniform float uTime; uniform float uAudio; uniform float uActive;
// Cheap 3D curl-ish noise from layered sines — enough for an organic drift.
vec3 flow(vec3 p){
  return vec3(
    sin(p.y*3.1 + uTime*0.9) + cos(p.z*2.3 - uTime*0.7),
    sin(p.z*2.7 + uTime*1.1) + cos(p.x*3.3 + uTime*0.6),
    sin(p.x*2.9 - uTime*0.8) + cos(p.y*2.1 + uTime*1.0)
  );
}
void main(){
  vec2 uv = gl_FragCoord.xy / resolution.xy;
  vec4 prev = texture2D(disp, uv);
  vec3 offset = prev.xyz;
  float seed = prev.w > 0.001 ? prev.w : fract(sin(dot(uv, vec2(41.3, 289.1))) * 43758.5453) + 0.001;
  // Turbulent push scaled by audio and whether the figure is present.
  vec3 turb = flow(offset * 6.0 + seed * 12.0) * (0.12 + uAudio * 0.9) * uActive;
  // Elastic pull back toward the surface (offset 0) keeps the fluid coherent.
  vec3 restore = -offset * 6.0;
  offset += (turb + restore) * uDt * 0.5;
  offset = clamp(offset, -0.35, 0.35);
  gl_FragColor = vec4(offset, seed);
}`;

export interface Ferrofluid {
  texture: THREE.Texture;
  step(dt: number, audio: number, active: boolean): void;
  dispose(): void;
}

export function createFerrofluid(renderer: THREE.WebGLRenderer, side: number, _basePositions: Float32Array, _count: number): Ferrofluid {
  const gpu = new GPUComputationRenderer(side, side, renderer);
  const initial = gpu.createTexture();
  // Seed per-texel phase in the alpha channel; offsets start at zero.
  const data = initial.image.data as unknown as Float32Array;
  for (let i = 0; i < data.length; i += 4) { data[i] = 0; data[i + 1] = 0; data[i + 2] = 0; data[i + 3] = Math.random() + 0.001; }
  const variable = gpu.addVariable('disp', simulationFragment, initial);
  gpu.setVariableDependencies(variable, [variable]);
  variable.material.uniforms.uDt = { value: 0.016 };
  variable.material.uniforms.uTime = { value: 0 };
  variable.material.uniforms.uAudio = { value: 0 };
  variable.material.uniforms.uActive = { value: 0 };
  const error = gpu.init();
  if (error) { gpu.dispose(); throw new Error(error); }
  let time = 0;
  return {
    get texture() { return gpu.getCurrentRenderTarget(variable).texture; },
    step(dt, audio, active) {
      time += Math.min(dt, 0.05);
      variable.material.uniforms.uDt.value = Math.min(dt, 0.05);
      variable.material.uniforms.uTime.value = time;
      variable.material.uniforms.uAudio.value = Math.max(0, Math.min(1, audio));
      variable.material.uniforms.uActive.value = active ? 1 : 0;
      gpu.compute();
    },
    dispose() { gpu.dispose(); },
  };
}
