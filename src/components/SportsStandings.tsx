'use client';
import { useState } from 'react';
import { useKnowledge } from '@/stores/knowledge';
type Standings = { competition: string; fetchedAt: string; standings: { id: number; position: number; name: string; played: number; points: number; difference: number }[] };
export function SportsStandings() {
  const [league, setLeague] = useState('PL'), [data, setData] = useState<Standings | null>(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  return <section><h3>League standings</h3><form onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError('');
    try { const response = await fetch(`/api/accounts?module=sports&view=standings&competition=${league}`); const result = await response.json(); if (!response.ok) throw new Error(result.error); setData(result); useKnowledge.getState().publish('sports', result); }
    catch (error) { setError(error instanceof Error ? error.message : 'Standings unavailable.'); }
    finally { setBusy(false); }
  }}><select aria-label="Football league" value={league} onChange={e => setLeague(e.target.value)}>{Object.entries({ PL: 'Premier League', PD: 'La Liga', BL1: 'Bundesliga', SA: 'Serie A', FL1: 'Ligue 1' }).map(([code, name]) => <option key={code} value={code}>{name}</option>)}</select><button className="text-button" disabled={busy}>{busy ? 'Loading standings…' : 'Load standings'}</button></form>
    {error && <p role="alert">{error}</p>}
    {data && <><h3>{data.competition}</h3><div className="standings-scroll"><table className="standings-table"><caption>Overall standings · P played, GD goal difference</caption><thead><tr><th scope="col">#</th><th scope="col">Team</th><th scope="col">P</th><th scope="col">GD</th><th scope="col">Pts</th></tr></thead><tbody>{data.standings.map(row => <tr key={row.id}><td>{row.position}</td><th scope="row">{row.name}</th><td>{row.played}</td><td>{row.difference}</td><td>{row.points}</td></tr>)}</tbody></table></div><p className="muted">football-data.org · retrieved {new Date(data.fetchedAt).toLocaleString()}</p></>}
  </section>;
}
