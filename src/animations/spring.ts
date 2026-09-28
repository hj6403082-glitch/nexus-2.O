// One motion vocabulary shared by the scene and the interface.
export const motion = {
  arriving: { stiffness: 130, damping: 23, mass: 1 },
  leaving: { stiffness: 180, damping: 27, mass: 1 },
  acknowledging: { stiffness: 280, damping: 22, mass: 1 },
  reporting: { stiffness: 100, damping: 25, mass: 1 },
  drifting: { stiffness: 22, damping: 10, mass: 1 },
} as const;
export type Spring = { value: number; velocity: number };
export function stepSpring(s: Spring, target: number, delta: number, stiffness = 100, damping = 22) {
  // Substeps are stable even after a slow frame. A settled spring is EXACTLY still.
  const dt = Math.min(delta, 0.064);
  const steps = Math.max(1, Math.ceil(dt / (1 / 120)));
  for (let i = 0; i < steps; i++) {
    s.velocity += ((target - s.value) * stiffness - s.velocity * damping) * dt / steps;
    s.value += s.velocity * dt / steps;
  }
  if (Math.abs(target - s.value) < 0.00001 && Math.abs(s.velocity) < 0.00001) {
    s.value = target; s.velocity = 0;
  }
  return s.value;
}
