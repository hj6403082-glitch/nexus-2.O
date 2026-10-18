'use client';
import { useMemo, useRef } from 'react';
import { useFrame } from '@react-three/fiber';
import * as THREE from 'three';
import { stepSpring } from '@/animations/spring';
import { fftSignal } from '@/ai/audio';
import { sfx } from '@/animations/sfx';
import { useAssistant, voiceSignal } from '@/stores/assistant';
import { formSignal } from '@/stores/form';
import { shockSignal } from '@/stores/nexus';

// The living core at the centre of the orbit: a noise-displaced energy sphere
// inside a slowly turning lattice dome. It breathes while idle, swirls while
// Zeno thinks, and its surface ripples with the voice while Zeno speaks.
// Hover makes it swell toward the pointer; a click wakes the assistant.
const noise = `
vec3 m289(vec3 x){return x-floor(x*(1./289.))*289.;}vec4 m289(vec4 x){return x-floor(x*(1./289.))*289.;}
vec4 perm(vec4 x){return m289(((x*34.)+1.)*x);}vec4 tis(vec4 r){return 1.79284291400159-.85373472095314*r;}
float snoise(vec3 v){const vec2 C=vec2(1./6.,1./3.);const vec4 D=vec4(0.,.5,1.,2.);
vec3 i=floor(v+dot(v,C.yyy)),x0=v-i+dot(i,C.xxx),g=step(x0.yzx,x0.xyz),l=1.-g,i1=min(g.xyz,l.zxy),i2=max(g.xyz,l.zxy);
vec3 x1=x0-i1+C.xxx,x2=x0-i2+C.yyy,x3=x0-D.yyy;i=m289(i);
vec4 p=perm(perm(perm(i.z+vec4(0.,i1.z,i2.z,1.))+i.y+vec4(0.,i1.y,i2.y,1.))+i.x+vec4(0.,i1.x,i2.x,1.));
vec3 ns=.142857142857*D.wyz-D.xzx;vec4 j=p-49.*floor(p*ns.z*ns.z),x_=floor(j*ns.z),y_=floor(j-7.*x_);
vec4 x=x_*ns.x+ns.yyyy,y=y_*ns.x+ns.yyyy,h=1.-abs(x)-abs(y),b0=vec4(x.xy,y.xy),b1=vec4(x.zw,y.zw);
vec4 s0=floor(b0)*2.+1.,s1=floor(b1)*2.+1.,sh=-step(h,vec4(0.)),a0=b0.xzyw+s0.xzyw*sh.xxyy,a1=b1.xzyw+s1.xzyw*sh.zzww;
vec3 p0=vec3(a0.xy,h.x),p1=vec3(a0.zw,h.y),p2=vec3(a1.xy,h.z),p3=vec3(a1.zw,h.w);
vec4 nr=tis(vec4(dot(p0,p0),dot(p1,p1),dot(p2,p2),dot(p3,p3)));p0*=nr.x;p1*=nr.y;p2*=nr.z;p3*=nr.w;
vec4 m=max(.6-vec4(dot(x0,x0),dot(x1,x1),dot(x2,x2),dot(x3,x3)),0.);m=m*m;
return 42.*dot(m*m,vec4(dot(p0,x0),dot(p1,x1),dot(p2,x2),dot(p3,x3)));}`;
const vertex = `${noise}
uniform float uTime,uLevel,uLow,uHigh,uThink,uHover;uniform vec3 uPointer;
varying vec3 vNormal,vView;varying float vDisp;
void main(){
 vec3 p=position,n=normalize(normal);
 float slow=snoise(n*1.6+vec3(0.,uTime*.25,0.))*.06;
 float swirl=snoise(n*3.2+vec3(uTime*.9,-uTime*.6,uTime*.4))*.09*uThink;
 float voice=snoise(n*4.5+vec3(0.,0.,uTime*3.))*(.16*uLevel+.12*uLow)+snoise(n*9.+uTime*5.)*.05*uHigh;
 float reach=pow(max(dot(n,normalize(uPointer)),0.),6.)*.14*uHover;
 float d=slow+swirl+voice+reach+sin(uTime*1.3)*.015;
 vDisp=d; p+=n*d*1.7;
 vec4 mv=modelViewMatrix*vec4(p,1.);
 vNormal=normalize(normalMatrix*n); vView=normalize(-mv.xyz);
 gl_Position=projectionMatrix*mv;}`;
const fragment = `uniform vec3 uColor,uHot;uniform float uLevel,uThink,uFade,uTime;
varying vec3 vNormal,vView;varying float vDisp;
void main(){
 float f=pow(1.-max(dot(normalize(vNormal),normalize(vView)),0.),2.4);
 float bands=.5+.5*sin(vDisp*60.+uTime*2.);
 vec3 c=mix(uColor,uHot,clamp(vDisp*5.+uLevel*.6,0.,1.));
 float core=pow(max(dot(normalize(vNormal),normalize(vView)),0.),3.)*(.10+.35*uLevel+.15*uThink);
 float a=(f*1.25+core+.03+bands*.08*(uThink+uLevel))*uFade;
 gl_FragColor=vec4(c*(1.2+uLevel*1.8+uThink*.5),a);}`;

export function CoreOrb() {
  const group = useRef<THREE.Group>(null), dome = useRef<THREE.LineSegments>(null), halo = useRef<THREE.Mesh>(null);
  const hover = useRef({ value: 0, velocity: 0 }), think = useRef({ value: 0, velocity: 0 }), level = useRef({ value: 0, velocity: 0 }), wake = useRef({ value: 0, velocity: 0 });
  const pointer = useRef(new THREE.Vector3(0, 0, 1)), hovered = useRef(false);
  const uniforms = useMemo(() => ({
    uTime: { value: 0 }, uLevel: { value: 0 }, uLow: { value: 0 }, uHigh: { value: 0 }, uThink: { value: 0 }, uHover: { value: 0 }, uFade: { value: 1 },
    uPointer: { value: new THREE.Vector3(0, 0, 1) }, uColor: { value: new THREE.Color('#3dffb0') }, uHot: { value: new THREE.Color('#f6ffd6') },
  }), []);
  const domeGeometry = useMemo(() => new THREE.WireframeGeometry(new THREE.IcosahedronGeometry(2.0, 3)), []);
  useFrame((state, dt) => {
    if (!group.current) return;
    const t = Math.min(dt, .05), a = useAssistant.getState();
    const active = a.status === 'Thinking' || a.status === 'Streaming' ? 1 : 0;
    const speaking = Math.min(1, Math.max(voiceSignal.level, fftSignal.level));
    uniforms.uTime.value += t * (1 + think.current.value * 1.5);
    uniforms.uThink.value = stepSpring(think.current, active, t, 60, 14);
    uniforms.uLevel.value = stepSpring(level.current, speaking, t, 380, 26);
    uniforms.uLow.value += ((fftSignal.bands[0] + fftSignal.bands[1]) * .5 - uniforms.uLow.value) * .35;
    uniforms.uHigh.value += ((fftSignal.bands[4] + fftSignal.bands[5]) * .5 - uniforms.uHigh.value) * .35;
    uniforms.uHover.value = stepSpring(hover.current, hovered.current ? 1 : 0, t, 140, 18);
    uniforms.uPointer.value.lerp(pointer.current, .15);
    const awake = stepSpring(wake.current, a.visible || a.status !== 'Idle' ? 1 : 0, t, 40, 13);
    // The core belongs to spatial mode: it fades as Zeno takes human form.
    const fade = 1 - formSignal.dissolve;
    uniforms.uFade.value = fade * (.38 + awake * .62);
    group.current.visible = fade > .01;
    const since = (performance.now() - shockSignal.at) / 1000, blast = shockSignal.at && since < 1.2 ? Math.sin(Math.min(1, since / 1.2) * Math.PI) * (1 - since / 1.2) : 0;
    uniforms.uLevel.value = Math.max(uniforms.uLevel.value, blast);
    const pulse = 1 + blast * .25 + uniforms.uLevel.value * .12 + Math.sin(uniforms.uTime.value * 1.1) * .02;
    group.current.scale.setScalar((1 + awake * .18 + uniforms.uHover.value * .06) * pulse);
    group.current.position.y = .6 + Math.sin(state.clock.elapsedTime * .6) * .08;
    if (dome.current) {
      dome.current.rotation.y += t * (.08 + uniforms.uThink.value * .5 + uniforms.uLevel.value * .8);
      dome.current.rotation.x = Math.sin(state.clock.elapsedTime * .2) * .2;
      (dome.current.material as THREE.LineBasicMaterial).opacity = (.07 + awake * .08 + uniforms.uLevel.value * .2) * fade;
    }
    if (halo.current) (halo.current.material as THREE.MeshBasicMaterial).opacity = (.025 + uniforms.uLevel.value * .1 + awake * .03) * fade;
  });
  return <group ref={group} position={[0, .6, -3.5]}>
    <mesh
      onPointerOver={e => { e.stopPropagation(); hovered.current = true; document.body.style.cursor = 'pointer'; }}
      onPointerOut={() => { hovered.current = false; document.body.style.cursor = ''; }}
      onPointerMove={e => { if (group.current) pointer.current.copy(group.current.worldToLocal(e.point.clone())).normalize(); }}
      onClick={e => { e.stopPropagation(); sfx.touch(); useAssistant.getState().wake(); }}>
      <icosahedronGeometry args={[1.45, 64]} />
      <shaderMaterial vertexShader={vertex} fragmentShader={fragment} uniforms={uniforms} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
    </mesh>
    <lineSegments ref={dome} geometry={domeGeometry}><lineBasicMaterial color="#b8ff4a" transparent opacity={.1} depthWrite={false} blending={THREE.AdditiveBlending} /></lineSegments>
    <mesh ref={halo} scale={2.5}><sphereGeometry args={[1, 32, 16]} /><meshBasicMaterial color="#16a866" transparent opacity={.06} side={THREE.BackSide} depthWrite={false} blending={THREE.AdditiveBlending} /></mesh>
  </group>;
}
