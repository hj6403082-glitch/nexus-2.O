'use client';
import { useEffect, useMemo, useState } from 'react';
import { ArrowUpRight, Globe, Search, UserRound } from 'lucide-react';
import { Dialog } from './Dialog';
import { ModuleIcon } from './Icon';
import { modules } from '@/lib/modules';
import { rankEntries } from '@/lib/rank';
import { useNexus } from '@/stores/nexus';
import { useAssistant } from '@/stores/assistant';
import { sites } from '@/lib/sites';
import { destinations } from '@/knowledge/destinations';
import { matchWebsite } from '@/ai/protocol';
import { executeCommand, openDestination, openWebsite } from '@/ai/commands';
type Source = 'MODULE' | 'WEB' | 'YOU';
type Entry = { key: string; name: string; source: Source; run: () => string | Promise<string> | void; icon?: string };
const icons: Record<Source, React.ReactNode> = { MODULE: null, WEB: <Globe size={20} strokeWidth={1.35} />, YOU: <UserRound size={20} strokeWidth={1.35} /> };
// ⌘K: modules, websites and personal destinations in one ranked list.
export function Launcher() {
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState(''), [busy, setBusy] = useState(false), [cursor, setCursor] = useState(0);
  const link = useAssistant(s => s.link), close = useNexus(s => s.close), open = useNexus(s => s.open);
  const entries = useMemo(() => {
    const all: Entry[] = [
      ...modules.map(m => ({ key: `m:${m.id}`, name: m.name, source: 'MODULE' as const, icon: m.icon, run: () => { useNexus.setState({ launcher: false }); open(m.id); } })),
      ...sites.map(site => ({ key: `w:${site.url}`, name: site.name, source: 'WEB' as const, run: () => openWebsite(site.url, site.name) })),
      ...destinations.map(d => ({ key: `y:${d.id}`, name: d.name, source: 'YOU' as const, run: () => openDestination(d.id) })),
    ];
    const ranked = rankEntries(all, query);
    // A typed address ("github.com/vercel") leads the list.
    const parsed = query.trim() ? matchWebsite(`open ${query.trim()}`) : null;
    if (parsed?.type === 'website' && !sites.some(site => site.url === parsed.url)) ranked.unshift({ key: 'parsed', name: query.trim(), source: 'WEB', run: () => executeCommand(parsed) });
    return ranked;
  }, [query, open]);
  useEffect(() => setCursor(0), [query]);
  const activate = async (entry?: Entry) => {
    if (!entry || busy) return; useAssistant.setState({ link: null });
    const result = entry.run(); if (!result) return;
    setBusy(true); setStatus('Working…');
    try { setStatus(await result); } finally { setBusy(false); }
  };
  return <Dialog title="QUICK ACCESS" onClose={close} className="launcher"><label className="launcher-search"><Search size={20} /><input autoFocus value={query} onChange={e => setQuery(e.target.value)} placeholder="Modules, websites, your pages…" aria-label="Find a module or website" aria-activedescendant={entries[cursor] ? `launch-${cursor}` : undefined} onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(entries.length - 1, c + 1)); } if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(0, c - 1)); } if (e.key === 'Enter') { e.preventDefault(); void activate(entries[cursor]); } }} /></label>
    {(status || link) && <p className="launcher-status" role="status">{status}{link && <> <a href={link.url} target="_blank" rel="noreferrer">{link.label} ↗</a></>}</p>}
    <div className="launcher-results" role="listbox">{entries.length ? entries.slice(0, 40).map((entry, i) => <button key={entry.key} id={`launch-${i}`} role="option" aria-selected={i === cursor} className={i === cursor ? 'cursor' : ''} disabled={busy} onMouseEnter={() => setCursor(i)} onClick={() => void activate(entry)}>{entry.icon ? <ModuleIcon name={entry.icon} /> : icons[entry.source]}<span>{entry.name}</span><small>{entry.source}</small><ArrowUpRight size={15} /></button>) : <p className="muted">Nothing matches “{query}”.</p>}</div></Dialog>;
}
