import type { Command } from './protocol';
import { useNexus } from '@/stores/nexus';
import { useAssistant } from '@/stores/assistant';
import { moduleById } from '@/lib/modules';
import { useForm } from '@/stores/form';
import { resolveDestination, type Destination } from '@/knowledge/destinations';
import { liveInstagramFeed } from '@/knowledge/instagramFeed';
// Websites open in a new tab when the browser allows it (a click in ⌘K);
// otherwise, as after a voice request, Zeno hands over a link.
export function openWebsite(url: string, label: string) {
  const tab = typeof window !== 'undefined' ? window.open(url, '_blank') : null;
  if (tab) { tab.opener = null; return `Opened ${label} in a new tab.`; }
  useAssistant.setState({ link: { label: `Open ${label}`, url } });
  return `${label} is ready. Use the link to open it.`;
}
export async function openDestination(destination: Destination) {
  const feed = await liveInstagramFeed();
  if ('error' in feed) return `I can't resolve that from your feed. ${feed.error}`;
  const resolved = resolveDestination(destination, feed);
  return 'error' in resolved ? resolved.error : openWebsite(resolved.url, resolved.label);
}
export function executeCommand(command: Command): string | Promise<string> {
  const scene = useNexus.getState();
  switch (command.type) {
    case 'open':
      if (command.module === 'ai') { useAssistant.getState().wake(); return "Hey, I'm right here. What's on your mind?"; }
      scene.open(command.module); useAssistant.setState({ visible: false });
      return command.module === 'system' ? "Here's how everything's running right now." : `Opening ${moduleById(command.module).name} for you.`;
    case 'rotate': if (useForm.getState().phase !== 'NORMAL') return "There's no orbit while I'm in human form. Switch me back to spatial and I'll spin it for you."; scene.rotate(command.direction === 'left' ? -1 : 1); return command.direction === 'left' ? 'Sure, spinning left.' : 'Sure, spinning right.';
    case 'close': scene.close(); return "Okay, we're back in the orbit.";
    case 'motion': useNexus.setState({ drift: command.enabled }); return command.enabled ? "Nice, letting everything drift." : "Got it, holding everything still.";
    case 'help': useNexus.setState({ help: true }); useAssistant.setState({ visible: false }); return "Here's everything you can do with your hands and keyboard.";
    case 'transform':
      if (useNexus.getState().renderer === 'fallback' && command.form === 'human') return 'Human form needs WebGL 2. Your browser is using the accessible spatial fallback.';
      scene.close(); useForm.getState().request(command.form); useAssistant.setState({ visible: false });
      return command.form === 'human' ? "Alright, give me a second to pull myself together." : "Okay, heading back to the orbit.";
    case 'youtube': useAssistant.setState({ link: { label: `Search YouTube for “${command.query}”`, url: `https://www.youtube.com/results?search_query=${encodeURIComponent(command.query)}` } }); return `Your YouTube search for “${command.query}” is ready. Use the link to open it.`;
    case 'website': return openWebsite(command.url, command.label);
    case 'destination': return openDestination(command.destination);
  }
}
