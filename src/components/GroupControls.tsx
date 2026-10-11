'use client';
import { modules } from '@/lib/modules';
import { useNexus } from '@/stores/nexus';
export function GroupControls() {
  const selected = useNexus(s => s.selected), grouped = useNexus(s => s.grouped), toggleSelect = useNexus(s => s.toggleSelect), setGrouped = useNexus(s => s.setGrouped);
  return <details className="group-controls"><summary>Group modules {selected.length ? `· ${selected.length}` : ''}</summary><div className="group-menu"><p>Choose the modules to gather, or none to gather the whole orbit.</p><div className="group-options">{modules.map(m => <label key={m.id}><input type="checkbox" checked={selected.includes(m.id)} onChange={() => toggleSelect(m.id)} />{m.name}</label>)}</div><p>With both hands open, bring them together to group or apart to split. Pinching with both hands still zooms. The G key and shift-click on the orbit dots work too.</p><button onClick={() => setGrouped(!grouped)}>{grouped ? 'Split into orbit' : selected.length ? 'Group selected modules' : 'Group all modules'}</button></div></details>;
}
