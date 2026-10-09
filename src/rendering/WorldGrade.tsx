'use client';
import { useMemo } from 'react';
import { Effect } from 'postprocessing';
import { Uniform, Vector3 } from 'three';
import { useFrame } from '@react-three/fiber';
import { useWorld, worlds, type WorldGrade as Grade } from '@/stores/world';
// Full-screen filmic grade. Violet goes into the shadows, warm white into the
// highlights, the mid-tones are untouched, contrast pivots at 18% grey, and a
// halation term bleeds warmth out of the brightest pixels. Each world supplies
// its own ends of the ramp, so switching worlds reads as a cinematic cut.
const fragment = `uniform float contrast; uniform float warmth; uniform vec3 shadowTint; uniform vec3 highlightTint; uniform float halation;
void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
 vec3 c = max(inputColor.rgb, vec3(0.));
 float l = dot(c, vec3(.2126, .7152, .0722));
 float shadow = 1. - smoothstep(0., .22, l);
 float high = smoothstep(.5, 1., l);
 // Split the ends of the ramp; mid-tones (both weights ~0) are left alone.
 c += shadowTint * shadow * (l + .04);
 c += highlightTint * high;
 c += vec3(warmth * .06, 0., -warmth * .045) * l;
 // Filmic contrast pivoting at 18% grey.
 c = (c - .18) * contrast + .18;
 // Halation: warm bleed that grows with the brightest, clamped highlights.
 c += vec3(1., .72, .5) * halation * high * high;
 outputColor = vec4(max(c, vec3(0.)), inputColor.a);
}`;
const keys = ['contrast', 'warmth', 'halation'] as const;
export function WorldGrade() {
  const effect = useMemo(() => new Effect('WorldGrade', fragment, { uniforms: new Map<string, Uniform>([
    ['contrast', new Uniform(1)], ['warmth', new Uniform(0)], ['halation', new Uniform(0)],
    ['shadowTint', new Uniform(new Vector3())], ['highlightTint', new Uniform(new Vector3())],
  ]) }), []);
  useFrame((_, dt) => {
    const grade = worlds[useWorld.getState().index].grade as Grade;
    const ease = 1 - Math.exp(-dt * 3);
    for (const key of keys) { const u = effect.uniforms.get(key)!; u.value += (grade[key] - u.value) * ease; }
    (effect.uniforms.get('shadowTint')!.value as Vector3).lerp(new Vector3(...grade.shadow), ease);
    (effect.uniforms.get('highlightTint')!.value as Vector3).lerp(new Vector3(...grade.highlight), ease);
  });
  return <primitive object={effect} dispose={null} />;
}
