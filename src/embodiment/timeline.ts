export const FORM_DURATION = 8;
export type FormPhase = 'NORMAL' | 'COMMAND_DETECTED' | 'COLLAPSING' | 'PARTICLE_CORE' | 'SKELETON_FORMING' | 'HUMANOID_FORMING' | 'HUMANOID_ACTIVE' | 'RETURNING';
export const smooth = (a: number, b: number, value: number) => { const t = Math.max(0, Math.min(1, (value - a) / (b - a))); return t * t * (3 - 2 * t); };
export function envelopes(time: number) {
  return { dim: smooth(0, 1.3, time), dissolve: smooth(.5, 2.6, time), collapse: smooth(.6, 3.1, time), core: smooth(2.2, 3.1, time) * (1 - smooth(3.8, 5.2, time)), skeleton: smooth(3.5, 4.5, time), body: smooth(4.3, 7.4, time), eyes: smooth(6.9, 7.8, time), presence: smooth(6.5, 8, time) };
}
export class FormTimeline {
  time = 0;
  target: 'human' | 'spatial' = 'spatial';
  step(delta: number, ready: boolean) {
    if (this.target === 'human') this.time = Math.min(ready ? FORM_DURATION : .45, this.time + Math.min(delta, .05));
    else this.time = Math.max(0, this.time - Math.min(delta, .05) * 1.7);
    return this.time;
  }
  get phase(): FormPhase {
    if (this.target === 'spatial' && this.time > 0) return 'RETURNING';
    if (this.time === 0) return 'NORMAL';
    if (this.time < .5) return 'COMMAND_DETECTED';
    if (this.time < 3.1) return 'COLLAPSING';
    if (this.time < 3.5) return 'PARTICLE_CORE';
    if (this.time < 4.4) return 'SKELETON_FORMING';
    if (this.time < 8) return 'HUMANOID_FORMING';
    return 'HUMANOID_ACTIVE';
  }
}
