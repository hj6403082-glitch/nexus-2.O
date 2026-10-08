'use client';
import { ArrowUpRight } from 'lucide-react';
import { AccountModule } from './AccountModules';
import { DesktopControls } from './DesktopControls';
import { MachineTelemetry } from './MachineTelemetry';
import { LocalCollection, LiveFeed, MusicPlayer } from './KnowledgeModules';
import { Dialog } from './Dialog';
import { ModuleIcon } from './Icon';
import { moduleById } from '@/lib/modules';
import { useForm } from '@/stores/form';
import { useNexus } from '@/stores/nexus';
import { useAssistant } from '@/stores/assistant';
const closeMainPanel = () => useNexus.setState({ expanded: null });
const closePinnedPanel = () => useNexus.setState({ pinned: null });
export function ModulePanel({ pinned = false }: { pinned?: boolean }) {
  const id = useNexus(s => pinned ? s.pinned : s.expanded), close = pinned ? closePinnedPanel : closeMainPanel;
  const embodied = useForm(s => s.phase === 'HUMANOID_ACTIVE');
  const fps = useNexus(s => s.fps), gpu = useNexus(s => s.gpu), quality = useNexus(s => s.quality), tracking = useNexus(s => s.tracking), renderer = useNexus(s => s.renderer);
  if (!id) return null; const module = moduleById(id);
  return <Dialog title={`${module.category} / ${module.id.toUpperCase()}`} onClose={close} className={`module-panel${pinned ? ' pinned-panel' : ''}`}>
    <span className="panel-module-icon" style={{ color: module.accent }}><ModuleIcon name={module.icon} size={30} /></span><h2>{module.name}</h2><p className="panel-subtitle">{module.subtitle}</p>
    {id === 'system' ? <><div className="diagnostics"><div><span>Render rate</span><strong>{renderer === 'fallback' ? '—' : fps || '—'} <small>FPS</small></strong></div><div><span>Quality</span><strong>{quality === 'high' ? 'Full' : 'Adaptive'}</strong></div><div><span>Input</span><strong>{tracking === 'tracking' ? 'Hand' : 'Pointer'}</strong></div><div><span>Renderer</span><strong>{renderer === 'fallback' ? '2D' : 'WebGL 2'}</strong></div></div><p className="gpu-name">{gpu}</p><p className="muted">Rendering diagnostics above; local machine measurements below.</p><MachineTelemetry /><DesktopControls /></> : id === 'stocks' || id === 'sports' || id === 'instagram' ? <AccountModule key={id} kind={id} /> : id === 'projects' || id === 'calendar' ? <LocalCollection key={id} kind={id} /> : id === 'weather' || id === 'news' ? <LiveFeed key={id} kind={id} /> : id === 'music' ? <MusicPlayer /> : <div className="connection-state"><span className="eyebrow">PHASE {module.phase} · AWAITING CONNECTION</span><p>{module.description}</p><span className="muted">The spatial controls are ready. No account is connected yet.</span></div>}
    <div className="panel-actions"><button className="text-button" onClick={close}>{embodied ? 'Dismiss panel' : 'Return to orbit'} <ArrowUpRight size={16} /></button><button className="text-button" onClick={() => useAssistant.getState().wake()}>Ask NEXUS about this</button>{embodied && !pinned && <button className="text-button" onClick={() => useNexus.setState({ pinned: id, expanded: null, launcher: true })}>Keep beside me · open another</button>}</div>
  </Dialog>;
}
export function HelpPanel() {
  const close = useNexus(s => s.close);
  return <Dialog title="INPUT GUIDE / 01" onClose={close} className="help-panel"><h2>A little more natural.</h2><p className="panel-subtitle">Keep one hand visible, about an arm’s length from the camera.</p><div className="gesture-guide">{[['Swipe left / right', 'Move an open hand sideways to turn the orbit.'], ['Pinch & release', 'Bring thumb and index finger together to grab. Release to return the card.'], ['Pull / push', 'While pinching, move your hand toward the camera to open; away to close.'], ['Hold an open palm', 'Hold still for a moment to pause ambient movement.'], ['Two-hand zoom', 'Pinch with both hands and move them apart or together to adjust orbit scale.'], ['Draw a circle', 'Wake the AI assistant. Microphone permission remains opt-in.']].map(([a, b]) => <div key={a}><strong>{a}</strong><p>{b}</p></div>)}</div><div className="keyboard-guide"><span><kbd>←</kbd><kbd>→</kbd> Rotate</span><span><kbd>Enter</kbd> Open</span><span><kbd>Esc</kbd> Return</span><span><kbd>H</kbd> HUD</span><span><kbd>Ctrl / ⌘ K</kbd> Modules</span></div><p className="privacy-note">Camera frames are processed on this device. NEXUS does not upload or record them.</p></Dialog>;
}
export { Launcher } from './Launcher';
