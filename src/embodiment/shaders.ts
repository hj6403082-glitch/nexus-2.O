export const humanVertex = `
attribute vec3 aSource; attribute vec3 aColor; attribute vec3 aNormal;
attribute float aCard; attribute float aSeed; attribute vec2 aCompute;
uniform mat4 uCards[10]; uniform float uTime; uniform float uPixelRatio; uniform float uSize;
uniform vec2 uHead; uniform float uJaw; uniform float uFlare; uniform float uReturn; uniform float uClock;
uniform sampler2D uDisplace; uniform float uComputeSize;
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
 float presence=smoothRange(6.5,8.,uTime);
 vec3 rnd=vec3(sin(aSeed*91.),cos(aSeed*73.),sin(aSeed*51.));
 vec3 core=rnd*.10+vec3(0.,.1,2.7);
 // Resolve the final surface point first so every phase can aim at it.
 vec3 target=position; vec3 n=aNormal;
 // Idle life: the chest breathes once the figure is present.
 if(target.y<-.15){float breath=1.+sin(uClock*1.25)*.014*presence;target.xz*=breath;target.y+=sin(uClock*1.25)*.008*presence;}
 if(target.y>.26){
   vec3 pivot=vec3(0.,.43,0.);
   // Speech moves the mouth only: the jaw and lower lip hinge open with a soft
   // falloff (no seam), the upper lip lifts slightly.
   float jaw=(1.-smoothRange(.47,.497,target.y))*smoothRange(.30,.37,target.y)*(1.-smoothRange(.15,.25,abs(target.x)))*smoothRange(0.,.14,target.z);
   if(jaw>0.){mat3 open=rx(uJaw*.2*jaw);target=vec3(0.,.56,0.)+open*(target-vec3(0.,.56,0.));n=open*n;}
   target.y+=uJaw*.012*smoothRange(.495,.505,target.y)*(1.-smoothRange(.53,.56,target.y))*(1.-smoothRange(.08,.12,abs(target.x)))*step(.25,target.z);
   mat3 head=ry(uHead.x)*rx(uHead.y);target=pivot+head*(target-pivot);n=head*n;
 }
 target=target*1.7+vec3(0.,.02,3.0);
 // GPGPU ferrofluid: sample this particle's simulated offset and add it, so the
 // surface seethes like magnetic fluid in zero-g once the figure has formed.
 vec3 disp=vec3(0.);
 if(uComputeSize>0.) disp=texture2D(uDisplace,aCompute).xyz;
 target+=disp*body*1.5;

 // Returning, the figure does not rewind into the core: it disintegrates into
 // an expanding cloud of motes that streams back to the interface.
 vec3 away=normalize(target-vec3(0.,.1,3.)+vec3(.0001));
 vec3 hub=mix(core,target+away*(1.4+aSeed*1.6)+vec3(0.,.9,0.)*aSeed+rnd*.9,uReturn);
 vec3 p=mix(source,hub,gather);
 // Gathering: a vortex around the core's vertical axis that tightens as the
 // particles close in, with a lift so the stream reads as a whirlwind.
 float flight=gather*(1.-gather)*4.;
 float swirl=flight*(2.4+aSeed*2.6)*(1.-body)*(1.-uReturn*.6);
 p=hub+ry(swirl)*(p-hub);
 p.y+=flight*(aSeed-.35)*.8*(1.-body);
 p+=rnd*sin(gather*3.14159265)*(1.-body)*.3;
 // The core holds as a beating star before the figure is drawn out of it.
 float coreE=smoothRange(2.6,3.2,uTime)*(1.-body)*(1.-uReturn);
 float beat=pow(.5+.5*sin(uTime*11.),3.);
 p=mix(p,hub+(p-hub)*(.55+beat*.7),coreE);
 // Emergence settles like a spring: a slight overshoot, then rest exactly on
 // the surface (normalised so body=1 lands precisely on target).
 float settle=(1.-exp(-5.*body)*cos(7.*body))/(1.-exp(-5.)*cos(7.));
 p=mix(p,target,settle);
 p+=normalize(target-hub+vec3(.0001))*sin(body*3.14159265)*mix(.55,.25,uReturn);
 vec3 key=normalize(vec3(-.55,.7,1.));float facing=clamp(dot(normalize(n),key),0.,1.);
 vec3 blue=mix(vec3(.035,.12,.24),vec3(.32,.67,.88),pow(facing,.85));
 blue+=vec3(.04,.09,.13)*pow(clamp(facing,0.,1.),16.);
 // Rim light keeps the silhouette crisp against the room.
 blue+=vec3(.08,.2,.32)*pow(1.-abs(normalize(n).z),3.)*presence;
 float eye=step(.5,aSeed-1.); // last two particles have an explicit eye flag
 float blink=1.-step(.965,fract(uClock/4.7+.3))*presence;
 if(eye>.5)blue=mix(blue,vec3(.7,.88,1.)*(0.7+uFlare*0.7),smoothRange(6.9,7.8,uTime)*blink);
 float seam=step(abs(position.y-.489),.012)*step(abs(position.x),.1)*step(.25,position.z);
 blue+=seam*uJaw*vec3(.12,.26,.32);
 // A holographic scan line travels up the body while it is present.
 blue+=vec3(.12,.28,.38)*pow(.5+.5*sin(position.y*7.-uClock*2.2),36.)*presence;
 vColor=mix(aColor,blue,body);
 // Energy: in-flight particles run hot cyan, the forming front flares, the
 // core flashes white and dispersing motes glow gold. Values above 1 bloom.
 float heat=sin(gather*3.14159265)*(1.-body);
 float edge=sin(body*3.14159265);
 vColor+=vec3(.35,.75,1.15)*(heat*.6+edge*.85)*(1.-uReturn*.5);
 vColor+=vec3(1.1,.85,.5)*uReturn*(edge*.7+heat*.35);
 vColor+=vec3(.9,1.,1.1)*coreE*(.6+beat*1.4);
 vVisibility=step(.08,uTime)*smoothRange(.45+delay,.75+delay,uTime);
 if(eye>.5)vVisibility*=smoothRange(6.9,7.8,uTime);
 vec4 mv=modelViewMatrix*vec4(p,1.);vView=mv.xyz;
 vRadius=mix(.006,uSize,body)*(1.+eye*.7)*(1.+heat*.7+edge*.5+coreE*.6);gl_PointSize=clamp(vRadius*2.*uPixelRatio*700./max(.2,-mv.z),1.,34.);
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
