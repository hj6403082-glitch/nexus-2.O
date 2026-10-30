export const humanVertex = `
attribute vec3 aSource; attribute vec3 aColor; attribute vec3 aNormal;
attribute float aCard; attribute float aSeed; attribute vec2 aCompute; attribute float aAO; attribute float aNode;
uniform mat4 uCards[10]; uniform float uTime; uniform float uPixelRatio; uniform float uSize;
uniform vec2 uHead; uniform vec2 uMouth; uniform vec2 uEye; uniform float uJaw; uniform float uFlare; uniform float uReturn; uniform float uClock;
uniform sampler2D uDisplace; uniform float uComputeSize; uniform float uUnder; uniform float uNet;
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
 float stagger=(1.-clamp((position.y-.3)/.9,0.,1.))*.9+aSeed*.25;
 float body=smoothRange(3.6+stagger,7.4,uTime);
 float presence=smoothRange(6.5,8.,uTime);
 vec3 rnd=vec3(sin(aSeed*91.),cos(aSeed*73.),sin(aSeed*51.));
 vec3 core=rnd*.10+vec3(0.,.1,2.7);
 // Resolve the final surface point first so every phase can aim at it.
 vec3 target=position; vec3 n=aNormal;
 if(target.y>.26){
   vec3 pivot=vec3(0.,.43,0.);
   // Speech moves the mouth only: the jaw and lower lip hinge open with a soft
   // falloff (no seam), the upper lip lifts slightly.
   float jaw=(1.-smoothRange(.47,.497,target.y))*smoothRange(.30,.37,target.y)*(1.-smoothRange(.15,.25,abs(target.x)))*smoothRange(0.,.14,target.z);
   if(jaw>0.){mat3 open=rx(uJaw*.2*jaw);target=vec3(0.,.56,0.)+open*(target-vec3(0.,.56,0.));n=open*n;}
   // Lip shapes: wide for bright vowels, rounded and pushed forward for "oo".
   float lips=(1.-smoothRange(.6,1.,length(vec2(target.x/.12,(target.y-.488)/.06))))*smoothRange(.2,.28,target.z);
   target.x*=1.+(uMouth.x*.14-uMouth.y*.2)*lips;target.z+=uMouth.y*.025*lips;
   target.y+=uJaw*.012*smoothRange(.495,.505,target.y)*(1.-smoothRange(.53,.56,target.y))*(1.-smoothRange(.08,.12,abs(target.x)))*step(.25,target.z);
   mat3 head=ry(uHead.x)*rx(uHead.y);target=pivot+head*(target-pivot);n=head*n;
 }
 // Only the head is shown, so it is enlarged and centred in the frame.
 target=(target-vec3(0.,.76,0.))*3.1+vec3(0.,.45,3.0);
 // GPGPU ferrofluid: sample this particle's simulated offset and add it, so the
 // surface seethes like magnetic fluid in zero-g once the figure has formed.
 vec3 disp=vec3(0.);
 if(uComputeSize>0.) disp=texture2D(uDisplace,aCompute).xyz;
 target+=disp*body*1.5;
 // Touch ripple: a ring of swelling particles expands from where the user
 // tapped the figure and fades out, so the body visibly reacts to a touch.
 float poke=0.;
 if(uPoke.w>=0.){float pd=distance(target,uPoke.xyz);poke=exp(-pow((pd-uPoke.w*.8)*6.,2.))*exp(-uPoke.w*1.1)*body;}
 target+=aNormal*poke*.14;

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
 // Three-point studio light: a warm-white key from upper left, a cool fill
 // and a cyan rim, all shaded by the baked occlusion so creases fall into shadow.
 vec3 nn=normalize(n);
 vec3 key=normalize(vec3(-.55+sin(uClock*.21)*.12,.7,1.));float facing=clamp(dot(nn,key),0.,1.);
 float fill=clamp(dot(nn,normalize(vec3(.8,-.1,.7))),0.,1.);
 // Occlusion is kept soft: deep per-bead shadows read as holes in the skin.
 float ao=mix(1.,.42+.58*pow(aAO,1.2),presence*.9+.1);
 vec3 blue=mix(vec3(.01,.08,.05),vec3(.36,.95,.68),pow(facing,1.1))+vec3(.04,.15,.10)*fill;
 blue+=vec3(.10,.14,.16)*pow(facing,18.); // soft specular sheen
 blue*=ao;
 blue+=vec3(.14,.42,.26)*pow(1.-abs(nn.z),3.)*presence; // rim
 float eye=step(.5,aSeed-1.); // last two particles have an explicit eye flag
 float blink=1.-step(.965,fract(uClock/4.7+.3))*presence;
 if(eye>.5)blue=mix(blue,vec3(.85,1.,.8)*(0.7+uFlare*0.7),smoothRange(6.9,7.8,uTime)*blink);
 // Glowing irises with dark pupils that glance around (uEye) and close in blinks.
 vec3 look=normalize(vec3(uEye*.35,1.));float iris=0.;
 for(int k=0;k<2;k++){vec3 q=position-vec3(k==0?.115:-.115,.752,.262);
  if(length(q/vec3(.052,.04,.045))<1.12&&position.z>.24&&eye<.5){float d=dot(normalize(q),look);iris=smoothRange(.76,.82,d);
   vec3 iris=mix(vec3(.55,.95,.15),vec3(1.05,1.2,.45),smoothRange(.86,.93,d))*(.7+uFlare*.6);
   vec3 c=mix(vec3(.22,.30,.36),iris,smoothRange(.78,.84,d));c=mix(c,vec3(.01,.02,.04),smoothRange(.95,.97,d));
   blue=mix(blue,c,presence*blink);}}
 // Lips read as a softer, paler material and brighten as they move.
 float lipTone=(1.-smoothRange(.65,1.,length(vec2(position.x/.11,(position.y-.488)/.05))))*step(.25,position.z);
 blue=mix(blue,vec3(.55,.95,.72)*(.45+.75*facing)*ao,lipTone*.5)+lipTone*uJaw*vec3(.12,.34,.20);
 // A faint holographic scan line drifts up the face while it is present.
 blue+=vec3(.10,.30,.18)*pow(.5+.5*sin(position.y*7.-uClock*2.2),48.)*presence;
 blue+=poke*vec3(.45,.95,.7);
 vColor=mix(aColor,blue,body);
 // Energy: in-flight particles run hot cyan, the forming front flares, the
 // core flashes white and dispersing motes glow gold. Values above 1 bloom.
 float heat=sin(gather*3.14159265)*(1.-body);
 float edge=sin(body*3.14159265);
 vColor+=vec3(.35,1.1,.65)*(heat*.6+edge*.85)*(1.-uReturn*.5);
 vColor+=vec3(1.1,.85,.5)*uReturn*(edge*.7+heat*.35);
 vColor+=vec3(.9,1.,1.1)*coreE*(.6+beat*1.4);
 vVisibility=step(.08,uTime)*smoothRange(.45+delay,.75+delay,uTime);
 if(eye>.5)vVisibility*=smoothRange(6.9,7.8,uTime);
 // Once formed the face is a net: threads between surface nodes (uNet pass),
 // small glowing knots where they meet, and the irises. Every other particle
 // fades out after carrying the transition.
 float formed=smoothRange(.7,1.,body)*(1.-uReturn);
 float knot=max(aNode,max(iris,eye));
 // Contrast lets the lighting carve the brow, nose, cheeks and lips out of the net.
 if(uNet>.5){vVisibility*=formed*(1.-eye);vColor=pow(max(vColor,vec3(0.)),vec3(1.7))*2.6+vec3(.01,.04,.025);}
 else if(uUnder<.5)vVisibility*=mix(1.,knot,formed);
 // Hidden depth pass: larger beads sunk well inside the surface so the back of
 // the head's net is hidden behind an invisible skull.
 float under=uUnder*smoothRange(.55,1.,body);
 if(uUnder>.5){p-=nn*.075;vVisibility*=step(.01,under)*(1.-eye);}
 vec4 mv=modelViewMatrix*vec4(p,1.);vView=mv.xyz;
 vRadius=mix(.006,uSize,body)*(1.+eye*.7)*(1.+heat*.7+edge*.5+coreE*.6)*(1.+under*1.5)*mix(1.,.38,formed*aNode*(1.-iris)*(1.-uUnder));gl_PointSize=clamp(vRadius*2.*uPixelRatio*700./max(.2,-mv.z),1.,34.);
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
 // Only a hint of per-bead shading: strong shading gave every bead a dark
 // crescent, which read as holes. The face lighting comes from the vertex shader.
 float beadLight=.86+.14*max(0.,dot(normalize(vec3(xy.x,-xy.y,z)),normalize(vec3(-.5,.7,1.))));
 gl_FragColor=vec4(vColor*beadLight,1.);
}`;

// The net's threads: lit like the surface and glowing, faded by visibility.
export const netFragment = `
precision highp float;
varying vec3 vColor;varying float vVisibility;
void main(){
 if(vVisibility<.02)discard;
 gl_FragColor=vec4(vColor,vVisibility*.85);
}`;
