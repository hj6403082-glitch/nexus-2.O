'use client';
import { worlds, useWorld } from '@/stores/world';
export function WorldControls() {
  const { index, set } = useWorld();
  return <label className="world-controls"><span>ENVIRONMENT</span><select aria-label="Environment" value={index} onChange={e => set(Number(e.target.value))}>{worlds.map((world, i) => <option value={i} key={world.name}>{world.name}</option>)}</select></label>;
}
