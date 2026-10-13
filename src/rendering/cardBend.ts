import * as THREE from 'three';

// Tension & elastic bending for holographic cards (Phase 8, Objective 2).
// Cards are no longer rigid planes: when grabbed and dragged they bow and
// stretch toward the fingertips like tensioned glass, then spring flat on
// release. Implemented by injecting a vertex displacement into the card's
// standard material via onBeforeCompile, so the lit look is preserved.
//
// Uniforms (per card):
//   uGrab   : local-space point the drag is pulling toward (x,y on the face)
//   uTension: 0..1 overall bend strength (follows drag velocity / hold)
//   uStretch: extra elongation toward the grab point
export interface BendUniforms {
  uGrab: { value: THREE.Vector2 };
  uTension: { value: number };
  uStretch: { value: number };
}

export function createBendUniforms(): BendUniforms {
  return { uGrab: { value: new THREE.Vector2() }, uTension: { value: 0 }, uStretch: { value: 0 } };
}

// Attach the bend to a standard material. Returns the uniforms object to drive
// each frame. The card geometry must be tessellated (segments on the face) for
// the bend to be smooth.
export function attachBend(material: THREE.MeshStandardMaterial, uniforms: BendUniforms) {
  material.onBeforeCompile = shader => {
    shader.uniforms.uGrab = uniforms.uGrab;
    shader.uniforms.uTension = uniforms.uTension;
    shader.uniforms.uStretch = uniforms.uStretch;
    shader.vertexShader = `uniform vec2 uGrab; uniform float uTension; uniform float uStretch;\n` + shader.vertexShader;
    // Half-extents of the card face (matches the geometry args below).
    shader.vertexShader = shader.vertexShader.replace(
      '#include <begin_vertex>',
      `#include <begin_vertex>
       vec2 faceHalf = vec2(1.515, 1.83);
       vec2 nrm = transformed.xy / faceHalf;              // -1..1 across the face
       // Distance from this vertex to the fingertip pull point, normalised.
       float d = distance(transformed.xy, uGrab) / length(faceHalf);
       float pull = (1.0 - clamp(d, 0.0, 1.0));
       // Bow the surface toward the viewer where the pull is strongest, and dish
       // it away at the far edge, so the card reads as flexing under tension.
       transformed.z += uTension * (pull * pull * 0.9 - (1.0 - pull) * 0.25);
       // Stretch the face toward the grab point (elastic elongation).
       transformed.xy += (uGrab - transformed.xy) * uStretch * pull * 0.12;
       // A little anticlastic curl at the free corners.
       transformed.z += uTension * 0.12 * nrm.x * nrm.y * (1.0 - pull);
      `,
    );
  };
  material.needsUpdate = true;
  return uniforms;
}

// Drive the bend uniforms from the card's drag springs each frame. `vx`/`vy`
// are the current drag spring velocities; `grabbed` is whether this card (or
// its group) is being pulled; `gx`/`gy` the fingertip offset on the face.
export function driveBend(u: BendUniforms, grabbed: boolean, gx: number, gy: number, vx: number, vy: number, dt: number) {
  const speed = Math.min(1, Math.hypot(vx, vy) * 0.25);
  const targetTension = grabbed ? 0.5 + speed * 0.5 : 0;
  const targetStretch = grabbed ? Math.min(1, speed * 1.2) : 0;
  const ease = 1 - Math.exp(-dt * (grabbed ? 16 : 9));
  u.uTension.value += (targetTension - u.uTension.value) * ease;
  u.uStretch.value += (targetStretch - u.uStretch.value) * ease;
  u.uGrab.value.x += (gx - u.uGrab.value.x) * ease;
  u.uGrab.value.y += (gy - u.uGrab.value.y) * ease;
}
