'use client';
import { useEffect, useState } from 'react';
import { Activity, ArrowLeft, ArrowRight, AudioLines, Camera, Command, Hand, HelpCircle, LockKeyhole, ScanLine, Sparkles, Volume2, X } from 'lucide-react';
import { modules, wrapIndex } from '@/lib/modules';
import { useNexus } from '@/stores/nexus';
import { useAssistant } from '@/stores/assistant';
export function Hud({ onTracking, onAudio, onAI }: { onTracking: () => void; onAudio: () => void; onAI: () => void }) {
  const state = useNexus();
  const microphone = useAssistant(s => s.microphone);
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => { setNow(new Date()); const id = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(id); }, []);
  const selected = modules[wrapIndex(state.index)];
  const trackingOn = ['loading', 'searching', 'tracking'].includes(state.tracking);
  return <>
    {state.hud && <>
      <header className="topbar"><div className="brand"><span className="brand-mark">N</span><span>NEXUS<small>SPATIAL OPERATING SYSTEM</small></span><span className="version">01.00</span></div><div className="top-center"><i />{state.renderer === 'fallback' ? 'ACCESSIBLE MODE' : 'SPATIAL ENGINE ONLINE'}</div><div className="clock"><time>{now?.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', hour12: false }) ?? '—:—'}</time><span>{now?.toLocaleDateString('en-GB', { weekday: 'short', day: '2-digit', month: 'short' }).toUpperCase() ?? 'LOCAL TIME'}</span></div></header>
      <aside className="system-stats"><div><span className="status-led" />SYSTEM NOMINAL</div><p><span>RENDER</span><b>{state.renderer === 'fallback' ? '2D FALLBACK' : `${state.fps || '—'} FPS`}</b></p><p><span>TRACKING</span><b>{state.tracking.toUpperCase()}</b></p><p><span>GPU</span><b title={state.gpu}>{state.renderer === 'fallback' ? 'UNAVAILABLE' : 'WEBGL 2'}</b></p></aside>
      <div className="workspace-heading"><span className="eyebrow">YOUR WORLD, WITHIN REACH</span><h1>Make space.</h1><p>Less between you and everything.</p></div>
      <div className="orbit-label"><span className="eyebrow">ORBIT / {String(wrapIndex(state.index) + 1).padStart(2, '0')}</span><span className="orbit-rule" /><span>{selected.category}</span></div>
      <aside className="system-log"><span className="eyebrow">SESSION LOG <span className="log-line" /></span>{state.logs.slice(-3).map(log => <p key={log.id}><time>{log.time}</time><span>{log.message}</span></p>)}</aside>
      <aside className="gesture-status"><div className="gesture-label"><ScanLine size={16} /><span>{state.tracking === 'tracking' ? state.gesture.toUpperCase() : state.tracking === 'searching' ? 'SHOW YOUR HAND' : 'AWAITING GESTURE'}</span></div><div className="confidence"><span>HANDEDNESS</span><div><i style={{ width: `${state.confidence * 100}%` }} /></div><b>{Math.round(state.confidence * 100)}%</b></div><p>{trackingOn ? 'ONE HAND · LOCAL PROCESSING' : 'POINTER + KEYBOARD READY'}</p></aside>
    </>}
    <div className="top-actions"><button className="small-control ai-wake-button" onClick={onAI} aria-label="Ask NEXUS"><Sparkles size={13} />{microphone ? 'NEXUS · MIC ON' : 'ASK NEXUS'}</button><button className={`small-control ${state.drift ? 'enabled' : ''}`} onClick={() => useNexus.setState({ drift: !state.drift })} aria-pressed={state.drift} title="Toggle ambient motion">{state.drift ? <Activity size={13} /> : <LockKeyhole size={13} />} {state.frozen ? 'HELD' : state.drift ? 'DRIFT' : 'LOCKED'}</button><button className="icon-button" aria-label="Open module launcher" onClick={() => useNexus.setState({ launcher: true })}><Command size={16} /></button></div>
    {state.trackingError && <div className="error-toast" role="alert"><Camera size={20} /><p>{state.trackingError}</p><button className="icon-button" aria-label="Dismiss camera error" onClick={() => useNexus.setState({ trackingError: null })}><X size={16} /></button></div>}
    <nav className="orbit-controls" aria-label="Orbit controls"><div className="orbit-pagination">{modules.map((m, i) => <button key={m.id} className={wrapIndex(state.index) === i ? 'selected' : ''} aria-label={`Select ${m.name}`} aria-current={wrapIndex(state.index) === i ? 'true' : undefined} onClick={() => state.select(m.id)}><span /></button>)}</div><div className="control-dock"><button className="dock-arrow" aria-label="Rotate left" onClick={() => state.rotate(-1)}><ArrowLeft size={18} /></button><div className="dock-divider" /><button className={`tracking-button ${trackingOn ? 'tracking-on' : ''}`} onClick={onTracking}><Hand size={19} /><span>{state.tracking === 'loading' ? 'Starting camera…' : trackingOn ? 'Stop hand tracking' : 'Enable hand tracking'}</span>{trackingOn ? <span className="status-led" /> : <span className="key-hint">CAM</span>}</button><div className="dock-divider" /><button className="dock-arrow" aria-label="Rotate right" onClick={() => state.rotate(1)}><ArrowRight size={18} /></button></div><span className="control-caption">{trackingOn ? 'PINCH TO GRAB · PULL TO OPEN' : 'OR USE ARROW KEYS TO EXPLORE · ENTER TO OPEN'}</span></nav>
    <footer className="bottom-strip"><span>PRIVATE BY DESIGN <span className="footer-cross">+</span> BUILT AROUND YOU</span><div><button onClick={onAudio} aria-pressed={state.audio}>{state.audio ? <Volume2 size={14} /> : <AudioLines size={14} />} SOUND {state.audio ? 'ON' : 'OFF'}</button><span className="footer-divider" /><button onClick={() => useNexus.setState({ help: true })}><HelpCircle size={14} /> CONTROLS</button></div></footer>
  </>;
}
