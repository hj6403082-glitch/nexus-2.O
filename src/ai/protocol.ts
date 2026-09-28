import { modules, type ModuleId } from '@/lib/modules';
export type AIStatus = 'Idle' | 'Listening' | 'Thinking' | 'Streaming' | 'Speaking' | 'Interrupted' | 'Offline';
export type Command = { type: 'open'; module: ModuleId } | { type: 'rotate'; direction: 'left' | 'right' } | { type: 'close' } | { type: 'motion'; enabled: boolean } | { type: 'help' } | { type: 'transform'; form: 'human' | 'spatial' } | { type: 'youtube'; query: string };
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
  return null;
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
