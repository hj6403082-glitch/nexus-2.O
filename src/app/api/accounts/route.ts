import { localRequestAllowed } from '@/ai/server';
import { instagramTarget, providerJson } from '@/knowledge/providers';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
  if (!localRequestAllowed(request)) return Response.json({ error: 'Local requests only.' }, { status: 403 });
  const params = new URL(request.url).searchParams, module = params.get('module');
  try {
    if (module === 'stocks') {
      const token = process.env.FINNHUB_API_KEY;
      if (!token) return Response.json({ error: 'Connect Finnhub by setting FINNHUB_API_KEY on the server, then restart NEXUS.' }, { status: 503 });
      const symbol = (params.get('symbol') || 'NVDA').toUpperCase();
      if (!/^[A-Z][A-Z0-9.-]{0,14}$/.test(symbol)) return Response.json({ error: 'Enter a valid market symbol.' }, { status: 400 });
      const quote = await providerJson(`https://finnhub.io/api/v1/quote?symbol=${encodeURIComponent(symbol)}`, { 'X-Finnhub-Token': token });
      if (!quote.t || !Number.isFinite(quote.c)) throw new Error('No quote is available for that symbol.');
      return Response.json({ symbol, price: quote.c, change: quote.d, percent: quote.dp, high: quote.h, low: quote.l, timestamp: quote.t, source: 'Finnhub', fetchedAt: new Date().toISOString() });
    }
    if (module === 'sports') {
      const token = process.env.FOOTBALL_DATA_TOKEN;
      if (!token) return Response.json({ error: 'Connect football-data.org by setting FOOTBALL_DATA_TOKEN on the server, then restart NEXUS.' }, { status: 503 });
      if (params.get('view') === 'standings') {
        const competition = params.get('competition') || 'PL';
        if (!['PL', 'PD', 'BL1', 'SA', 'FL1'].includes(competition)) return Response.json({ error: 'Choose a supported league.' }, { status: 400 });
        const result = await providerJson(`https://api.football-data.org/v4/competitions/${competition}/standings`, { 'X-Auth-Token': token });
        const total = result.standings?.find((standing: { type: string }) => standing.type === 'TOTAL');
        if (!total?.table) throw new Error('Standings are unavailable for this league and account.');
        return Response.json({ source: 'football-data.org', fetchedAt: new Date().toISOString(), competition: result.competition?.name || competition, standings: total.table.slice(0, 30).map((row: { position: number; team: { id: number; name: string }; playedGames: number; won: number; draw: number; lost: number; points: number; goalDifference: number }) => ({ position: row.position, id: row.team.id, name: row.team.name, played: row.playedGames, won: row.won, drawn: row.draw, lost: row.lost, points: row.points, difference: row.goalDifference })) });
      }
      const result = await providerJson('https://api.football-data.org/v4/matches', { 'X-Auth-Token': token });
      return Response.json({ source: 'football-data.org', fetchedAt: new Date().toISOString(), matches: (result.matches ?? []).slice(0, 20).map((m: { id: number; utcDate: string; status: string; homeTeam: { name: string }; awayTeam: { name: string }; score: { fullTime: { home: number | null; away: number | null } } }) => ({ id: m.id, date: m.utcDate, status: m.status, home: m.homeTeam.name, away: m.awayTeam.name, score: m.score.fullTime })) });
    }
    if (module === 'instagram') {
      const token = process.env.INSTAGRAM_ACCESS_TOKEN;
      if (!token) return Response.json({ error: 'Connect your professional Instagram account by setting INSTAGRAM_ACCESS_TOKEN on the server.' }, { status: 503 });
      const target = instagramTarget(token, process.env.INSTAGRAM_BUSINESS_ID);
      const profile = await providerJson(`${target.base}/${target.account}?fields=id,username,followers_count,media_count`, { Authorization: `Bearer ${token}` });
      const media = await providerJson(`${target.base}/${profile.id}/media?fields=id,caption,media_type,permalink,timestamp,like_count,comments_count&limit=8`, { Authorization: `Bearer ${token}` });
      return Response.json({ source: 'Instagram Graph API', fetchedAt: new Date().toISOString(), username: profile.username, followers: profile.followers_count, mediaCount: profile.media_count, url: `https://www.instagram.com/${encodeURIComponent(profile.username)}/`, media: media.data ?? [] });
    }
    return Response.json({ error: 'Unknown account module.' }, { status: 400 });
  } catch (error) { return Response.json({ error: error instanceof Error ? error.message : 'Connection failed.' }, { status: 502 }); }
}
