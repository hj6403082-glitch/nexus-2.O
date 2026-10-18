import * as THREE from 'three';
const nextFrame = () => new Promise<void>(resolve => requestAnimationFrame(() => resolve()));
const vertex = `varying vec2 vUv; void main(){vUv=uv;gl_Position=vec4(position.xy,0.,1.);}`;
const fragment = `precision highp float;
varying vec2 vUv; uniform float uMode;
// Sine-free hash of the texel coordinate (Hoskins hash32). fract(sin(big)) loses
// precision on some GPUs and software renderers, collapsing thousands of seeds
// onto the same point so the bust could not be baked.
vec3 hash3(vec2 p){vec3 q=fract(vec3(p.xyx)*vec3(.1031,.1030,.0973));q+=dot(q,q.yxz+33.33);return fract((q.xxy+q.yzz)*q.zyx);}
float ell(vec3 p,vec3 r){float k0=length(p/r),k1=length(p/(r*r));return k0*(k0-1.)/max(k1,.0001);}
float sm(float a,float b,float k){float h=clamp(.5+.5*(b-a)/k,0.,1.);return mix(b,a,h)-k*h*(1.-h);}
float cap(vec3 p,vec3 a,vec3 b,float r){vec3 pa=p-a,ba=b-a;float h=clamp(dot(pa,ba)/dot(ba,ba),0.,1.);return length(pa-ba*h)-r;}
// A sculpted android bust: defined brow, cheekbones, nose, lips, jaw and chin
// rather than a smooth blob, so the particles read as a face.
float field(vec3 p){
 float head=ell(p-vec3(0.,.78,-.02),vec3(.315,.40,.33));
 head=sm(head,ell(p-vec3(0.,.62,.08),vec3(.262,.30,.26)),.10);
 head=sm(head,ell(p-vec3(0.,.47,.10),vec3(.215,.13,.20)),.08);
 head=sm(head,ell(p-vec3(0.,.395,.235),vec3(.10,.065,.075)),.06);
 head=sm(head,ell(p-vec3(0.,.835,.255),vec3(.25,.045,.075)),.05);
 head=sm(head,ell(p-vec3(.165,.655,.215),vec3(.085,.055,.075)),.05);
 head=sm(head,ell(p-vec3(-.165,.655,.215),vec3(.085,.055,.075)),.05);
 head=sm(head,cap(p,vec3(0.,.79,.30),vec3(0.,.635,.345),.028),.035);
 head=sm(head,ell(p-vec3(0.,.615,.33),vec3(.06,.032,.045)),.03);
 head=sm(head,ell(p-vec3(0.,.515,.305),vec3(.095,.024,.045)),.025);
 head=sm(head,ell(p-vec3(0.,.462,.298),vec3(.085,.028,.045)),.025);
 head=sm(head,ell(p-vec3(.315,.70,-.02),vec3(.04,.11,.07)),.03);
 head=sm(head,ell(p-vec3(-.315,.70,-.02),vec3(.04,.11,.07)),.03);
 // Eye sockets with eyeballs set into them, and the parted mouth line.
 head=max(head,-ell(p-vec3(.115,.755,.30),vec3(.075,.04,.07)));
 head=max(head,-ell(p-vec3(-.115,.755,.30),vec3(.075,.04,.07)));
 head=min(head,ell(p-vec3(.115,.752,.262),vec3(.045,.032,.035)));
 head=min(head,ell(p-vec3(-.115,.752,.262),vec3(.045,.032,.035)));
 head=max(head,-ell(p-vec3(0.,.489,.32),vec3(.10,.008,.05)));
 float neck=ell(p-vec3(0.,.12,0.),vec3(.14,.36,.16));
 float traps=ell(p-vec3(0.,-.17,-.02),vec3(.45,.13,.2));
 float shoulders=ell(p-vec3(0.,-.36,.03),vec3(.66,.21,.26));
 float chest=ell(p-vec3(0.,-.74,.06),vec3(.52,.45,.28));
 chest=sm(chest,cap(p,vec3(.05,-.25,.22),vec3(.36,-.30,.17),.022),.05);
 chest=sm(chest,cap(p,vec3(-.05,-.25,.22),vec3(-.36,-.30,.17),.022),.05);
 return sm(sm(head,neck,.10),sm(sm(traps,shoulders,.15),chest,.2),.16);
}
vec3 normalAt(vec3 p){vec2 e=vec2(.001,0.);return normalize(vec3(field(p+e.xyy)-field(p-e.xyy),field(p+e.yxy)-field(p-e.yxy),field(p+e.yyx)-field(p-e.yyx)));}
void main(){
 vec3 h=hash3(floor(vUv*256.)+vec2(.5,1.5)), g=hash3(floor(vUv*256.)+vec2(91.5,37.5));
 // Two in five seeds start around the head so the face gets the finest detail.
 vec3 p=g.x<.4 ? vec3((h.x-.5)*.8,h.y*.95+.3,(h.z-.5)*.8+.05) : vec3((h.x-.5)*1.9,h.y*2.8-1.35,(h.z-.5)*1.1);
 for(int i=0;i<28;i++){float d=field(p);vec3 n=normalAt(p);p-=n*clamp(d,-.18,.18);}
 vec3 quant=floor(clamp((p+vec3(1.2,1.5,.8))/vec3(2.4,3.,1.6),0.,1.)*65535.+.5);
 if(uMode<.5)gl_FragColor=vec4(floor(quant/256.)/255.,1.);
 else if(uMode<1.5)gl_FragColor=vec4(mod(quant,256.)/255.,1.);
 else gl_FragColor=vec4(normalAt(p)*.5+.5,1.);
}`;
// Greedy Poisson selection over GPU-projected candidates. Reduce exclusion
// radius until an exact count exists; no duplicate/filler points are added.
// Cells are integer-keyed linked lists (no string keys or per-cell arrays), so
// a pass is cheap enough that slow GPUs no longer stall the transformation here.
export async function poissonSelect(candidates: Float32Array, count: number, sliceMs = 10): Promise<number[]> {
  const total = candidates.length / 3, next = new Int32Array(total);
  let accepted: number[] = [];
  for (let radius = .018; radius >= .001 && accepted.length < count; radius *= .84) {
    accepted = []; const head = new Map<number, number>(); const squared = radius * radius, inv = 1 / radius;
    let budget = performance.now();
    for (let i = 0; i < total && accepted.length < count; i++) {
      const x = candidates[i * 3], y = candidates[i * 3 + 1], z = candidates[i * 3 + 2];
      const gx = Math.floor(x * inv) + 2048, gy = Math.floor(y * inv) + 2048, gz = Math.floor(z * inv) + 2048; let good = true;
      for (let dx = -1; dx <= 1 && good; dx++) for (let dy = -1; dy <= 1 && good; dy++) for (let dz = -1; dz <= 1 && good; dz++) {
        for (let j = head.get(((gx + dx) * 4096 + gy + dy) * 4096 + gz + dz) ?? -1; j >= 0; j = next[j]) {
          const ex = x - candidates[j * 3], ey = y - candidates[j * 3 + 1], ez = z - candidates[j * 3 + 2];
          if (ex * ex + ey * ey + ez * ez < squared) { good = false; break; }
        }
      }
      if (good) { accepted.push(i); const key = (gx * 4096 + gy) * 4096 + gz; next[i] = head.get(key) ?? -1; head.set(key, i); }
      if ((i & 255) === 0 && performance.now() - budget > sliceMs) { await new Promise<void>(resolve => setTimeout(resolve, 0)); budget = performance.now(); }
    }
  }
  return accepted;
}
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
  const accepted = await poissonSelect(candidates, count);
  if (accepted.length !== count) throw new Error('The human surface could not be baked. Try returning to spatial mode and retrying.');
  const positions = new Float32Array(count * 3), normals = new Float32Array(count * 3);
  for (let i = 0; i < count; i++) for (let a = 0; a < 3; a++) { positions[i * 3 + a] = candidates[accepted[i] * 3 + a]; normals[i * 3 + a] = bytes[2][accepted[i] * 4 + a] / 255 * 2 - 1; }
  return { positions, normals, count };
}
