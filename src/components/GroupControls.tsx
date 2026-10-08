'use client';
import { modules } from '@/lib/modules';
import { useNexus } from '@/stores/nexus';
export function GroupControls() {
  const selected = useNexus(s => s.groupSelection), grouped = useNexus(s => s.grouped), mode = useNexus(s => s.twoHandMode);
  return <details className="group-controls"><summary>Group modules {selected.length ? `· ${selected.length}` : ''}</summary><div className="group-menu"><p>Choose two or three modules.</p><div className="group-options">{modules.map(m => <label key={m.id}><input type="checkbox" checked={selected.includes(m.id)} disabled={!selected.includes(m.id) && selected.length >= 3} onChange={e => useNexus.setState({ groupSelection: e.target.checked ? [...selected, m.id] : selected.filter(id => id !== m.id), grouped: false })} />{m.name}</label>)}</div><label>Two-hand gesture<select aria-label="Two-hand gesture mode" value={mode} onChange={e => useNexus.setState({ twoHandMode: e.target.value as 'zoom' | 'group' })}><option value="zoom">Zoom</option><option value="group">Group / split</option></select></label><p>In Group mode, pinch with both hands, then bring them together to group or apart to split. Release before repeating.</p><button disabled={selected.length < 2} onClick={() => useNexus.setState({ grouped: !grouped })}>{grouped ? 'Split into orbit' : 'Group selected modules'}</button></div></details>;
}
