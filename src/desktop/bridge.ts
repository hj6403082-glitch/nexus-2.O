import { execFile } from 'node:child_process';
import { promisify } from 'node:util';
import { readdir } from 'node:fs/promises';
import { homedir } from 'node:os';
import path from 'node:path';
import { mediaActions, verbs, type DesktopRequest, type DesktopVerb, type MediaAction } from './verbs';
import { describeDisplays, displayPhrase, linkDisplay, windowBounds, type CocoaFrame } from './displays';
export { verbs, type DesktopRequest, type DesktopVerb } from './verbs';
// execFile, never exec: no shell is spawned, so every argument is inert data.
const runFile = promisify(execFile);
const run = async (file: string, args: string[]) => (await runFile(file, args, { timeout: 15000, maxBuffer: 1024 * 1024 })).stdout.trim();
export function validateDesktop(value: unknown): DesktopRequest | null {
  if (!value || typeof value !== 'object') return null;
  const data = value as Record<string, unknown>;
  if (!verbs.includes(data.verb as DesktopVerb) || (data.value !== undefined && (typeof data.value !== 'string' || data.value.length > 10000))) return null;
  return { verb: data.verb as DesktopVerb, value: data.value as string | undefined };
}
export type InstalledApp = { name: string; path: string };
export async function installedApps() {
  const apps: InstalledApp[] = [];
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
export function resolveApp(apps: InstalledApp[], name: string) { return apps.find(app => app.name.toLocaleLowerCase() === name.trim().toLocaleLowerCase()); }
const script = (body: string, args: string[] = []) => run('/usr/bin/osascript', ['-e', `on run argv\n${body}\nend run`, ...args]);
const jxa = (body: string) => run('/usr/bin/osascript', ['-l', 'JavaScript', '-e', body]);
// The process macOS asks about is the terminal running the dev server, not the browser.
export function permissionMessage(error: unknown) {
  const message = error instanceof Error ? `${error.message} ${(error as { stderr?: string }).stderr ?? ''}` : '';
  if (message.includes('-1743') || /not authori[sz]ed to send apple events/i.test(message)) return 'macOS refused Automation. Allow the terminal running NEXUS in System Settings → Privacy & Security → Automation, then retry.';
  if (/assistive|accessibility|1002|-25211|not allowed to send keystrokes/i.test(message)) return 'macOS refused Accessibility. Allow the terminal running NEXUS in System Settings → Privacy & Security → Accessibility, then retry.';
  if (/could not create image|screen capture|screen recording/i.test(message)) return 'macOS refused Screen Recording. Allow the terminal running NEXUS in System Settings → Privacy & Security → Screen Recording, then quit and reopen the terminal.';
  if (/couldn.t find shortcut|shortcut .* not found|no shortcut/i.test(message)) return 'Do Not Disturb needs two Shortcuts named “NEXUS Focus On” and “NEXUS Focus Off” (each a single Set Focus action). Create them in the Shortcuts app, then retry.';
  if (/-600|isn.t running/i.test(message)) return 'That application is not running.';
  if (/-1728|can.t get/i.test(message)) return 'The application did not expose that item. Open it once and retry.';
  if (/ETIMEDOUT|timed out/i.test(message)) return 'macOS did not answer in time. A permission dialog may be waiting on screen; answer it and retry.';
  return 'macOS could not complete the action. Check the application and its permissions, then retry.';
}
// Failures that are already user-facing explanations rather than macOS errors.
export class DesktopError extends Error {}
const refuse = (message: string): never => { throw new DesktopError(message); };
export async function listDisplays() {
  const raw = JSON.parse(await jxa(`ObjC.import('AppKit'); const s = $.NSScreen.screens, out = []; for (let i = 0; i < s.count; i++) { const d = s.objectAtIndex(i), f = d.frame; out.push({ name: d.respondsToSelector('localizedName') ? d.localizedName.js : '', frame: { x: f.origin.x, y: f.origin.y, width: f.size.width, height: f.size.height } }); } JSON.stringify(out);`)) as { name: string; frame: CocoaFrame }[];
  return describeDisplays(raw);
}
const windowIds = async (browser: 'Google Chrome' | 'Safari') => (await script(`if application "${browser}" is running then\ntell application "${browser}" to return id of every window\nend if\nreturn ""`)).split(/,\s*/).filter(Boolean);
async function newWindow(browser: 'Google Chrome' | 'Safari', before: string[]) {
  for (let attempt = 0; attempt < 20; attempt++) {
    const id = (await windowIds(browser)).find(value => !before.includes(value));
    if (id) return id;
    await new Promise(resolve => setTimeout(resolve, 150));
  }
  return null;
}
async function openWebsite(value: string, apps: InstalledApp[]) {
  let url: URL;
  try { url = new URL(value); } catch { return refuse('Use an HTTP or HTTPS website address.'); }
  if (!['https:', 'http:'].includes(url.protocol) || url.username || url.password) refuse('Use an HTTP or HTTPS website address.');
  const displays = await listDisplays().catch(() => []), display = displays.length ? linkDisplay(displays) : null;
  const chrome = resolveApp(apps, 'Google Chrome'), browser = chrome ? 'Google Chrome' : 'Safari';
  // Diff window ids so the placement targets the window we created, never whichever is frontmost.
  const before = await windowIds(browser);
  // Chrome ignores AppleScript URL assignment on new windows; its CLI flag is reliable.
  if (chrome) await run('/usr/bin/open', ['-na', chrome.path, '--args', '--new-window', url.href]);
  else await script('tell application "Safari"\nactivate\nmake new document with properties {URL:item 1 of argv}\nend tell', [url.href]);
  const id = display ? await newWindow(browser, before) : null;
  if (display && id) {
    await script(`tell application "${browser}" to set bounds of (first window whose id is ((item 1 of argv) as integer)) to {(item 2 of argv) as integer, (item 3 of argv) as integer, (item 4 of argv) as integer, (item 5 of argv) as integer}`, [id, ...windowBounds(display).map(String)]);
    return { message: `Opened ${url.hostname} in a new ${browser === 'Safari' ? 'Safari' : 'Chrome'} window ${displayPhrase(display)}.` };
  }
  return { message: `Opened ${url.hostname} in a new window.` };
}
const players = ['Spotify', 'Music'] as const;
const mediaScript: Record<MediaAction, string> = { playpause: 'playpause', play: 'play', pause: 'pause', next: 'next track', previous: 'previous track' };
async function media(value: string, apps: InstalledApp[]) {
  const action = mediaActions.find(a => a === value) ?? refuse('Media actions are play, pause, playpause, next and previous.');
  // Player names are fixed constants, never caller text, so they may appear in script source.
  const installed = players.filter(name => resolveApp(apps, name));
  for (const player of installed) if ((await script(`return application "${player}" is running`)) === 'true') { await script(`tell application "${player}" to ${mediaScript[action]}`); return { message: `${player}: ${action === 'playpause' ? 'play/pause' : action}.` }; }
  const player = installed[0] ?? refuse('No supported player is installed. NEXUS controls Spotify and Music.');
  if (action === 'pause') return { message: 'Nothing is playing.' };
  await script(`tell application "${player}" to ${mediaScript[action === 'playpause' ? 'play' : action]}`); return { message: `${player}: ${action === 'playpause' ? 'play' : action}.` };
}
type Handler = (value: string, apps: () => Promise<InstalledApp[]>) => Promise<Record<string, unknown>>;
const app = async (apps: () => Promise<InstalledApp[]>, value: string) => resolveApp(await apps(), value) ?? refuse(`No such application: “${value.trim().slice(0, 80)}” is not installed.`);
const escapeHtml = (value: string) => value.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!));
// Every verb is a hand-written implementation. No path runs a caller-supplied command.
// Shutdown, restart and file deletion are deliberately absent: a misheard word must not destroy work.
const handlers: Record<DesktopVerb, Handler> = {
  apps: async (_, apps) => ({ apps: (await apps()).map(a => a.name).sort() }),
  displays: async () => { const displays = await listDisplays(); return { displays, message: displays.map(d => `${d.name}${d.main ? ' (main)' : ''}`).join(', ') }; },
  launch: async (value, apps) => { const found = await app(apps, value); await run('/usr/bin/open', ['-a', found.path]); return { message: `Opened ${found.name}.` }; },
  quit: async (value, apps) => { const found = await app(apps, value); await script('tell application (item 1 of argv) to quit', [found.name]); return { message: `Asked ${found.name} to quit. Unsaved-work prompts remain under your control.` }; },
  'hide-others': async () => { await script('tell application "System Events" to set visible of (every process whose visible is true and frontmost is false) to false'); return { message: 'Hid the other applications.' }; },
  website: async (value, apps) => openWebsite(value, await apps()),
  media: async (value, apps) => media(value, await apps()),
  volume: async value => { const level = Number(value); if (!/^\d{1,3}$/.test(value) || level > 100) refuse('Volume must be between 0 and 100.'); await script('set volume output volume ((item 1 of argv) as integer)', [String(level)]); return { message: `Volume set to ${level}%.` }; },
  screenshot: async () => { const file = path.join(homedir(), 'Desktop', `NEXUS ${new Date().toISOString().replace(/[:.]/g, '-')}.png`); await run('/usr/sbin/screencapture', ['-x', file]); return { message: `Saved a screenshot to your Desktop as ${path.basename(file)}.`, file }; },
  'clipboard-read': async () => ({ text: await run('/usr/bin/pbpaste', []) }),
  'clipboard-write': async value => { if (!value) refuse('Enter the text to copy.'); await script('set the clipboard to (item 1 of argv)', [value]); return { message: 'Copied to the clipboard.' }; },
  'lock-screen': async () => { await script('tell application "System Events" to keystroke "q" using {control down, command down}'); return { message: 'Screen locked.' }; },
  'sleep-display': async () => { await run('/usr/bin/pmset', ['displaysleepnow']); return { message: 'Display sleep requested.' }; },
  // macOS exposes no public Focus API; Shortcuts is the supported automation path.
  focus: async value => { const on = value === 'on' ? true : value === 'off' ? false : refuse('Do Not Disturb takes on or off.'); await run('/usr/bin/shortcuts', ['run', on ? 'NEXUS Focus On' : 'NEXUS Focus Off']); return { message: `Do Not Disturb ${on ? 'on' : 'off'}.` }; },
  note: async value => { if (!value.trim()) refuse('Enter the note text.'); await script('tell application "Notes" to make new note at folder "Notes" with properties {name:"NEXUS", body:item 1 of argv}', [escapeHtml(value)]); return { message: 'Created a note.' }; },
  reminder: async value => { if (!value.trim()) refuse('Enter the reminder text.'); await script('tell application "Reminders" to make new reminder with properties {name:item 1 of argv}', [value]); return { message: 'Created a reminder.' }; },
};
export async function executeDesktop(request: DesktopRequest, apps: () => Promise<InstalledApp[]> = installedApps) { return handlers[request.verb](request.value ?? '', apps); }
