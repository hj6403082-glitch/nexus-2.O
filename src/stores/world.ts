import { create } from 'zustand';
// Phase 6 — six world-specific filmic grades. Each splits the ends of the blue
// luminance ramp differently: `shadow` tints the darks, `highlight` the brights,
// mid-tones are left alone. `contrast` pivots at 18% grey; `halation` is the
// amount of warm bleed around the brightest pixels. A world change reads as a
// cinematic cut because these move together.
export type WorldGrade = { contrast: number; warmth: number; shadow: [number, number, number]; highlight: [number, number, number]; halation: number };
export const worlds = [
  { name: 'Minimal Studio', fog: '#101925', light: '#c1dbec', grid: '#304458', grade: { contrast: 1, warmth: 0, shadow: [.022, 0, .05], highlight: [.02, .014, 0], halation: .12 } },
  { name: 'Dark Lab', fog: '#050815', light: '#9dacf2', grid: '#242d54', grade: { contrast: 1.12, warmth: -.1, shadow: [.03, 0, .085], highlight: [.01, .01, .028], halation: .1 } },
  { name: 'Glass Observatory', fog: '#0d2029', light: '#bde9f0', grid: '#345b68', grade: { contrast: 1.04, warmth: -.03, shadow: [.01, .006, .045], highlight: [.015, .025, .03], halation: .16 } },
  { name: 'Industrial Command Center', fog: '#181614', light: '#d9c8a2', grid: '#514938', grade: { contrast: 1.2, warmth: .15, shadow: [.04, .012, .01], highlight: [.05, .035, 0], halation: .14 } },
  { name: 'Ocean Platform', fog: '#061c28', light: '#81cce9', grid: '#225970', grade: { contrast: 1.08, warmth: -.2, shadow: [.004, .01, .06], highlight: [0, .018, .04], halation: .13 } },
  { name: 'Fog Chamber', fog: '#18202a', light: '#c5d5df', grid: '#3b4b57', grade: { contrast: .82, warmth: .02, shadow: [.028, .02, .045], highlight: [.045, .04, .035], halation: .26 } },
] as const satisfies readonly { name: string; fog: string; light: string; grid: string; grade: WorldGrade }[];
export const useWorld = create<{ index: number; weatherCode: number; set: (index: number) => void }>(set => ({ index: 0, weatherCode: 0, set: index => set({ index: Math.max(0, Math.min(5, index)) }) }));
