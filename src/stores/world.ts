import { create } from 'zustand';
export const worlds = [
  { name: 'Minimal Studio', fog: '#101925', light: '#c1dbec', grid: '#304458', contrast: 1, warmth: 0 },
  { name: 'Dark Lab', fog: '#050815', light: '#9dacf2', grid: '#242d54', contrast: 1.12, warmth: -.1 },
  { name: 'Glass Observatory', fog: '#0d2029', light: '#bde9f0', grid: '#345b68', contrast: 1.04, warmth: -.03 },
  { name: 'Industrial Command Center', fog: '#181614', light: '#d9c8a2', grid: '#514938', contrast: 1.2, warmth: .15 },
  { name: 'Ocean Platform', fog: '#061c28', light: '#81cce9', grid: '#225970', contrast: 1.08, warmth: -.2 },
  { name: 'Fog Chamber', fog: '#18202a', light: '#c5d5df', grid: '#3b4b57', contrast: .85, warmth: .02 },
] as const;
export const useWorld = create<{ index: number; weatherCode: number; set: (index: number) => void }>(set => ({ index: 0, weatherCode: 0, set: index => set({ index: Math.max(0, Math.min(5, index)) }) }));
