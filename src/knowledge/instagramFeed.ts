'use client';
import type { InstagramFeed } from './destinations';
// Always read the live feed: personal destinations are never cached or hardcoded.
export async function liveInstagramFeed(): Promise<InstagramFeed | { error: string }> {
  try {
    const response = await fetch('/api/accounts?module=instagram', { cache: 'no-store' }); const data = await response.json();
    return response.ok ? data : { error: data.error || 'Instagram is unavailable.' };
  } catch { return { error: 'Instagram is unreachable. Check that NEXUS is still running.' }; }
}
