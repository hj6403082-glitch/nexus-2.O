export const humanVertex = `
attribute vec3 aSource; attribute vec3 aColor; attribute vec3 aNormal;
attribute float aCard; attribute float aSeed; attribute vec2 aCompute;
uniform mat4 uCards[10]; uniform float uTime; uniform float uPixelRatio; uniform float uSize;
uniform vec2 uHead; uniform float uJaw; uniform float uFlare;
uniform sampler2D uDisplace; uniform float uComputeSize; uniform float uBands[8];
uniform vec4 uPoke; // xyz: world-space touch point, w: seconds since the touch (<0 = none)
varying vec3 vColor; varying vec3 vView; varying float vRadius; varying float vVisibility;
float smoothRange(float a,float b,float x){float t=clamp((x-a)/(b-a),0.,1.);return t*t*(3.-2.*t);}
mat3 ry(float a){float c=cos(a),s=sin(a);return mat3(c,0.,-s,0.,1.,0.,s,0.,c);}
mat3 rx(float a){float c=cos(a),s=sin(a);return mat3(1.,0.,0.,0.,c,s,0.,-s,c);}
void main(){
 vec3 source=aSource;
 for(int i=0;i<10;i++){if(abs(aCard-float(i))<.1)source=(uCards[i]*vec4(aSource,1.)).xyz;}
 float delay=aCard<9.5 ? (1.-clamp((source.z+8.7)/10.4,0.,1.))*.5 : .8;
 float gather=smoothRange(.6+delay,3.1,uTime);
 float stagger=(1.-clamp((position.y+1.2)/2.4,0.,1.))*.9+aSeed*.25;
 float body=smoothRange(3.6+stagger,7.4,uTime);
 vec3 core=vec3(sin(aSeed*91.),cos(aSeed*73.),sin(aSeed*51.))*.10+vec3(0.,.1,2.7);
 vec3 p=mix(source,core,gather);
 float spiral=sin(gather*3.14159265)*(1.-body);
 p+=vec3(sin(aSeed*51.+gather*5.),cos(aSeed*67.+gather*4.),sin(aSeed*23.))*spiral*.65;
 vec3 target=position; vec3 n=aNormal;
 if(target.y>.26){
   vec3 pivot=vec3(0.,.43,0.);
   if(target.y<.50&&target.z>.08&&abs(target.x)<.25){target=vec3(0.,.54,0.)+rx(uJaw*.16)*(target-vec3(0.,.54,0.));n=rx(uJaw*.16)*n;}
   mat3 head=ry(uHead.x)*rx(uHead.y);target=pivot+head*(target-pivot);n=head*n;
 }
 target=target*1.7+vec3(0.,.02,3.0);
 // GPGPU ferrofluid: sample this particle's simulated offset and add it, so the
 // surface seethes like magnetic fluid in zero-g once the figure has formed.
 vec3 disp=vec3(0.);
 if(uComputeSize>0.) disp=texture2D(uDisplace,aCompute).xyz;
 target+=disp*body*1.5;
 // FFT band ripple: a band chosen by height makes the neck and jaw ripple with
 // cymatic resonance rather than a stiff hinge. Constant loop index keeps this
 // portable (no dynamic uniform-array indexing).
 float region=clamp((position.y+1.2)/2.4,0.,1.);
 float bandIdx=region*7.0; float band=0.;
 for(int i=0;i<8;i++){if(abs(float(i)-bandIdx)<.5)band=uBands[i];}
 target+=aNormal*band*0.11*body*smoothRange(.0,.55,region);
 // Touch ripple: a ring of swelling particles expands from where the user
 // tapped the figure and fades out, so the body visibly reacts to a touch.
 float poke=0.;
 if(uPoke.w>=0.){float pd=distance(target,uPoke.xyz);poke=exp(-pow((pd-uPoke.w*.8)*6.,2.))*exp(-uPoke.w*1.1)*body;}
 target+=aNormal*poke*.14;
 p=mix(p,target,body);
 p+=normalize(target-core+vec3(.0001))*sin(body*3.14159265)*.7;
 vec3 key=normalize(vec3(-.55,.7,1.));float facing=clamp(dot(normalize(n),key),0.,1.);
 vec3 blue=mix(vec3(.035,.12,.24),vec3(.32,.67,.88),pow(facing,.85));
 blue+=vec3(.04,.09,.13)*pow(clamp(facing,0.,1.),16.);
 float eye=step(.5,aSeed-1.); // last two particles have an explicit eye flag
 if(eye>.5)blue=mix(blue,vec3(.7,.88,1.)*(0.7+uFlare*0.7),smoothRange(6.9,7.8,uTime));
 blue+=poke*vec3(.45,.75,.95);
 float seam=step(abs(position.y-.49),.009)*step(abs(position.x),.12)*step(.25,position.z);
 blue+=seam*uJaw*vec3(.12,.26,.32);
 vColor=mix(aColor,blue,body);
 vVisibility=step(.08,uTime)*smoothRange(.45+delay,.75+delay,uTime);
 if(eye>.5)vVisibility*=smoothRange(6.9,7.8,uTime);
 vec4 mv=modelViewMatrix*vec4(p,1.);vView=mv.xyz;
 vRadius=mix(.006,uSize,body)*(1.+eye*.7);gl_PointSize=clamp(vRadius*2.*uPixelRatio*700./max(.2,-mv.z),1.,34.);
 gl_Position=projectionMatrix*mv;
}`;
export const humanFragment = `
precision highp float;
varying vec3 vColor;varying vec3 vView;varying float vRadius;varying float vVisibility;
uniform mat4 projectionMatrix;
void main(){
 if(vVisibility<.03)discard;
 vec2 xy=gl_PointCoord*2.-1.;float r2=dot(xy,xy);if(r2>1.)discard;
 float z=sqrt(max(0.,1.-r2));
 vec3 surface=vView+vec3(xy.x,-xy.y,z)*vRadius;
 vec4 clip=projectionMatrix*vec4(surface,1.);
 gl_FragDepth=clip.z/clip.w*.5+.5;
 float beadLight=.55+.45*max(0.,dot(normalize(vec3(xy.x,-xy.y,z)),normalize(vec3(-.5,.7,1.))));
 gl_FragColor=vec4(vColor*beadLight,1.);
}`;
