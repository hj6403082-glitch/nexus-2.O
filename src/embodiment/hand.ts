export const fingers = [{ x: -.22, length: .57, radius: .055 }, { x: -.075, length: .68, radius: .059 }, { x: .075, length: .62, radius: .055 }, { x: .21, length: .46, radius: .049 }];
const f = (n: number) => n.toFixed(4);
export const handField = `
float capsule(vec3 p,vec3 a,vec3 b,float r){vec3 ab=b-a;float h=clamp(dot(p-a,ab)/dot(ab,ab),0.,1.);return length(p-a-ab*h)-r;}
float field(vec3 p){
 float d=ell(p-vec3(0.,-.04,0.),vec3(.29,.36,.11));
 d=sm(d,ell(p-vec3(0.,-.79,-.025),vec3(.17,.58,.12)),.16);
 ${fingers.map(finger => `d=sm(d,capsule(p,vec3(${f(finger.x)},.16,0.),vec3(${f(finger.x * 1.25)},${f(.16 + finger.length)},.02),${f(finger.radius)}),.06);`).join('\n')}
 d=sm(d,capsule(p,vec3(-.20,-.14,0.),vec3(-.46,.17,.065),.075),.12);
 d=sm(d,ell(p-vec3(-.17,-.12,.045),vec3(.14,.20,.115)),.06);
 return d;
}`;
export const panelAnchor = { x: 0, y: 0, lift: 0 };

// Attach each sampled point to the nearest finger above its knuckle.
// Palm points keep -1 so articulation never tears the wrist or thenar mass.
export function fingerForPoint(x: number, y: number): number {
  if (y < .22) return -1;
  let nearest = -1, distance = Infinity;
  fingers.forEach((finger, index) => {
    const axis = finger.x * (1 + .25 * Math.min(1, (y - .16) / finger.length));
    const delta = Math.abs(x - axis);
    if (delta < finger.radius * 1.7 && delta < distance) { nearest = index; distance = delta; }
  });
  return nearest;
}
