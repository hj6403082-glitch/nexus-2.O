// Personal phrasing ("open my reels") resolves against the LIVE account feed.
// Nothing here knows a username or a profile URL ahead of time.
export type Destination = 'profile' | 'reels' | 'latest-post' | 'latest-reel';
export type InstagramFeed = { username?: string; media?: { permalink?: string; media_type?: string; media_product_type?: string; timestamp?: string }[] };
export const destinations: { id: Destination; name: string; pattern: RegExp }[] = [
  { id: 'reels', name: 'My reels', pattern: /^(?:my )?(?:instagram )?reels$/ },
  { id: 'latest-reel', name: 'My latest reel', pattern: /^(?:my )?(?:latest|last|newest|most recent) reel$/ },
  { id: 'latest-post', name: 'My latest post', pattern: /^(?:my )?(?:latest|last|newest|most recent) (?:instagram )?post$/ },
  { id: 'profile', name: 'My Instagram profile', pattern: /^(?:my )?(?:instagram(?: profile| account| page)?|profile|instagram)$/ },
];
export function matchDestination(phrase: string): Destination | null {
  const t = phrase.toLowerCase().trim();
  if (!/^my\b/.test(t)) return null;
  return destinations.find(d => d.pattern.test(t))?.id ?? null;
}
const instagramPermalink = (value?: string) => { try { const url = new URL(value ?? ''); return url.protocol === 'https:' && url.hostname === 'www.instagram.com' ? url.href : null; } catch { return null; } };
export function resolveDestination(id: Destination, feed: InstagramFeed): { url: string; label: string } | { error: string } {
  const username = feed.username && /^[A-Za-z0-9._]{1,30}$/.test(feed.username) ? feed.username : null;
  if (!username) return { error: 'Your Instagram feed did not return a username. Check the Instagram connection in the Instagram module.' };
  const profile = `https://www.instagram.com/${encodeURIComponent(username)}/`;
  if (id === 'profile') return { url: profile, label: `@${username}` };
  if (id === 'reels') return { url: `${profile}reels/`, label: `@${username} reels` };
  const media = [...(feed.media ?? [])].sort((a, b) => (b.timestamp ?? '').localeCompare(a.timestamp ?? ''));
  const item = media.find(m => id === 'latest-reel' ? m.media_product_type === 'REELS' || (m.media_type === 'VIDEO' && m.permalink?.includes('/reel/')) : true);
  const url = instagramPermalink(item?.permalink);
  return url ? { url, label: id === 'latest-reel' ? 'your latest reel' : 'your latest post' } : { error: `Your feed has no ${id === 'latest-reel' ? 'reels' : 'posts'} to open.` };
}
