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
