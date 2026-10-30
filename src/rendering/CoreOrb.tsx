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

// The living core at the centre of the orbit: a gyroscopic singularity. A
// noise-displaced plasma heart sits inside a scanning event-horizon shell,
// circled by three tilted rings with light racing along them and particle
// streams flowing in their planes. It breathes while idle, the gyroscope spins
// up and the streams swirl while Zeno thinks, and the plasma, rings and
// streams all pulse with the voice while Zeno speaks. Hover makes it swell
// toward the pointer; a click wakes the assistant.
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

const shellVertex = `varying vec3 vNormal,vView,vPos;
void main(){vPos=position;vec4 mv=modelViewMatrix*vec4(position,1.);vNormal=normalize(normalMatrix*normal);vView=normalize(-mv.xyz);gl_Position=projectionMatrix*mv;}`;
// Event horizon: a fresnel rim with latitude scan lines sweeping down it and a
// faint hex-like cell pattern that only shows at the edge.
const shellFragment = `uniform vec3 uColor;uniform float uTime,uLevel,uThink,uFade;
varying vec3 vNormal,vView,vPos;
void main(){
 float f=pow(1.-abs(dot(normalize(vNormal),normalize(vView))),3.);
 float scan=smoothstep(.92,1.,sin(vPos.y*28.-uTime*(2.+uThink*6.)));
 float sweep=exp(-pow((vPos.y-(fract(uTime*.18)*2.4-1.2))*6.,2.));
 vec2 q=vec2(atan(vPos.z,vPos.x)*6.,vPos.y*10.);float cell=smoothstep(.42,.5,abs(fract(q.x+.5*floor(q.y))-.5))+smoothstep(.42,.5,abs(fract(q.y)-.5));
 float a=(f*f*.7+scan*.12*f+sweep*.35*f+cell*f*.12+uLevel*f*.5)*uFade;
 gl_FragColor=vec4(uColor*(1.1+uLevel),a);}`;
const ringVertex = `varying vec2 vUv;void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}`;
// Rings: dim track with dashes and a bright comet head racing around it.
const ringFragment = `uniform vec3 uColor,uHot;uniform float uTime,uLevel,uThink,uFade,uSpeed,uDash;
varying vec2 vUv;
void main(){
 float u=vUv.x;
 float dash=step(.55,fract(u*uDash-uTime*uSpeed*.6));
 float head=fract(u-uTime*uSpeed*.18);float comet=pow(head,14.)+pow(head,90.)*2.;
 float a=(.08+dash*.18*(.5+uThink)+comet*(.9+uLevel*1.5))*uFade;
 gl_FragColor=vec4(mix(uColor,uHot,clamp(comet,0.,1.))*(1.2+uLevel*1.5),a);}`;
// Particle streams: each point orbits in its ring's plane on the GPU.
const streamVertex = `attribute vec4 aOrbit;uniform float uTime,uLevel,uThink,uBlast,uPixelRatio;
varying float vGlow;
void main(){
 float r=aOrbit.x*(1.+uLevel*.16+uBlast*.7)+sin(uTime*3.+aOrbit.z*9.)*.03*(uThink+uLevel);
 float a=aOrbit.z+uTime*aOrbit.w*(1.+uThink*2.2+uLevel*1.2);
 vec3 p=vec3(cos(a)*r,sin(a)*r,aOrbit.y);
 vec4 mv=modelViewMatrix*vec4(p,1.);
 vGlow=.5+.5*sin(a*7.+aOrbit.z*13.);
 gl_PointSize=clamp((3.+vGlow*3.+uLevel*4.)*uPixelRatio*4./max(.2,-mv.z),1.5,12.);
 gl_Position=projectionMatrix*mv;}`;
const streamFragment = `uniform vec3 uColor,uHot;uniform float uFade,uLevel;varying float vGlow;
void main(){vec2 c=gl_PointCoord-.5;float d=length(c);if(d>.5)discard;float s=pow(1.-d*2.,1.6);
 gl_FragColor=vec4(mix(uColor,uHot,vGlow*.7+uLevel*.3)*1.4,s*(.35+vGlow*.5)*uFade);}`;
const RINGS = [
  // tilt = angle away from the viewer, turn = where around the view axis it leans.
  { radius: 1.32, tilt: 1.12, turn: .3, spin: .55, dash: 48, color: '#3dffd0' },
  { radius: 1.56, tilt: 1.2, turn: 2.4, spin: -.4, dash: 64, color: '#b8ff4a' },
  { radius: 1.8, tilt: 1.05, turn: 4.4, spin: .3, dash: 80, color: '#7dffb0' },
] as const;
function streamGeometry(radius: number, count: number) {
  const orbit = new Float32Array(count * 4), position = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) {
    const band = Math.random() < .7 ? (Math.random() - .5) * .14 : (Math.random() - .5) * .5;
    orbit.set([radius + band, (Math.random() - .5) * .05, Math.random() * Math.PI * 2, (.25 + Math.random() * .5) * (Math.random() < .12 ? -1 : 1)], i * 4);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.BufferAttribute(position, 3)); g.setAttribute('aOrbit', new THREE.BufferAttribute(orbit, 4));
  g.boundingSphere = new THREE.Sphere(new THREE.Vector3(), radius + 1);
  return g;
}

export function CoreOrb() {
  const group = useRef<THREE.Group>(null), halo = useRef<THREE.Mesh>(null);
  const gimbals = useRef<(THREE.Group | null)[]>([]), spinners = useRef<(THREE.Group | null)[]>([]);
  const hover = useRef({ value: 0, velocity: 0 }), think = useRef({ value: 0, velocity: 0 }), level = useRef({ value: 0, velocity: 0 }), wake = useRef({ value: 0, velocity: 0 });
  const pointer = useRef(new THREE.Vector3(0, 0, 1)), hovered = useRef(false);
  const uniforms = useMemo(() => ({
    uTime: { value: 0 }, uLevel: { value: 0 }, uLow: { value: 0 }, uHigh: { value: 0 }, uThink: { value: 0 }, uHover: { value: 0 }, uFade: { value: 1 },
    uPointer: { value: new THREE.Vector3(0, 0, 1) }, uColor: { value: new THREE.Color('#3dffb0') }, uHot: { value: new THREE.Color('#f6ffd6') },
  }), []);
  // Shared live values; each material gets its own colour but the same clock and levels.
  const shared = useMemo(() => ({ uBlast: { value: 0 }, uPixelRatio: { value: 1 } }), []);
  const shell = useMemo(() => ({ uTime: uniforms.uTime, uLevel: uniforms.uLevel, uThink: uniforms.uThink, uFade: uniforms.uFade, uColor: { value: new THREE.Color('#5affc8') } }), [uniforms]);
  const rings = useMemo(() => RINGS.map(r => ({
    ring: { uTime: uniforms.uTime, uLevel: uniforms.uLevel, uThink: uniforms.uThink, uFade: uniforms.uFade, uColor: { value: new THREE.Color(r.color) }, uHot: { value: new THREE.Color('#fff6c2') }, uSpeed: { value: Math.abs(r.spin) * 2 }, uDash: { value: r.dash } },
    stream: { uTime: uniforms.uTime, uLevel: uniforms.uLevel, uThink: uniforms.uThink, uFade: uniforms.uFade, uBlast: shared.uBlast, uPixelRatio: shared.uPixelRatio, uColor: { value: new THREE.Color(r.color) }, uHot: { value: new THREE.Color('#ffe066') } },
    geometry: streamGeometry(r.radius, 1400),
  })), [uniforms, shared]);
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
    shared.uPixelRatio.value = state.gl.getPixelRatio();
    const awake = stepSpring(wake.current, a.visible || a.status !== 'Idle' ? 1 : 0, t, 40, 13);
    // The core belongs to spatial mode: it fades as Zeno takes human form.
    const fade = 1 - formSignal.dissolve;
    uniforms.uFade.value = fade * (.45 + awake * .55);
    group.current.visible = fade > .01;
    const since = (performance.now() - shockSignal.at) / 1000, blast = shockSignal.at && since < 1.2 ? Math.sin(Math.min(1, since / 1.2) * Math.PI) * (1 - since / 1.2) : 0;
    shared.uBlast.value = blast;
    uniforms.uLevel.value = Math.max(uniforms.uLevel.value, blast);
    const pulse = 1 + blast * .25 + uniforms.uLevel.value * .1 + Math.sin(uniforms.uTime.value * 1.1) * .02;
    group.current.scale.setScalar((1 + awake * .12 + uniforms.uHover.value * .06) * pulse);
    group.current.position.y = .6 + Math.sin(state.clock.elapsedTime * .6) * .08;
    // The gyroscope: each ring spins in its plane while its gimbal precesses;
    // thinking spins it up, the voice kicks it, the pointer tilts it.
    const drive = 1 + uniforms.uThink.value * 3.5 + uniforms.uLevel.value * 2 + blast * 6;
    RINGS.forEach((r, i) => {
      const spin = spinners.current[i], gimbal = gimbals.current[i];
      if (spin) spin.rotation.z += t * r.spin * drive;
      if (gimbal) {
        gimbal.rotation.z = r.turn + state.clock.elapsedTime * .09 * (i % 2 ? -1 : 1) + uniforms.uPointer.value.x * uniforms.uHover.value * .3;
        gimbal.rotation.x = r.tilt + Math.sin(state.clock.elapsedTime * .3 + i * 2) * .08 - uniforms.uPointer.value.y * uniforms.uHover.value * .3;
      }
    });
    if (halo.current) (halo.current.material as THREE.MeshBasicMaterial).opacity = (.02 + uniforms.uLevel.value * .08 + awake * .025) * fade;
  });
  return <group ref={group} position={[0, .6, -3.5]}>
    <mesh
      onPointerOver={e => { e.stopPropagation(); hovered.current = true; document.body.style.cursor = 'pointer'; }}
      onPointerOut={() => { hovered.current = false; document.body.style.cursor = ''; }}
      onPointerMove={e => { if (group.current) pointer.current.copy(group.current.worldToLocal(e.point.clone())).normalize(); }}
      onClick={e => { e.stopPropagation(); sfx.touch(); useAssistant.getState().wake(); }}>
      <sphereGeometry args={[1.25, 24, 16]} />
      <meshBasicMaterial transparent opacity={0} depthWrite={false} colorWrite={false} />
    </mesh>
    {/* Displacement is in object units, so the heart is a scaled-down full-size sphere. */}
    <mesh scale={.42}>
      <icosahedronGeometry args={[1.24, 48]} />
      <shaderMaterial vertexShader={vertex} fragmentShader={fragment} uniforms={uniforms} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
    </mesh>
    <mesh>
      <sphereGeometry args={[1.02, 64, 48]} />
      <shaderMaterial vertexShader={shellVertex} fragmentShader={shellFragment} uniforms={shell} transparent depthWrite={false} blending={THREE.AdditiveBlending} />
    </mesh>
    {RINGS.map((r, i) => <group key={i} ref={el => { gimbals.current[i] = el; }} rotation={new THREE.Euler(r.tilt, 0, r.turn, 'ZXY')}>
      <group ref={el => { spinners.current[i] = el; }}>
        <mesh><torusGeometry args={[r.radius, .007, 6, 320]} /><shaderMaterial vertexShader={ringVertex} fragmentShader={ringFragment} uniforms={rings[i].ring} transparent depthWrite={false} blending={THREE.AdditiveBlending} /></mesh>
      </group>
      <points geometry={rings[i].geometry}><shaderMaterial vertexShader={streamVertex} fragmentShader={streamFragment} uniforms={rings[i].stream} transparent depthWrite={false} blending={THREE.AdditiveBlending} /></points>
    </group>)}
    <mesh ref={halo} scale={2.4}><sphereGeometry args={[1, 32, 16]} /><meshBasicMaterial color="#16a866" transparent opacity={.05} side={THREE.BackSide} depthWrite={false} blending={THREE.AdditiveBlending} /></mesh>
  </group>;
}
