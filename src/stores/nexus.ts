import { create } from 'zustand';
import { modules, wrapIndex, type ModuleId } from '@/lib/modules';
import { useAssistant } from './assistant';
import { useForm } from './form';
export type TrackingStatus = 'off' | 'loading' | 'searching' | 'tracking' | 'error';
export type Gesture = 'None' | 'Open palm' | 'Closed hand' | 'Pinch' | 'Release' | 'Swipe left' | 'Swipe right' | 'Pull' | 'Push' | 'Hold' | 'Circle';
type Log = { id: number; time: string; message: string };
interface NexusState {
  index: number; expanded: ModuleId | null; pinned: ModuleId | null; hovered: ModuleId | null; dragging: ModuleId | null;
  drift: boolean; frozen: boolean; audio: boolean; hud: boolean; help: boolean; launcher: boolean;
  tracking: TrackingStatus; trackingError: string | null; gesture: Gesture; confidence: number;
  fps: number; gpu: string; quality: 'high' | 'low'; renderer: 'webgl' | 'fallback'; logs: Log[];
  warnings: ModuleId[]; setWarning: (id: ModuleId, warned: boolean) => void;
  selected: ModuleId[]; grouped: boolean; toggleSelect: (id: ModuleId) => void; setGrouped: (grouped: boolean) => void;
  rotate: (direction: number) => void; select: (id: ModuleId) => void; open: (id?: ModuleId) => void;
  close: () => void; log: (message: string) => void;
}
export const useNexus = create<NexusState>((set, get) => ({
  index: 2, expanded: null, pinned: null, hovered: null, dragging: null,
  drift: false, frozen: false, audio: false, hud: true, help: false, launcher: false,
  tracking: 'off', trackingError: null, gesture: 'None', confidence: 0,
  fps: 0, gpu: 'Detecting', quality: 'high', renderer: 'webgl', logs: [], warnings: [], selected: [], grouped: false,
  setWarning: (id, warned) => set(s => ({ warnings: warned ? (s.warnings.includes(id) ? s.warnings : [...s.warnings, id]) : s.warnings.filter(w => w !== id) })),
  toggleSelect: id => set(s => ({ selected: s.selected.includes(id) ? s.selected.filter(m => m !== id) : [...s.selected, id] })),
  setGrouped: grouped => { set(s => ({ grouped, selected: grouped ? s.selected : [] })); get().log(grouped ? 'Cards grouped' : 'Cards spread to orbit'); },
  rotate: direction => { if (get().dragging || useForm.getState().phase !== 'NORMAL') return; set(s => ({ index: s.index + direction, expanded: null })); },
  select: id => {
    const current = get().index;
    const wanted = modules.findIndex(m => m.id === id);
    let diff = wanted - wrapIndex(current);
    if (diff > 5) diff -= 10;
    if (diff < -5) diff += 10;
    set({ index: current + diff, expanded: null });
  },
  open: id => { const selected = id ?? modules[wrapIndex(get().index)].id; get().select(selected); if (selected === 'ai') { set({ dragging: null }); useAssistant.getState().wake(); } else set({ expanded: selected, pinned: get().pinned === selected ? null : get().pinned, dragging: null }); get().log(`${selected.toUpperCase()} · focused`); },
  close: () => set({ expanded: null, pinned: null, dragging: null, help: false, launcher: false, grouped: false, selected: [] }),
  log: message => set(s => ({ logs: [...s.logs.slice(-4), { id: Date.now() + Math.random(), time: new Date().toLocaleTimeString('en-GB', { hour12: false }), message }] })),
}));
// Hot tracking data never causes React renders at camera frame rate.
export const handSignal = { x: 0.5, y: 0.5, scale: 0, visible: false, pinching: false, zoom: 1 };
