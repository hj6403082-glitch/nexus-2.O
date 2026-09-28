'use client';
import { ScanFace, Orbit, Sparkles } from 'lucide-react';
import { useForm } from '@/stores/form';
import { useAssistant } from '@/stores/assistant';
import { useNexus } from '@/stores/nexus';
import type { AssistantController } from '@/ai/useAssistantController';
export function FormControls({ controller }: { controller: AssistantController }) {
  const form = useForm(), renderer = useNexus(s => s.renderer);
  return <>
    <nav className="form-switcher" aria-label="NEXUS form"><button aria-pressed={form.target === 'spatial'} onClick={() => void controller.send('Return to spatial mode')}><Orbit size={14} /> Spatial</button><button aria-pressed={form.target === 'human'} disabled={renderer === 'fallback'} onClick={() => void controller.send('Nexus, transform into a human shape')}><ScanFace size={14} /> Human</button></nav>
    {form.phase !== 'NORMAL' && <div className="form-status"><span className="eyebrow">{form.phase.replaceAll('_', ' ')}</span><p>{form.progress || (form.phase === 'HUMANOID_ACTIVE' ? "I'm here. How can I help?" : form.phase === 'RETURNING' ? 'Returning to your workspace.' : 'The same particles. A different presence.')}</p>{form.phase === 'HUMANOID_ACTIVE' && <button className="human-ask" onClick={() => useAssistant.getState().wake()}><Sparkles size={15} /> Talk to NEXUS</button>}</div>}
    {form.error && <div className="form-error" role="alert">{form.error}</div>}
  </>;
}
