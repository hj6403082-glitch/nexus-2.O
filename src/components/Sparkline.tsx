// A line that draws itself once, then holds perfectly still.
export function Sparkline({ values, label, width = 480, height = 72 }: { values: number[]; label: string; width?: number; height?: number }) {
  if (values.length < 2) return null;
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1, pad = 4;
  const points = values.map((v, i) => `${(i / (values.length - 1) * (width - pad * 2) + pad).toFixed(1)},${(height - pad - (v - min) / span * (height - pad * 2)).toFixed(1)}`).join(' ');
  return <svg className="sparkline" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} preserveAspectRatio="none"><polyline points={points} pathLength={1} /></svg>;
}
