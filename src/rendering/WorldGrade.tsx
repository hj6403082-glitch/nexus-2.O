'use client';
import { useMemo } from 'react';
import { Effect } from 'postprocessing';
import { Uniform } from 'three';
import { useFrame } from '@react-three/fiber';
import { useWorld, worlds } from '@/stores/world';
const fragment = `uniform float contrast; uniform float warmth;
void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
 vec3 c=max(inputColor.rgb,vec3(0.)); float l=dot(c,vec3(.2126,.7152,.0722));
 float shadow=1.-smoothstep(0.,.18,l);float high=smoothstep(.45,1.,l);
 c+=vec3(.025,0.,.055)*shadow*l+vec3(.025,.017,0.)*high;
 c+=vec3(warmth*.06,0.,-warmth*.045)*l;
 c=(c-.18)*contrast+.18; outputColor=vec4(max(c,vec3(0.)),inputColor.a);
}`;
export function WorldGrade() {
  const effect = useMemo(() => new Effect('WorldGrade', fragment, { uniforms: new Map([['contrast', new Uniform(1)], ['warmth', new Uniform(0)]]) }), []);
  useFrame((_, dt) => { const world = worlds[useWorld.getState().index]; for (const key of ['contrast', 'warmth'] as const) { const u = effect.uniforms.get(key)!; u.value += (world[key] - u.value) * (1 - Math.exp(-dt * 3)); } });
  return <primitive object={effect} dispose={null} />;
}
