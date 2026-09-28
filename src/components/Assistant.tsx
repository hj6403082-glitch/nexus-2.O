'use client';
import { useEffect, useRef, useState } from 'react';
import { ArrowUp, ExternalLink, History, Mic, MicOff, RefreshCw, Sparkles, Square, Trash2, Volume2, VolumeX, X } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { useAssistant, voiceSignal } from '@/stores/assistant';
import { useNexus } from '@/stores/nexus';
import { recognitionConstructor } from '@/ai/speech';
import type { AssistantController } from '@/ai/useAssistantController';

function VoiceMeter() {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => { let frame: number; const tick = () => { ref.current?.style.setProperty('--voice-level', String(voiceSignal.level)); frame = requestAnimationFrame(tick); }; frame = requestAnimationFrame(tick); return () => cancelAnimationFrame(frame); }, []);
  return <div ref={ref} className="voice-meter" aria-hidden="true">{Array.from({ length: 17 }, (_, i) => <i key={i} style={{ '--bar': .25 + Math.sin(i * 2.3) ** 2 * .75 } as React.CSSProperties} />)}</div>;
}
export function Assistant({ controller }: { controller: AssistantController }) {
  const state = useAssistant();
  const [voices, setVoices] = useState<SpeechSynthesisVoice[]>([]), [history, setHistory] = useState(false);
  const [voiceAvailable, setVoiceAvailable] = useState(false), [micAvailable, setMicAvailable] = useState(false);
  const end = useRef<HTMLDivElement>(null), input = useRef<HTMLInputElement>(null);
  const lastUser = state.messages.filter(m => m.role === 'user').at(-1);
  const last = state.messages.filter(m => m.role === 'assistant').at(-1);
  const busy = ['Thinking', 'Streaming', 'Speaking'].includes(state.status);
  useEffect(() => {
    setMicAvailable(!!recognitionConstructor()); setVoiceAvailable('speechSynthesis' in window);
    if (!('speechSynthesis' in window)) return;
    const update = () => setVoices(speechSynthesis.getVoices()); update();
    speechSynthesis.addEventListener('voiceschanged', update);
    return () => speechSynthesis.removeEventListener('voiceschanged', update);
  }, []);
  useEffect(() => { if (state.visible) input.current?.focus({ preventScroll: true }); }, [state.visible]);
  useEffect(() => { end.current?.scrollIntoView({ block: 'nearest', behavior: 'instant' }); }, [last?.text]);
  if (!state.visible) return null;
  return <motion.section className="assistant-panel" aria-label="NEXUS AI assistant" initial={{ opacity: 0, x: 25 }} animate={{ opacity: 1, x: 0 }} exit={{ opacity: 0, x: 20 }} transition={{ type: 'spring', stiffness: 130, damping: 23 }}>
    <header className="assistant-heading"><span className="assistant-symbol"><Sparkles size={18} /></span><div><strong>NEXUS</strong><span>{state.status.toUpperCase()} {state.microphone ? '· MIC ON' : ''}</span></div><button className="icon-button" onClick={() => { controller.interrupt(false); controller.stopMicrophone(); useAssistant.setState({ visible: false, status: 'Idle' }); }} aria-label="Close AI assistant"><X size={18} /></button></header>
    <VoiceMeter />
    <div className="assistant-context"><span>{useNexus.getState().expanded ? `${useNexus.getState().expanded?.toUpperCase()} CONTEXT` : 'SPATIAL CONTEXT'}</span><span>{state.configured ? 'GEMINI CONNECTED' : 'LOCAL COMMANDS READY'}</span></div>
    <div className="assistant-response" aria-live="polite" aria-busy={busy}>
      {history ? <div className="conversation-history">{state.messages.filter(m => m.text).map(m => <div key={m.id}><span className="eyebrow">{m.role === 'user' ? 'YOU' : 'NEXUS'}{m.interrupted ? ' · INTERRUPTED' : ''}{m.failed ? ' · INCOMPLETE' : ''}</span><p>{m.text}</p></div>)}{!state.messages.length && <p className="muted">Your conversation will appear here. History stays in this session.</p>}</div> : <>
        {lastUser && <p className="assistant-question">{lastUser.text}</p>}
        {last?.text ? <p className="holographic-text">{last.text.split(/(\s+)/).map((word, i) => /\s/.test(word) ? word : <motion.span key={`${last.id}-${i}`} initial={{ opacity: 0, filter: 'blur(5px)', y: 3 }} animate={{ opacity: 1, filter: 'blur(0px)', y: 0 }} transition={{ type: 'spring', stiffness: 150, damping: 24 }}>{word}</motion.span>)}{last.interrupted && <small className="response-note">Interrupted</small>}</p> : state.status === 'Thinking' ? <p className="holographic-text muted">Thinking<span className="thinking-dots">…</span></p> : <div className="assistant-welcome"><span className="eyebrow">A LITTLE MORE CONTEXT.</span><h2>What’s on your mind?</h2><p>Ask a question, open a module, or explore an idea.</p></div>}
        {state.link && <a className="assistant-link" href={state.link.url} target="_blank" rel="noopener noreferrer">{state.link.label}<ExternalLink size={15} /></a>}
      </>}
      <div ref={end} />
    </div>
    {state.error && <div className="assistant-error" role="alert">{state.error}</div>}
    {state.configured === false && !state.error && <div className="assistant-setup"><strong>Connect Gemini to ask questions.</strong><p>Set <code>GEMINI_API_KEY</code> in <code>.env.local</code> and restart NEXUS. Module commands work now.</p><button onClick={() => void controller.refresh()}><RefreshCw size={12} /> Check connection</button></div>}
    {!state.messages.length && <div className="assistant-suggestions">{['Open system', 'Rotate left', 'Explain MCP'].map(q => <button key={q} onClick={() => void controller.send(q)}>{q}</button>)}</div>}
    {state.transcript && <p className="live-transcript">{state.transcript}</p>}
    <form className="assistant-composer" onSubmit={e => { e.preventDefault(); setHistory(false); void controller.send(state.draft); }}><input ref={input} value={state.draft} onChange={e => useAssistant.setState({ draft: e.target.value })} maxLength={3000} placeholder="Ask NEXUS…" aria-label="Message NEXUS" /><button className="icon-button" type="button" aria-label={state.microphone ? 'Stop microphone' : 'Enable microphone'} aria-pressed={state.microphone} title={micAvailable ? 'Listen now, then say Nexus to wake again' : 'Speech recognition unavailable in this browser'} onClick={controller.toggleMicrophone}>{state.microphone ? <MicOff size={17} /> : <Mic size={17} />}</button>{busy ? <button className="send-button" type="button" onClick={() => controller.interrupt()} aria-label="Interrupt response"><Square size={14} /></button> : <button className="send-button" type="submit" disabled={!state.draft.trim()} aria-label="Send message"><ArrowUp size={18} /></button>}</form>
    <div className="assistant-settings"><button onClick={() => useAssistant.setState({ voice: !state.voice })} disabled={!voiceAvailable} aria-pressed={state.voice}>{state.voice ? <Volume2 size={14} /> : <VolumeX size={14} />} Voice {state.voice ? 'on' : 'off'}</button><button onClick={() => setHistory(!history)} aria-pressed={history}><History size={14} /> History</button><button onClick={controller.clear} aria-label="Clear conversation"><Trash2 size={14} /></button></div>
    {state.voice && <label className="voice-choice">Voice<select aria-label="Speaking voice" value={state.voiceURI} onChange={e => useAssistant.setState({ voiceURI: e.target.value })}><option value="">Best available</option>{voices.map(v => <option key={v.voiceURI} value={v.voiceURI}>{v.name} · {v.lang}</option>)}</select></label>}
    <p className="voice-privacy">{state.microphone ? 'Say “Nexus” to wake. Use headphones for reliable interruption. Browser speech recognition may use its provider’s servers.' : 'Voice is opt-in. Conversation history stays in this tab; questions sent to Gemini include recent context.'}</p>
  </motion.section>;
}
export function WakeWave() {
  const wakeAt = useAssistant(s => s.wakeAt);
  return <AnimatePresence>{wakeAt > 0 && <motion.div key={wakeAt} className="wake-wave" aria-hidden="true" initial={{ opacity: .45, scale: .15 }} animate={{ opacity: 0, scale: 2.8 }} transition={{ type: 'spring', stiffness: 22, damping: 12 }} />}</AnimatePresence>;
}
