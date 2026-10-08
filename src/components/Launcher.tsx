'use client';
import { useEffect, useMemo, useState } from 'react';
import { AppWindow, ArrowUpRight, Globe, Search, UserRound, Zap } from 'lucide-react';
import { Dialog } from './Dialog';
import { ModuleIcon } from './Icon';
import { modules } from '@/lib/modules';
import { rankEntries } from '@/lib/rank';
import { useNexus } from '@/stores/nexus';
import { useAssistant } from '@/stores/assistant';
import { sites } from '@/desktop/sites';
import { installedAppNames } from '@/desktop/client';
import { destinations } from '@/knowledge/destinations';
import { matchDesktop } from '@/ai/protocol';
import { executeCommand, openDestination, openWebsite, runDesktop } from '@/ai/commands';
type Source = 'MODULE' | 'APP' | 'WEB' | 'YOU' | 'ACTION';
type Entry = { key: string; name: string; source: Source; run: () => string | Promise<string> | void; icon?: string };
const actions: { name: string; command: string }[] = [
  { name: 'Play / pause', command: 'play/pause' }, { name: 'Next track', command: 'next track' }, { name: 'Previous track', command: 'previous track' },
  { name: 'Take a screenshot', command: 'take a screenshot' }, { name: 'Hide other apps', command: 'hide others' }, { name: 'Lock screen', command: 'lock screen' },
  { name: 'Sleep display', command: 'sleep display' }, { name: 'Do Not Disturb on', command: 'turn on do not disturb' }, { name: 'Do Not Disturb off', command: 'turn off do not disturb' },
  { name: 'Read clipboard', command: 'read clipboard' }, { name: 'List displays', command: 'show displays' }, { name: 'Mute', command: 'mute' },
];
const icons: Record<Source, React.ReactNode> = { MODULE: null, APP: <AppWindow size={20} strokeWidth={1.35} />, WEB: <Globe size={20} strokeWidth={1.35} />, YOU: <UserRound size={20} strokeWidth={1.35} />, ACTION: <Zap size={20} strokeWidth={1.35} /> };
// ⌘K: modules, installed apps, websites, personal destinations and desktop actions in one ranked list.
export function Launcher() {
  const [query, setQuery] = useState(''), [apps, setApps] = useState<string[]>([]), [desktop, setDesktop] = useState(false);
  const [status, setStatus] = useState(''), [busy, setBusy] = useState(false), [cursor, setCursor] = useState(0);
  const link = useAssistant(s => s.link), close = useNexus(s => s.close), open = useNexus(s => s.open);
  useEffect(() => {
    const abort = new AbortController();
    void fetch('/api/desktop', { signal: abort.signal }).then(r => r.json()).then(s => { if (s.supported && s.enabled) { setDesktop(true); void installedAppNames().then(names => { if (!abort.signal.aborted) setApps(names); }); } }).catch(() => {});
    return () => abort.abort();
  }, []);
  const entries = useMemo(() => {
    const all: Entry[] = [
      ...modules.map(m => ({ key: `m:${m.id}`, name: m.name, source: 'MODULE' as const, icon: m.icon, run: () => { useNexus.setState({ launcher: false }); open(m.id); } })),
      ...apps.map(name => ({ key: `a:${name}`, name, source: 'APP' as const, run: () => runDesktop({ verb: 'launch', value: name }) })),
      ...sites.map(site => ({ key: `w:${site.url}`, name: site.name, source: 'WEB' as const, run: () => openWebsite(site.url, site.name) })),
      ...destinations.map(d => ({ key: `y:${d.id}`, name: d.name, source: 'YOU' as const, run: () => openDestination(d.id) })),
      ...(desktop ? actions.map(a => ({ key: `x:${a.name}`, name: a.name, source: 'ACTION' as const, run: () => { const c = matchDesktop(a.command); return c ? executeCommand(c) : undefined; } })) : []),
    ];
    const ranked = rankEntries(all, query);
    // A typed instruction ("volume 30", "remind me to call Sam", "github.com/vercel") leads the list.
    const parsed = query.trim() ? matchDesktop(query.trim()) : null;
    if (parsed?.type === 'desktop' && !['launch', 'quit'].includes(parsed.request.verb) && (desktop || parsed.request.verb === 'website')) ranked.unshift({ key: 'parsed', name: query.trim(), source: parsed.request.verb === 'website' ? 'WEB' : 'ACTION', run: () => executeCommand(parsed) });
    return ranked;
  }, [apps, desktop, query, open]);
  useEffect(() => setCursor(0), [query]);
  const activate = async (entry?: Entry) => {
    if (!entry || busy) return; useAssistant.setState({ link: null });
    const result = entry.run(); if (!result) return;
    setBusy(true); setStatus('Working…');
    try { setStatus(await result); } finally { setBusy(false); }
  };
  return <Dialog title="QUICK ACCESS" onClose={close} className="launcher"><label className="launcher-search"><Search size={20} /><input autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder="Modules, apps, websites, actions…" aria-label="Find a module, app, website or action" aria-activedescendant={entries[cursor] ? `launch-${cursor}` : undefined} onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(entries.length - 1, c + 1)); } if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(0, c - 1)); } if (e.key === 'Enter') { e.preventDefault(); void activate(entries[cursor]); } }} /></label>
    {(status || link) && <p className="launcher-status" role="status">{status}{link && <> <a href={link.url} target="_blank" rel="noreferrer">{link.label} ↗</a></>}</p>}
    <div className="launcher-results" role="listbox">{entries.length ? entries.slice(0, 40).map((entry, i) => <button key={entry.key} id={`launch-${i}`} role="option" aria-selected={i === cursor} className={i === cursor ? 'cursor' : ''} disabled={busy} onMouseEnter={() => setCursor(i)} onClick={() => void activate(entry)}>{entry.icon ? <ModuleIcon name={entry.icon} /> : icons[entry.source]}<span>{entry.name}</span><small>{entry.source}</small><ArrowUpRight size={15} /></button>) : <p className="muted">Nothing matches “{query}”.{!desktop && ' Apps and desktop actions appear when the macOS bridge is enabled.'}</p>}</div></Dialog>;
}
