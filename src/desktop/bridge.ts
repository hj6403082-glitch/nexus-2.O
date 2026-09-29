import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { readdir } from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
const runFile = promisify(execFile);
const run = async (file: string, args: string[]) => (await runFile(file, args, { timeout: 15000, maxBuffer: 1024 * 1024 })).stdout.trim();
export const verbs = ['apps', 'launch', 'quit', 'website', 'volume', 'clipboard-read', 'clipboard-write', 'sleep-display', 'note', 'reminder'] as const;
export type DesktopVerb = typeof verbs[number];
export type DesktopRequest = { verb: DesktopVerb; value?: string };
export function validateDesktop(value: unknown): DesktopRequest | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (!verbs.includes(data.verb as DesktopVerb) || (data.value !== undefined && (typeof data.value !== 'string' || data.value.length > 10000))) return null;
  return { verb: data.verb as DesktopVerb, value: data.value as string | undefined };
}
export async function installedApps() {
  const apps: { name: string; path: string }[] = [];
  for (const root of ['/Applications', '/System/Applications', path.join(homedir(), 'Applications')]) {
    const scan = async (folder: string, depth: number) => {
      for (const entry of await readdir(folder, { withFileTypes: true }).catch(() => [])) {
        if (entry.name.endsWith('.app')) apps.push({ name: entry.name.slice(0, -4), path: path.join(folder, entry.name) });
        else if (entry.isDirectory() && depth < 1) await scan(path.join(folder, entry.name), depth + 1);
      }
    }; await scan(root, 0);
  }
  return apps;
}
export function resolveApp(apps: { name: string; path: string }[], name: string) { return apps.find(app => app.name.toLocaleLowerCase() === name.trim().toLocaleLowerCase()); }
const script = (body: string, args: string[] = []) => run('/usr/bin/osascript', ['-e', `on run argv\n${body}\nend run`, ...args]);
export function permissionMessage(error: unknown) {
  const message = error instanceof Error ? error.message : '';
  if (message.includes('-1743') || /not authorized/i.test(message)) return 'Allow the terminal running NEXUS in System Settings → Privacy & Security → Automation, then retry.';
  if (/assistive|accessibility|1002/i.test(message)) return 'Allow the terminal running NEXUS in System Settings → Privacy & Security → Accessibility.';
  if (/could not create image|screen capture/i.test(message)) return 'Allow the terminal running NEXUS in System Settings → Privacy & Security → Screen Recording, then restart it.';
  return 'macOS could not complete the action. Check the application and its permissions, then retry.';
}
const handlers: Record<DesktopVerb, (value: string) => Promise<unknown>> = {
  apps: async () => ({ apps: (await installedApps()).map(a => a.name) }),
  launch: async value => { const app = resolveApp(await installedApps(), value); if (!app) throw new Error('No such installed application.'); await run('/usr/bin/open', ['-a', app.path]); return { message: `Opened ${app.name}.` }; },
  quit: async value => { const app = resolveApp(await installedApps(), value); if (!app) throw new Error('No such installed application.'); await script('tell application (item 1 of argv) to quit', [app.path]); return { message: `Requested graceful quit for ${app.name}. Unsaved-work prompts remain under your control.` }; },
  website: async value => { const url = new URL(value); if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) throw new Error('Use an HTTP or HTTPS website address.'); const chrome = resolveApp(await installedApps(), 'Google Chrome'); if (chrome) await run('/usr/bin/open', ['-a', chrome.path, '--args', '--new-window', url.href]); else await script('tell application "Safari"\nactivate\nmake new document with properties {URL:item 1 of argv}\nend tell', [url.href]); return { message: 'Opened a dedicated browser window. Display placement is not configured.' }; },
  volume: async value => { const level = Number(value); if (!/^\d{1,3}$/.test(value) || level > 100) throw new Error('Volume must be between 0 and 100.'); await script('set volume output volume ((item 1 of argv) as integer)', [String(level)]); return { message: `Volume set to ${level}%.` }; },
  'clipboard-read': async () => ({ text: await run('/usr/bin/pbpaste', []) }),
  'clipboard-write': async value => { await script('set the clipboard to (item 1 of argv)', [value]); return { message: 'Copied to the clipboard.' }; },
  'sleep-display': async () => { await run('/usr/bin/pmset', ['displaysleepnow']); return { message: 'Display sleep requested.' }; },
  note: async value => { if (!value.trim()) throw new Error('Enter the note text.'); await script('tell application "Notes" to make new note at folder "Notes" with properties {name:"NEXUS", body:item 1 of argv}', [value.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!))]); return { message: 'Created a note.' }; },
  reminder: async value => { if (!value.trim()) throw new Error('Enter the reminder text.'); await script('tell application "Reminders" to make new reminder with properties {name:item 1 of argv}', [value]); return { message: 'Created a reminder.' }; },
};
export async function executeDesktop(request: DesktopRequest) { return handlers[request.verb](request.value ?? ''); }
