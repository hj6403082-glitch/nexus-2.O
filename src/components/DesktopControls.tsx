'use client';
import { useEffect, useState } from 'react';
import { verbLabels } from '@/desktop/verbs';
import { desktopAction } from '@/desktop/client';
export function DesktopControls() {
  const [status, setStatus] = useState<{ supported: boolean; enabled: boolean; message: string } | null>(null), [verb, setVerb] = useState('apps'), [value, setValue] = useState(''), [result, setResult] = useState(''), [busy, setBusy] = useState(false);
  useEffect(() => { const abort = new AbortController(); void fetch('/api/desktop', { signal: abort.signal }).then(r => r.json()).then(setStatus).catch(() => {}); return () => abort.abort(); }, []);
  return <section className="knowledge"><h3>Desktop bridge</h3><p className="muted">{status?.message ?? 'Checking desktop capabilities…'}</p>{status?.supported && status.enabled && <form onSubmit={async e => { e.preventDefault(); setBusy(true); try { setResult((await desktopAction({ verb: verb as keyof typeof verbLabels, value })).message); } finally { setBusy(false); } }}><select aria-label="Desktop action" value={verb} onChange={e => setVerb(e.target.value)}>{Object.entries(verbLabels).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select><input aria-label="Desktop action value" value={value} onChange={e => setValue(e.target.value)} placeholder="App name, https:// address, 0–100, play / next, on / off, or text" /><button className="text-button" disabled={busy}>{busy ? 'Working…' : 'Run action'}</button></form>}{result && <p role="status">{result}</p>}</section>;
}
