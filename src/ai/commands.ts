import type { Command } from './protocol';
import { useNexus } from '@/stores/nexus';
import { useAssistant } from '@/stores/assistant';
import { moduleById } from '@/lib/modules';
import { useForm } from '@/stores/form';
import { bridgeUnavailable, desktopAction } from '@/desktop/client';
import { resolveDestination, type Destination } from '@/knowledge/destinations';
import { liveInstagramFeed } from '@/knowledge/instagramFeed';
import type { DesktopRequest } from '@/desktop/verbs';
// Websites go to a dedicated window through the bridge; without one, NEXUS hands over a link.
export async function openWebsite(url: string, label: string) {
  const result = await desktopAction({ verb: 'website', value: url });
  if (result.ok) return result.message;
  if (bridgeUnavailable(result)) { useAssistant.setState({ link: { label: `Open ${label}`, url } }); return `${label} is ready. The desktop bridge is off here, so use the link to open it.`; }
  return result.message;
}
export async function runDesktop(request: DesktopRequest) {
  if (request.verb === 'website' && request.value) return openWebsite(request.value, new URL(request.value).hostname);
  const result = await desktopAction(request);
  useNexus.getState().log(`DESKTOP · ${request.verb} · ${result.ok ? 'done' : 'refused'}`);
  return result.message;
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
      if (command.module === 'ai') { useAssistant.getState().wake(); return "I'm here. What would you like to explore?"; }
      scene.open(command.module); useAssistant.setState({ visible: false });
      return command.module === 'system' ? 'Here are your live rendering diagnostics.' : `Opening ${moduleById(command.module).name}.`;
    case 'rotate': if (useForm.getState().phase !== 'NORMAL') return 'There is no orbit in human mode. Return to spatial mode to rotate the modules.'; scene.rotate(command.direction === 'left' ? -1 : 1); return `Rotating ${command.direction}.`;
    case 'close': scene.close(); return 'Back in spatial view.';
    case 'motion': useNexus.setState({ drift: command.enabled }); return command.enabled ? 'Ambient movement enabled.' : 'Ambient movement locked.';
    case 'help': useNexus.setState({ help: true }); useAssistant.setState({ visible: false }); return 'Here are the gesture and keyboard controls.';
    case 'transform':
      if (useNexus.getState().renderer === 'fallback' && command.form === 'human') return 'Human form needs WebGL 2. Your browser is using the accessible spatial fallback.';
      scene.close(); useForm.getState().request(command.form); useAssistant.setState({ visible: false });
      return command.form === 'human' ? 'Understood. Give me a moment.' : 'Returning to spatial mode.';
    case 'youtube': useAssistant.setState({ link: { label: `Search YouTube for “${command.query}”`, url: `https://www.youtube.com/results?search_query=${encodeURIComponent(command.query)}` } }); return `Your YouTube search for “${command.query}” is ready. Use the link to open it.`;
    case 'desktop': return runDesktop(command.request);
    case 'destination': return openDestination(command.destination);
  }
}
