import { Color } from 'three';
// Phase 6 — "Gold at the centre", with its three counter-intuitive rules.
// Gold hue (~47°) and Warning Orange (~29°) sit close on the wheel, so the
// two must never appear on the same card: the centred-card gold term is gated
// ENTIRELY on the warning flag.
export const GOLD = '#d8c074';      // ~47° — gold, drawn dim so it reads as gold, not white.
export const WARNING = '#e8913f';   // ~29° — warning orange, reserved for warned cards.
const gold = new Color(GOLD), warning = new Color(WARNING), accentColor = new Color();
// Earned gold: fades in continuously with centred position on a power curve,
// never a binary switch. `frontal` is cos(angle-to-camera) in [-1, 1].
export function goldAmount(frontal: number, warned: boolean) {
  if (warned) return 0;                       // Rule 1: a warned card is NEVER gold.
  return Math.pow(Math.max(0, frontal), 6);   // Rule 3: earned, a smooth power curve.
}
export type CardTint = { color: Color; intensity: number };
// Rule 2: gold must be drawn DIMMER than blue to read as gold; prominence comes
// from hue and (elsewhere) a wider outer bloom, never from an intensity > 1 that
// would clip red and green to white. Intensities stay below 1.
export function cardTint(accent: string, frontal: number, warned: boolean, out: CardTint): CardTint {
  if (warned) { out.color.copy(warning); out.intensity = 0.14; return out; }
  const g = goldAmount(frontal, warned);
  accentColor.set(accent);
  // Blue accent is the bright baseline; gold is deliberately drawn dimmer.
  const blueIntensity = 0.05 + Math.max(0, frontal) * 0.07;   // up to .12
  const goldIntensity = 0.03 + g * 0.05;                      // up to .08, always < blue's peak
  out.color.copy(accentColor).lerp(gold, g);
  out.intensity = blueIntensity * (1 - g) + goldIntensity * g;
  return out;
}
// A gold card earns a wider OUTER bloom rather than a brighter core.
export const goldBloom = (frontal: number, warned: boolean) => goldAmount(frontal, warned) * 0.6;
