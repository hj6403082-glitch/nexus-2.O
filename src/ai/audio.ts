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

export function createVoiceGraph(context: AudioContext): VoiceGraph {
  const input = context.createGain();
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

  input.connect(subBass); subBass.connect(comp);
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
      try { input.disconnect(); subBass.disconnect(); comp.disconnect(); dry.disconnect(); wet.disconnect(); reverb.disconnect(); panner.disconnect(); analyser.disconnect(); } catch { /* already gone */ }
      fftSignal.level = 0; fftSignal.bands.fill(0);
    },
  };
}
