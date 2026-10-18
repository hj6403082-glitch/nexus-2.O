'use client';
import { useForm } from '@/stores/form';
// Screen-space layer for the embodiment transition: the ignition flash and
// shockwave when the particle core lights, the scan that sweeps the figure as
// it materialises, and the chromatic bloom as it disperses. Pure CSS driven by
// the --form-* variables HumanForm writes each frame (no React re-renders).
export function FormFX() {
  const phase = useForm(s => s.phase);
  if (phase === 'NORMAL') return null;
  return <div className="form-fx" aria-hidden="true" data-phase={phase}><i className="fx-flash" /><i className="fx-ring" /><i className="fx-ring fx-ring-2" /><i className="fx-scan" /><i className="fx-return" /><i className="fx-grain" /></div>;
}
const STAGES = [['COLLAPSING', 'Gather'], ['PARTICLE_CORE', 'Ignite'], ['SKELETON_FORMING', 'Frame'], ['HUMANOID_FORMING', 'Form'], ['HUMANOID_ACTIVE', 'Present']] as const;
export function FormRail() {
  const phase = useForm(s => s.phase);
  const at = STAGES.findIndex(([id]) => id === phase);
  return <div className="form-rail" data-returning={phase === 'RETURNING' || undefined}><div className="form-rail-track"><i /></div><ol>{STAGES.map(([id, label], i) => <li key={id} data-state={phase === 'RETURNING' ? 'return' : i < at ? 'done' : i === at ? 'now' : 'next'}>{label}</li>)}</ol></div>;
}
