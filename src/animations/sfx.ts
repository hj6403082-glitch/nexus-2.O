// Synthesised sound design for Zeno transitions and the orb: no audio files,
// everything is built from oscillators and noise through a shared reverb.
// The audio context starts on the first click or key press (browsers require a
// gesture); until then, and when effects are muted, every cue is silent.
let context: AudioContext | null = null, master: GainNode | null = null, space: ConvolverNode | null = null, noise: AudioBuffer | null = null;
let enabled = true;
export function setSfxEnabled(on: boolean) { enabled = on; if (master && context) master.gain.setTargetAtTime(on ? .55 : 0, context.currentTime, .05); }
export function unlockSfx() {
  if (typeof AudioContext === 'undefined') return;
  try {
    if (!context) {
      context = new AudioContext(); master = context.createGain(); master.gain.value = enabled ? .55 : 0; master.connect(context.destination);
      space = context.createConvolver(); const length = context.sampleRate * 2.4, impulse = context.createBuffer(2, length, context.sampleRate);
      for (let c = 0; c < 2; c++) { const d = impulse.getChannelData(c); for (let i = 0; i < length; i++) d[i] = (Math.random() * 2 - 1) * Math.pow(1 - i / length, 2.6); }
      space.buffer = impulse; const wet = context.createGain(); wet.gain.value = .35; space.connect(wet); wet.connect(master);
      noise = context.createBuffer(1, context.sampleRate * 2, context.sampleRate); const n = noise.getChannelData(0); for (let i = 0; i < n.length; i++) n[i] = Math.random() * 2 - 1;
    }
    if (context.state === 'suspended') void context.resume().catch(() => {});
  } catch { context = null; }
}
const ready = () => enabled && context && master && space && context.state === 'running' ? { ctx: context, out: master, verb: space } : null;
function route(node: AudioNode, gain: number, verb = .6) {
  const r = ready(); if (!r) return null;
  const g = r.ctx.createGain(); g.gain.value = gain; node.connect(g); g.connect(r.out);
  const s = r.ctx.createGain(); s.gain.value = verb; g.connect(s); s.connect(r.verb);
  return g;
}
function tone(type: OscillatorType, from: number, to: number, start: number, length: number, peak: number, attack = .02, verb = .6) {
  const r = ready(); if (!r) return;
  const t = r.ctx.currentTime + start, osc = r.ctx.createOscillator(), env = r.ctx.createGain();
  osc.type = type; osc.frequency.setValueAtTime(from, t); osc.frequency.exponentialRampToValueAtTime(Math.max(1, to), t + length);
  env.gain.setValueAtTime(0.0001, t); env.gain.exponentialRampToValueAtTime(peak, t + attack); env.gain.exponentialRampToValueAtTime(0.0001, t + length);
  osc.connect(env); const out = route(env, 1, verb); if (!out) return;
  osc.start(t); osc.stop(t + length + .05); osc.onended = () => { osc.disconnect(); env.disconnect(); out.disconnect(); };
}
function whoosh(start: number, length: number, from: number, to: number, peak: number, filter: BiquadFilterType = 'bandpass') {
  const r = ready(); if (!r || !noise) return;
  const t = r.ctx.currentTime + start, src = r.ctx.createBufferSource(), band = r.ctx.createBiquadFilter(), env = r.ctx.createGain();
  src.buffer = noise; src.loop = true; band.type = filter; band.Q.value = 1.4;
  band.frequency.setValueAtTime(from, t); band.frequency.exponentialRampToValueAtTime(to, t + length);
  env.gain.setValueAtTime(0.0001, t); env.gain.exponentialRampToValueAtTime(peak, t + length * .7); env.gain.exponentialRampToValueAtTime(0.0001, t + length);
  src.connect(band); band.connect(env); const out = route(env, 1, .8); if (!out) return;
  src.start(t); src.stop(t + length + .05); src.onended = () => { src.disconnect(); band.disconnect(); env.disconnect(); out.disconnect(); };
}
export const sfx = {
  // Interface collapses inward: rising wind and a climbing drone.
  gather() { whoosh(0, 2.6, 180, 2600, .5); tone('sawtooth', 55, 110, 0, 2.6, .05, 1.6, .4); tone('sine', 110, 220, .2, 2.4, .08, 1.4); },
  // The core ignites: sub-bass drop, impact and a bright ping.
  ignite() { tone('sine', 90, 28, 0, 1.6, .9, .01, .3); whoosh(0, .6, 3000, 200, .6, 'lowpass'); tone('sine', 1760, 1760, .02, 1.8, .08, .005, 1); tone('triangle', 880, 870, .02, 1.4, .05, .005, 1); },
  // The scan sweeps the forming body.
  scan() { tone('sine', 1800, 3600, 0, 2.6, .035, .3, .9); tone('sine', 2400, 4800, .15, 2.4, .02, .3, .9); whoosh(0, 2.4, 6000, 9000, .06, 'highpass'); },
  // The figure is present: a resolved, warm chord.
  present() { [220, 329.63, 493.88, 659.25].forEach((f, i) => tone('sine', f, f, i * .07, 3.2, .09 - i * .012, .04, 1)); tone('triangle', 110, 110, 0, 2.4, .05, .2, .5); },
  // Dispersal: a falling rush and a scatter of glints.
  disperse() { whoosh(0, 2.2, 4000, 300, .45); for (let i = 0; i < 18; i++) { const f = 1800 + Math.random() * 3200; tone('sine', f, f * .98, Math.random() * 1.6, .35, .03, .005, 1); } },
  // Orb interaction.
  // A double-click shockwave: a soft thump and an outward rush.
  shock() { tone('sine', 120, 38, 0, .9, .6, .008, .4); whoosh(0, .9, 600, 4200, .35); },
  touch() { tone('sine', 660, 990, 0, .35, .07, .005, .8); tone('sine', 1320, 1320, .05, .5, .03, .005, 1); },
};
