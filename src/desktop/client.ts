'use client';
import type { DesktopRequest } from './verbs';
export type DesktopResult = { ok: boolean; status: number; message: string; data?: Record<string, unknown> };
// One browser entry point for every desktop verb, used by voice and ⌘K alike.
export async function desktopAction(request: DesktopRequest): Promise<DesktopResult> {
  try {
    const response = await fetch('/api/desktop', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(request) });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) return { ok: false, status: response.status, message: data.error || `The desktop bridge refused the action (${response.status}).` };
    const message = data.message || (typeof data.text === 'string' ? (data.text ? `Clipboard: ${data.text.slice(0, 600)}` : 'The clipboard is empty.') : Array.isArray(data.apps) ? `${data.apps.length} installed apps: ${data.apps.slice(0, 40).join(', ')}${data.apps.length > 40 ? '…' : ''}` : 'Done.');
    return { ok: true, status: response.status, message, data };
  } catch { return { ok: false, status: 0, message: 'The desktop bridge is unreachable. Check that NEXUS is still running.' }; }
}
// 501 (not macOS) and 403 (bridge off) mean "no desktop here", not a failure of the action itself.
export const bridgeUnavailable = (result: DesktopResult) => !result.ok && (result.status === 501 || result.status === 403);
let appCache: Promise<string[]> | null = null;
export function installedAppNames() {
  appCache ??= desktopAction({ verb: 'apps' }).then(r => r.ok && Array.isArray(r.data?.apps) ? r.data.apps as string[] : []).catch(() => []);
  return appCache;
}
