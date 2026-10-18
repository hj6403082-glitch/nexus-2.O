// Cinematic audio processing for the voice of NEXUS (Phase 8, Objective 4) and
// the FFT signal the ferrofluid humanoid reads (Objective 3).
//
// Premium TTS audio (ElevenLabs) is routed through a Web Audio graph that gives
// the voice physical presence:
//   source -> sub-bass shelf (low-shelf lift) -> dynamics -> spatial reverb
//          -> panner (localised in the room) -> analyser -> destination
// The analyser feeds `fftSignal`: an overall level plus eight frequency bands
// that modulate the humanoid's surface-displacement shader in real time.

// Hot signal read every frame by the embodiment shader. No React re-renders.
export const fftSignal = { level: 0, bands: new Float32Array(8) };

// Build a short synthetic impulse response for a tight, localised reverb — a
// small resonant space so the voice feels like it comes from the entity in the
// centre of the room rather than a cathedral.
function buildImpulse(context: AudioContext, seconds = 0.9, decay = 3.2): AudioBuffer {
  const rate = context.sampleRate, length = Math.max(1, Math.floor(rate * seconds));
  const impulse = context.createBuffer(2, length, rate);
  for (let channel = 0; channel < 2; channel++) {
    const data = impulse.getChannelData(channel);
    for (let i = 0; i < length; i++) {
      // Early reflections plus an exponential tail.
      const t = i / length;
      data[i] = (Math.random() * 2 - 1) * Math.pow(1 - t, decay) * (0.6 + 0.4 * Math.sin(t * 40));
    }
  }
  return impulse;
}

export interface VoiceGraph {
  input: AudioNode;        // connect a TTS source here
  analyser: AnalyserNode;
  setPosition(x: number, y: number, z: number): void;
  update(): void;          // call per frame to refresh fftSignal
  dispose(): void;
}

// Voice characters. "ultron" is an original synthetic-menace treatment in the
// spirit of a film AI antagonist: a calm, deep human performance (the source is
// slowed slightly, which also lowers its pitch) layered with a detuned digital
// double, a faint ring-modulated metallic edge, a short comb resonance and soft
// saturation. It processes NEXUS's own neural voice; it does not imitate any
// real actor's voice. "natural" leaves the human voice clean.
export type VoiceStyle = 'ultron' | 'natural';
export const VOICE_STYLES: Record<VoiceStyle, { label: string; playbackRate: number; speed: number }> = {
  ultron: { label: 'Ultron-style synthetic', playbackRate: .9, speed: 1.08 },
  natural: { label: 'Natural human', playbackRate: 1, speed: 1 },
};
function softClip(amount: number) {
  const curve = new Float32Array(1024);
  for (let i = 0; i < curve.length; i++) { const x = i / (curve.length - 1) * 2 - 1; curve[i] = Math.tanh(x * amount) / Math.tanh(amount); }
  return curve;
}
// Builds the character layer between `input` and `output`; returns its nodes so
// they can be disconnected.
function characterChain(context: AudioContext, input: AudioNode, output: AudioNode, style: VoiceStyle): AudioNode[] {
  if (style === 'natural') { input.connect(output); return []; }
  const nodes: AudioNode[] = [];
  const add = <T extends AudioNode>(node: T) => { nodes.push(node); return node; };
  const sum = add(context.createGain()); sum.gain.value = 1;
  // Dry voice.
  const dry = add(context.createGain()); dry.gain.value = .9; input.connect(dry); dry.connect(sum);
  // Digital double: two short, slowly modulated delays (chorus) behind the voice.
  for (const [ms, rate] of [[11, .21], [17, .33]] as const) {
    const delay = add(context.createDelay(.05)); delay.delayTime.value = ms / 1000;
    const lfo = add(context.createOscillator()); lfo.frequency.value = rate;
    const depth = add(context.createGain()); depth.gain.value = .0018;
    lfo.connect(depth); depth.connect(delay.delayTime); lfo.start();
    const level = add(context.createGain()); level.gain.value = .32;
    input.connect(delay); delay.connect(level); level.connect(sum);
  }
  // Metallic edge: a little ring modulation at a low carrier.
  const ring = add(context.createGain()); ring.gain.value = 0;
  const carrier = add(context.createOscillator()); carrier.frequency.value = 52; carrier.start();
  carrier.connect(ring.gain);
  const ringLevel = add(context.createGain()); ringLevel.gain.value = .14;
  input.connect(ring); ring.connect(ringLevel); ringLevel.connect(sum);
  // Short comb resonance: the "inside a machine" colour.
  const comb = add(context.createDelay(.02)); comb.delayTime.value = .0042;
  const feedback = add(context.createGain()); feedback.gain.value = .38;
  const combLevel = add(context.createGain()); combLevel.gain.value = .16;
  input.connect(comb); comb.connect(feedback); feedback.connect(comb); comb.connect(combLevel); combLevel.connect(sum);
  // Weight and edge, then gentle saturation.
  const low = add(context.createBiquadFilter()); low.type = 'lowshelf'; low.frequency.value = 140; low.gain.value = 4;
  const presence = add(context.createBiquadFilter()); presence.type = 'peaking'; presence.frequency.value = 2900; presence.Q.value = 1.1; presence.gain.value = 3.5;
  const air = add(context.createBiquadFilter()); air.type = 'highshelf'; air.frequency.value = 9000; air.gain.value = -3;
  const shaper = add(context.createWaveShaper()); shaper.curve = softClip(1.6); shaper.oversample = '2x';
  sum.connect(low); low.connect(presence); presence.connect(air); air.connect(shaper); shaper.connect(output);
  return nodes;
}

export function createVoiceGraph(context: AudioContext, style: VoiceStyle = 'ultron'): VoiceGraph {
  const input = context.createGain();
  const shaped = context.createGain();
  const character = characterChain(context, input, shaped, style);
  // Sub-bass presence: lift the low shelf for physical weight.
  const subBass = context.createBiquadFilter();
  subBass.type = 'lowshelf'; subBass.frequency.value = 120; subBass.gain.value = 6.5;
  // A gentle compressor keeps the commanding voice even and present.
  const comp = context.createDynamicsCompressor();
  comp.threshold.value = -24; comp.ratio.value = 3; comp.attack.value = 0.004; comp.release.value = 0.18;
  // Dry/wet split into a tight spatial reverb.
  const dry = context.createGain(); dry.gain.value = 0.82;
  const wet = context.createGain(); wet.gain.value = 0.28;
  const reverb = context.createConvolver(); reverb.buffer = buildImpulse(context);
  // Localise the voice in the room, slightly ahead of the listener.
  const panner = context.createPanner();
  panner.panningModel = 'HRTF'; panner.distanceModel = 'inverse';
  panner.refDistance = 1; panner.maxDistance = 20; panner.rolloffFactor = 1.2;
  panner.positionZ.value = -1.5;
  const analyser = context.createAnalyser();
  analyser.fftSize = 512; analyser.smoothingTimeConstant = 0.78;

  shaped.connect(subBass); subBass.connect(comp);
  comp.connect(dry); comp.connect(reverb); reverb.connect(wet);
  dry.connect(panner); wet.connect(panner);
  panner.connect(analyser); analyser.connect(context.destination);

  const bins = new Uint8Array(analyser.frequencyBinCount);
  return {
    input, analyser,
    setPosition(x, y, z) { try { panner.positionX.value = x; panner.positionY.value = y; panner.positionZ.value = z; } catch { /* older impls */ } },
    update() {
      analyser.getByteFrequencyData(bins as Uint8Array<ArrayBuffer>);
      const per = Math.floor(bins.length / 8) || 1; let total = 0;
      for (let b = 0; b < 8; b++) {
        let sum = 0; for (let i = 0; i < per; i++) sum += bins[b * per + i];
        const v = sum / per / 255; fftSignal.bands[b] = v; total += v;
      }
      fftSignal.level = Math.min(1, total / 8 * 1.6);
    },
    dispose() {
      try { for (const node of character) { node.disconnect(); if (node instanceof OscillatorNode) node.stop(); } input.disconnect(); shaped.disconnect(); subBass.disconnect(); comp.disconnect(); dry.disconnect(); wet.disconnect(); reverb.disconnect(); panner.disconnect(); analyser.disconnect(); } catch { /* already gone */ }
      fftSignal.level = 0; fftSignal.bands.fill(0);
    },
  };
}
