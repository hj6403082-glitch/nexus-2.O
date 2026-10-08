export function instagramTarget(token: string, account?: string) {
  if (token.startsWith('IGAA')) return { base: 'https://graph.instagram.com', account: 'me' };
  if (token.startsWith('EAA') && account && /^\d+$/.test(account)) return { base: 'https://graph.facebook.com', account };
  throw new Error('Instagram Login needs an IGAA token; Facebook Login needs an EAA token and the business account ID.');
}
export function followerHistory(total: number, deltas: { date: string; delta: number }[]) {
  let running = total;
  return [...deltas].sort((a, b) => b.date.localeCompare(a.date)).map(item => { const point = { date: item.date, total: running }; running -= item.delta; return point; }).reverse();
}
export async function providerJson(url: string, headers: Record<string, string>) {
  const response = await fetch(url, { headers, signal: AbortSignal.timeout(12000), cache: 'no-store' });
  if (!response.ok) throw new Error(response.status === 429 ? 'Provider rate limit reached. Try again later.' : response.status === 401 || response.status === 403 ? 'The provider rejected the credentials or permissions. Check the server configuration.' : 'The provider could not return this data.');
  const value = await response.json(); if (value.error) throw new Error('The provider rejected this request. Check account permissions and configuration.'); return value;
}
type InsightSeries = { name?: string; values?: { value?: unknown; end_time?: string }[] };
// Instagram's follower_count insight is a DAILY DELTA (new follows that day), not a running total.
export function parseInsights(result: { data?: InsightSeries[] }) {
  const series = (name: string) => (result.data?.find(s => s.name === name)?.values ?? []).filter(v => typeof v.value === 'number' && typeof v.end_time === 'string').map(v => ({ date: v.end_time!.slice(0, 10), value: v.value as number }));
  return { deltas: series('follower_count').map(v => ({ date: v.date, delta: v.value })), reach: series('reach') };
}
export type MediaItem = { id: string; like_count?: number; comments_count?: number };
export function engagement(media: MediaItem[], followers?: number) {
  const scored = media.map(m => ({ id: m.id, interactions: (m.like_count ?? 0) + (m.comments_count ?? 0) }));
  const total = scored.reduce((sum, m) => sum + m.interactions, 0);
  return { rate: followers && media.length ? total / media.length / followers : null, top: [...scored].sort((a, b) => b.interactions - a.interactions).slice(0, 3).map(m => m.id) };
}
