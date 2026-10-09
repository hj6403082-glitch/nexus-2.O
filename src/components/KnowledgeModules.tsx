'use client';
import { useEffect, useState } from 'react';
import { useKnowledge } from '@/stores/knowledge';
import { useWorld } from '@/stores/world';
import { useProject } from '@/stores/project';
import { ProjectMedia } from './ProjectMedia';
import { deleteProjectAssets } from '@/knowledge/media';
type Entry = { id: string; title: string; detail: string };
function useEntries(key: string) {
  const [entries, setEntries] = useState<Entry[]>([]), [loaded, setLoaded] = useState(false), [error, setError] = useState('');
  useEffect(() => { try { const value = JSON.parse(localStorage.getItem(`nexus:${key}`) || '[]'); if (Array.isArray(value)) setEntries(value.filter(x => typeof x.id === 'string' && typeof x.title === 'string' && typeof x.detail === 'string')); } catch { setError('Saved entries could not be read.'); } setLoaded(true); }, [key]);
  useEffect(() => { if (!loaded) return; try { localStorage.setItem(`nexus:${key}`, JSON.stringify(entries)); useKnowledge.getState().publish(key, entries); } catch { setError('Browser storage is full or unavailable. Changes are not saved.'); } }, [entries, loaded, key]);
  return { entries, setEntries, loaded, error, setError };
}
export function LocalCollection({ kind }: { kind: 'projects' | 'calendar' }) {
  const { entries, setEntries, loaded, error, setError } = useEntries(kind), [title, setTitle] = useState(''), [detail, setDetail] = useState('');
  return <section className="knowledge"><p className="muted">{kind === 'projects' ? 'Your local project library. Add notes and repository links.' : 'Your local agenda. Times use your device timezone.'} Saved in this browser.</p>
    <form onSubmit={e => { e.preventDefault(); if (!title.trim() || !detail.trim()) return; setEntries(v => [...v, { id: crypto.randomUUID(), title: title.trim(), detail }]); setTitle(''); setDetail(''); }}>
      <input aria-label={kind === 'projects' ? 'Project name' : 'Event title'} placeholder={kind === 'projects' ? 'Project name' : 'Event title'} value={title} maxLength={140} required onChange={e => setTitle(e.target.value)} />
      {kind === 'calendar' ? <input aria-label="Event date and time" type="datetime-local" required value={detail} onChange={e => setDetail(e.target.value)} /> : <textarea aria-label="Project notes" placeholder="Description, prompt history, GitHub URL…" value={detail} maxLength={5000} required onChange={e => setDetail(e.target.value)} />}
      <button className="text-button" disabled={!loaded}>Add {kind === 'projects' ? 'project' : 'event'} +</button>
    </form>{error && <p role="alert">{error}</p>}
    <div className="knowledge-list">{(kind === 'calendar' ? [...entries].sort((a, b) => a.detail.localeCompare(b.detail)) : entries).map(entry => <article key={entry.id}><h3>{entry.title}</h3><p>{kind === 'calendar' ? new Date(entry.detail).toLocaleString() : entry.detail}</p><div className="entry-actions">{kind === 'projects' && <button className="text-button" onClick={() => useProject.getState().enter({ id: entry.id, title: entry.title, detail: entry.detail })}>Enter world ↗</button>}<button className="text-button" onClick={async () => { try { if (kind === 'projects') { if (useProject.getState().focused?.id === entry.id) useProject.getState().exit(); await deleteProjectAssets(entry.id); } setEntries(v => v.filter(x => x.id !== entry.id)); } catch { setError('Could not remove this project and its media.'); } }}>Remove</button></div>{kind === 'projects' && <ProjectMedia project={entry.id} />}</article>)}{loaded && !entries.length && <p className="muted">No {kind === 'projects' ? 'projects' : 'events'} yet. Add your first above.</p>}</div>
  </section>;
}
type Weather = { place: string; current: { temperature_2m: number; relative_humidity_2m: number; wind_speed_10m: number; weather_code: number }; daily: { time: string[]; temperature_2m_max: number[]; temperature_2m_min: number[] }; fetchedAt: string; sourceUrl: string };
type News = { items: { id: number; title: string; url: string; score: number; time: number }[]; fetchedAt: string; sourceUrl: string };
export function LiveFeed({ kind }: { kind: 'weather' | 'news' }) {
  const [city, setCity] = useState(''), [data, setData] = useState<Weather | News | null>(null), [error, setError] = useState(''), [loading, setLoading] = useState(false);
  const load = async () => { setLoading(true); setError(''); try { const response = await fetch(`/api/knowledge?module=${kind}&city=${encodeURIComponent(city)}`); const value = await response.json(); if (!response.ok) throw new Error(value.error); setData(value); useKnowledge.getState().publish(kind, value); if (kind === 'weather') { const code = value.current?.weather_code; useWorld.setState({ weatherCode: Number.isFinite(code) ? code : 0 }); useWorld.getState().set(code >= 51 ? 4 : code >= 45 ? 5 : code > 0 ? 2 : 0); } } catch (e) { setError(e instanceof Error ? e.message : 'Could not load data.'); } finally { setLoading(false); } };
  return <section className="knowledge"><form onSubmit={e => { e.preventDefault(); void load(); }}>{kind === 'weather' && <input aria-label="Weather city" placeholder="City, region" value={city} maxLength={100} required onChange={e => setCity(e.target.value)} />}<button className="text-button" disabled={loading}>{loading ? 'Connecting…' : data ? 'Refresh' : kind === 'weather' ? 'Get weather' : 'Load technology headlines'} ↗</button></form>{error && <p role="alert">{error}</p>}
    {data && 'current' in data && <><h3>{data.place}</h3><div className="diagnostics"><div><span>Temperature</span><strong>{data.current.temperature_2m}°C</strong></div><div><span>Humidity</span><strong>{data.current.relative_humidity_2m}%</strong></div><div><span>Wind</span><strong>{data.current.wind_speed_10m}<small> km/h</small></strong></div></div><div className="forecast">{data.daily.time.map((day, i) => <div key={day}><span>{new Date(day + 'T12:00').toLocaleDateString(undefined, { weekday: 'short' })}</span><b>{data.daily.temperature_2m_max[i]}°</b><small>{data.daily.temperature_2m_min[i]}°</small></div>)}</div></>}
    {data && 'items' in data && <div className="knowledge-list">{data.items.map(item => <article key={item.id}><a href={item.url} target="_blank" rel="noreferrer"><h3>{item.title} ↗</h3></a><small>{item.score} points · {new Date(item.time * 1000).toLocaleDateString()}</small></article>)}</div>}
    {data && <p className="muted"><a href={data.sourceUrl} target="_blank" rel="noreferrer">{kind === 'weather' ? 'Open-Meteo' : 'Hacker News'}</a> · retrieved {new Date(data.fetchedAt).toLocaleTimeString()}. {kind === 'weather' ? 'Forecast model estimates.' : 'Headlines only; summaries must not imply the full article was read.'}</p>}
  </section>;
}
export function MusicPlayer() {
  const [track, setTrack] = useState<{ name: string; url: string } | null>(null);
  useEffect(() => () => { if (track) URL.revokeObjectURL(track.url); }, [track]);
  return <section className="knowledge"><p className="muted">Play an audio file from your device. It stays local.</p><input aria-label="Choose audio file" type="file" accept="audio/*" onChange={e => { const file = e.target.files?.[0]; if (file) setTrack({ name: file.name, url: URL.createObjectURL(file) }); }} />{track && <><h3>{track.name}</h3><audio controls src={track.url} style={{ width: '100%' }} /></>}</section>;
}
