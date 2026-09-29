import type { Command } from './protocol';
import { useNexus } from '@/stores/nexus';
import { useAssistant } from '@/stores/assistant';
import { moduleById } from '@/lib/modules';
import { useForm } from '@/stores/form';
export function executeCommand(command: Command): string {
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
  }
}
