'use client';
import { worlds, useWorld } from '@/stores/world';
import { handSignal } from '@/stores/nexus';
import { useForm } from '@/stores/form';
import { GroupControls } from './GroupControls';
export function WorldControls() {
  const { index, set } = useWorld();
  const phase = useForm(s => s.phase);
  if (phase !== 'NORMAL') return null;
  return <div className="world-controls"><span>ENVIRONMENT</span><select aria-label="Environment" value={index} onChange={e => set(Number(e.target.value))}>{worlds.map((world, i) => <option value={i} key={world.name}>{world.name}</option>)}</select><button aria-label="Zoom out" onClick={() => { handSignal.zoom = Math.max(.75, handSignal.zoom - .1); }}>−</button><button aria-label="Reset zoom" onClick={() => { handSignal.zoom = 1; }}>1:1</button><button aria-label="Zoom in" onClick={() => { handSignal.zoom = Math.min(1.35, handSignal.zoom + .1); }}>+</button><GroupControls /></div>;
}
