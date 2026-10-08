import { modules, type ModuleId } from '@/lib/modules';
import type { DesktopRequest } from '@/desktop/verbs';
import { siteByName, websiteUrl } from '@/desktop/sites';
import { matchDestination, type Destination } from '@/knowledge/destinations';
export type AIStatus = 'Idle' | 'Listening' | 'Thinking' | 'Streaming' | 'Speaking' | 'Interrupted' | 'Offline';
export type Command = { type: 'open'; module: ModuleId } | { type: 'rotate'; direction: 'left' | 'right' } | { type: 'close' } | { type: 'motion'; enabled: boolean } | { type: 'help' } | { type: 'transform'; form: 'human' | 'spatial' } | { type: 'youtube'; query: string }
  // Local-only: produced by the phrase matcher, never accepted from the model stream.
  | { type: 'desktop'; request: DesktopRequest } | { type: 'destination'; destination: Destination };
export type Turn = { id: string; role: 'user' | 'assistant'; text: string; interrupted?: boolean; failed?: boolean; createdAt: number };
export type StreamEvent = { type: 'text'; text: string } | { type: 'command'; command: Command } | { type: 'error'; message: string } | { type: 'done' };
export const isModule = (value: unknown): value is ModuleId => typeof value === 'string' && modules.some(m => m.id === value);
export function validateCommand(value: unknown): Command | null {
  if (!value || typeof value !== 'object') return null;
  const c = value as Record<string, unknown>;
  if (c.type === 'open' && isModule(c.module)) return { type: 'open', module: c.module };
  if (c.type === 'rotate' && (c.direction === 'left' || c.direction === 'right')) return { type: 'rotate', direction: c.direction };
  if (c.type === 'close' || c.type === 'help') return { type: c.type };
  if (c.type === 'motion' && typeof c.enabled === 'boolean') return { type: 'motion', enabled: c.enabled };
  if (c.type === 'transform' && (c.form === 'human' || c.form === 'spatial')) return { type: 'transform', form: c.form };
  if (c.type === 'youtube' && typeof c.query === 'string' && c.query.length > 0 && c.query.length <= 200) return { type: 'youtube', query: c.query };
  return null;
}
export function matchCommand(text: string): Command | null {
  const t = text.toLowerCase().trim().replace(/^(?:hey\s+)?nexus[\s,:.!]*/, '').replace(/[.!?]+$/, '').trim();
  const open = t.match(/^(?:open|show|show me|go to|focus)(?: the| my)? (instagram|stocks|projects|sports|calendar|weather|ai|news|music|system)(?: module)?$/);
  if (open && isModule(open[1])) return { type: 'open', module: open[1] };
  const rotate = t.match(/^(?:rotate|turn|move|swipe)(?: the orbit)? (left|right)$/);
  if (rotate) return { type: 'rotate', direction: rotate[1] as 'left' | 'right' };
  if (/^(close(?: (?:the )?(?:module|panel))?|back|return to (?:the )?orbit)$/.test(t)) return { type: 'close' };
  if (/^(?:freeze|lock|hold still|stop (?:the )?(?:ambient )?motion)$/.test(t)) return { type: 'motion', enabled: false };
  if (/^(?:enable drift|unlock|start (?:the )?(?:ambient )?motion)$/.test(t)) return { type: 'motion', enabled: true };
  if (/^(?:help|show (?:the )?controls|how do i use this)$/.test(t)) return { type: 'help' };
  if (/^(?:transform into a human(?: shape)?|become human)$/.test(t)) return { type: 'transform', form: 'human' };
  if (/^return to spatial mode$/.test(t)) return { type: 'transform', form: 'spatial' };
  const youtube = t.match(/^search youtube(?: for)? (.{1,200})$/);
  if (youtube) return { type: 'youtube', query: youtube[1] };
  return matchDesktop(text.trim().replace(/^(?:hey\s+)?nexus[\s,:.!]*/i, '').replace(/[.!?]+$/, '').trim());
}
const desktop = (verb: DesktopRequest['verb'], value?: string): Command => ({ type: 'desktop', request: value === undefined ? { verb } : { verb, value } });
// Desktop phrasing. The app name stays exactly as heard: it is resolved against
// the live installed-app scan on the server, so "safari; rm -rf ~" is simply
// an application that does not exist.
export function matchDesktop(text: string): Command | null {
  const t = text.slice(0, 2100), raw = t.toLowerCase().slice(0, 500);
  if (/^(?:list|show)(?: me)?(?: all)? (?:my |the )?(?:installed )?apps$/.test(raw)) return desktop('apps');
  if (/^(?:list|show|which)(?: me)?(?: my| the)? (?:displays|screens|monitors)$/.test(raw)) return desktop('displays');
  if (/^hide (?:all )?(?:the )?others?(?: apps| applications| windows)?$/.test(raw)) return desktop('hide-others');
  if (/^lock(?: the| my)? (?:screen|mac|computer)$/.test(raw)) return desktop('lock-screen');
  if (/^(?:sleep|turn off)(?: the| my)? (?:display|screen|monitor)s?$/.test(raw)) return desktop('sleep-display');
  if (/^(?:take a |take |capture (?:a |the )?)?(?:screenshot|screen capture|capture(?: the)? screen)$/.test(raw)) return desktop('screenshot');
  if (/^(?:read|paste|what(?:'s| is) (?:on|in)) (?:my |the )?clipboard$/.test(raw)) return desktop('clipboard-read');
  const media = raw.match(/^(play|pause|resume|next|skip|previous)(?: the)?(?: music| song| track| playback)?$/);
  if (media) return desktop('media', { play: 'play', resume: 'play', pause: 'pause', next: 'next', skip: 'next', previous: 'previous' }[media[1]]);
  if (/^(?:play|pause|toggle) ?\/ ?(?:play|pause)$|^play or pause$/.test(raw)) return desktop('media', 'playpause');
  const volume = raw.match(/^(?:set (?:the )?)?volume(?: to)? (\d{1,3})(?: ?%| percent)?$/);
  if (volume) return desktop('volume', volume[1]);
  if (/^(?:mute|mute (?:the )?(?:sound|audio|volume))$/.test(raw)) return desktop('volume', '0');
  const focus = raw.match(/^(?:turn |switch )?(on|off) do not disturb$|^(?:turn |switch )?do not disturb (on|off)$|^(enable|disable) do not disturb$/);
  if (focus) return desktop('focus', (focus[1] ?? focus[2] ?? (focus[3] === 'enable' ? 'on' : 'off')));
  const copy = t.match(/^copy (.{1,2000}?)(?: to (?:my |the )?clipboard)?$/i);
  if (copy) return desktop('clipboard-write', copy[1]);
  const note = t.match(/^(?:create|make|add|take) (?:a )?note(?: saying| that says|:)? (.{1,2000})$|^note (.{1,2000})$/i);
  if (note) return desktop('note', note[1] ?? note[2]);
  const reminder = t.match(/^remind me (?:to )?(.{1,500})$|^(?:create|add|set) (?:a )?reminder(?: to|:)? (.{1,500})$/i);
  if (reminder) return desktop('reminder', reminder[1] ?? reminder[2]);
  const quit = raw.match(/^(?:quit|close) (?:the )?(.{1,120}?)(?: app| application)?$/);
  if (quit) return isModule(quit[1]) || /^(?:module|panel|orbit)$/.test(quit[1]) ? { type: 'close' } : desktop('quit', quit[1]);
  const open = raw.match(/^(open|launch|start|go to|show|show me|visit|take me to) (?:the )?(.{1,500}?)(?: app| application| website| site)?$/);
  if (!open) return null;
  const [, verb, target] = open, destination = matchDestination(target);
  if (destination) return { type: 'destination', destination };
  const site = siteByName(target), url = site?.url ?? websiteUrl(target);
  if (url) return desktop('website', url);
  // Anything else said as "open X" is an app name. Keep it to short names so
  // questions ("show me how...") still reach the model.
  if (!['open', 'launch', 'start'].includes(verb) || target.split(/\s+/).length > 5 || /^(?:how|what|why|when|where|who|me)\b/.test(target)) return null;
  return desktop('launch', target);
}
// Buffers arbitrary network chunk boundaries, including split UTF-8 codepoints.
export class EventDecoder {
  private decoder = new TextDecoder();
  private buffer = '';
  push(chunk?: Uint8Array): StreamEvent[] {
    this.buffer += this.decoder.decode(chunk, { stream: !!chunk });
    const lines = this.buffer.split('\n'); this.buffer = lines.pop() ?? '';
    if (!chunk && this.buffer.trim()) { lines.push(this.buffer); this.buffer = ''; }
    return lines.filter(l => l.trim()).map(line => {
      const v = JSON.parse(line);
      if (v.type === 'text' && typeof v.text === 'string') return { type: 'text', text: v.text };
      if (v.type === 'done') return { type: 'done' };
      if (v.type === 'error' && typeof v.message === 'string') return { type: 'error', message: v.message };
      const command = v.type === 'command' ? validateCommand(v.command) : null;
      if (command) return { type: 'command', command };
      throw new Error('Unrecognized AI stream event.');
    });
  }
}
