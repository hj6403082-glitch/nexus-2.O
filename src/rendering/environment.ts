import { bridgeSignal } from '@/stores/bridge';

// Shared, render-loop-friendly signals for the adaptive kinetic environment
// (Phase 8, Objective 5). None of these cause React re-renders; the scene reads
// them every frame.

// Ambient room loudness from the opt-in microphone, 0..1 (smoothed). Procedural
// fog density and dust drift follow it.
export const ambientSignal = { level: 0 };

// Eased thermal load, 0..1. Driven by the Windows bridge: it ramps up while the
// bridge is processing a task and relaxes back. The post-processing grade blends
// from deep cobalt toward violet/cyan as this rises.
export const thermalSignal = { load: 0 };

// Call once per frame from a single owner (the World loop). Advances the eased
// bridge-load value that the thermal LUT reads.
export function stepEnvironment(dt: number) {
  const ease = 1 - Math.exp(-dt * (bridgeSignal.target > thermalSignal.load ? 2.4 : 0.8));
  bridgeSignal.load += (bridgeSignal.target - bridgeSignal.load) * ease;
  thermalSignal.load = bridgeSignal.load;
  return thermalSignal.load;
}

// A violet-shadow / cyan-highlight bias added to any world grade in proportion
// to thermal load. Returned as additive tint deltas and a warmth delta.
export function thermalShift(load: number) {
  const k = Math.max(0, Math.min(1, load));
  return {
    shadow: [0.05 * k, -0.01 * k, 0.11 * k] as [number, number, number], // violet pushed into darks
    highlight: [-0.03 * k, 0.03 * k, 0.06 * k] as [number, number, number], // cyan into brights
    warmth: -0.18 * k, // cool the whole frame
    contrast: 0.12 * k,
  };
}
