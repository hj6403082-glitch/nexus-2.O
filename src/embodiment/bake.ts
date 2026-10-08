import * as THREE from 'three';
const nextFrame = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
const vertex = `varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}`;
const fragment = `precision highp float;
varying vec2 vUv; uniform float uMode;
float hash(float n){return fract(sin(n)*43758.5453);}
float ell(vec3 p,vec3 r){float k0=length(p/r),k1=length(p/(r*r));return k0*(k0-1.)/max(k1,.0001);}
float sm(float a,float b,float k){float h=clamp(.5+.5*(b-a)/k,0.,1.);return mix(b,a,h)-k*h*(1.-h);}
float field(vec3 p){
 float head=ell(p-vec3(0.,.72,0.),vec3(.345,.465,.30));
 float face=ell(p-vec3(0.,.60,.075),vec3(.29,.31,.265));
 head=sm(head,face,.12);
 head=sm(head,ell(p-vec3(0.,.66,.285),vec3(.075,.135,.09)),.10);
 head=sm(head,ell(p-vec3(.335,.70,-.015),vec3(.06,.13,.075)),.045);
 head=sm(head,ell(p-vec3(-.335,.70,-.015),vec3(.06,.13,.075)),.045);
 // Recessed eye sockets and a narrow mouth make the neutral face readable.
 head=max(head,-ell(p-vec3(.12,.765,.31),vec3(.088,.048,.075)));
 head=max(head,-ell(p-vec3(-.12,.765,.31),vec3(.088,.048,.075)));
 head=max(head,-ell(p-vec3(0.,.48,.30),vec3(.135,.016,.075)));
 float neck=ell(p-vec3(0.,.07,.035),vec3(.16,.37,.175));
 float shoulders=ell(p-vec3(0.,-.35,.055),vec3(.69,.235,.28));
 float chest=ell(p-vec3(0.,-.73,.07),vec3(.535,.46,.285));
 return sm(sm(head,neck,.14),sm(shoulders,chest,.22),.20);
}
vec3 normalAt(vec3 p){vec2 e=vec2(.001,0.);return normalize(vec3(field(p+e.xyy)-field(p-e.xyy),field(p+e.yxy)-field(p-e.yxy),field(p+e.yyx)-field(p-e.yyx)));}
void main(){
 float id=floor(vUv.x*256.)+floor(vUv.y*256.)*256.;
 vec3 p=vec3((hash(id*3.+1.)-.5)*1.9,hash(id*3.+2.)*2.8-1.35,(hash(id*3.+3.)-.5)*1.1);
 for(int i=0;i<28;i++){float d=field(p);vec3 n=normalAt(p);p-=n*clamp(d,-.18,.18);}
 vec3 packed=floor(clamp((p+vec3(1.2,1.5,.8))/vec3(2.4,3.,1.6),0.,1.)*65535.+.5);
 if(uMode<.5)gl_FragColor=vec4(floor(packed/256.)/255.,1.);
 else if(uMode<1.5)gl_FragColor=vec4(mod(packed,256.)/255.,1.);
 else gl_FragColor=vec4(normalAt(p)*.5+.5,1.);
}`;
export type BakedSurface = { positions: Float32Array; normals: Float32Array; count: number };
export async function bakeBust(gl: THREE.WebGLRenderer, count: number, report: (message: string) => void, field?: string): Promise<BakedSurface> {
  report('Baking the human surface');
  const target = new THREE.WebGLRenderTarget(256, 256, { type: THREE.UnsignedByteType, format: THREE.RGBAFormat, depthBuffer: false, stencilBuffer: false, minFilter: THREE.NearestFilter, magFilter: THREE.NearestFilter });
  const scene = new THREE.Scene(), camera = new THREE.Camera();
  const material = new THREE.ShaderMaterial({ vertexShader: vertex, fragmentShader: field ? fragment.replace(/float field\(vec3 p\)\{[\s\S]*?\n\}/, field) : fragment, uniforms: { uMode: { value: 0 } }, depthTest: false, depthWrite: false });
  const geometry = new THREE.PlaneGeometry(2, 2); scene.add(new THREE.Mesh(geometry, material));
  const bytes: Uint8Array[] = [];
  try {
    for (let pass = 0; pass < 3; pass++) {
      await nextFrame(); const previous = gl.getRenderTarget(); const autoClear = gl.autoClear;
      try { material.uniforms.uMode.value = pass; gl.autoClear = true; gl.setRenderTarget(target); gl.render(scene, camera); const data = new Uint8Array(256 * 256 * 4); gl.readRenderTargetPixels(target, 0, 0, 256, 256, data); bytes.push(data); }
      finally { gl.setRenderTarget(previous); gl.autoClear = autoClear; }
    }
  } finally { geometry.dispose(); material.dispose(); target.dispose(); }
  const candidates = new Float32Array(65536 * 3);
  for (let i = 0; i < 65536; i++) for (let axis = 0; axis < 3; axis++) candidates[i * 3 + axis] = (bytes[0][i * 4 + axis] * 256 + bytes[1][i * 4 + axis]) / 65535 * [2.4, 3, 1.6][axis] - [1.2, 1.5, .8][axis];
  report('Spreading the particles');
  let accepted: number[] = [];
  // Greedy Poisson selection over GPU-projected candidates. Reduce exclusion
  // radius until an exact count exists; no duplicate/filler points are added.
  for (let radius = .018; radius >= .001 && accepted.length < count; radius *= .84) {
    accepted = []; const grid = new Map<string, number[]>(); const squared = radius * radius;
    let budget = performance.now();
    for (let i = 0; i < 65536 && accepted.length < count; i++) {
      const x = candidates[i * 3], y = candidates[i * 3 + 1], z = candidates[i * 3 + 2];
      const gx = Math.floor(x / radius), gy = Math.floor(y / radius), gz = Math.floor(z / radius); let good = true;
      for (let dx = -1; dx <= 1 && good; dx++) for (let dy = -1; dy <= 1 && good; dy++) for (let dz = -1; dz <= 1 && good; dz++) {
        for (const j of grid.get(`${gx + dx},${gy + dy},${gz + dz}`) ?? []) {
          if ((x - candidates[j * 3]) ** 2 + (y - candidates[j * 3 + 1]) ** 2 + (z - candidates[j * 3 + 2]) ** 2 < squared) { good = false; break; }
        }
      }
      if (good) { accepted.push(i); const key = `${gx},${gy},${gz}`; const bucket = grid.get(key) ?? []; bucket.push(i); grid.set(key, bucket); }
      if (performance.now() - budget > 7) { await new Promise<void>(resolve => setTimeout(resolve, 0)); budget = performance.now(); }
    }
  }
  if (accepted.length !== count) throw new Error('The human surface could not be baked. Try returning to spatial mode and retrying.');
  const positions = new Float32Array(count * 3), normals = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) for (let a = 0; a < 3; a++) { positions[i * 3 + a] = candidates[accepted[i] * 3 + a]; normals[i * 3 + a] = bytes[2][accepted[i] * 4 + a] / 255 * 2 - 1; }
  return { positions, normals, count };
}
