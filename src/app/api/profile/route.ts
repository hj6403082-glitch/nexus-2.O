import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { localRequestAllowed } from '@/ai/server';
import { parseProfile } from '@/ai/companion';
export const dynamic = 'force-dynamic';
// The owner's private profile (zeno-profile.json beside the app, never
// committed) so Zeno knows them from the very first launch.
export async function GET(request: Request) {
  if (!localRequestAllowed(request)) return Response.json({ error: 'Local, same-origin requests only.' }, { status: 403 });
  try {
    const text = await readFile(path.join(process.cwd(), 'zeno-profile.json'), 'utf8');
    return Response.json(parseProfile(JSON.parse(text.replace(/^﻿/, ''))), { headers: { 'Cache-Control': 'no-store' } });
  } catch { return Response.json({ name: null, facts: [] }, { headers: { 'Cache-Control': 'no-store' } }); }
}
