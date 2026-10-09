'use client';
import { useEffect } from 'react';
import { useNexus } from '@/stores/nexus';
import { useAssistant } from '@/stores/assistant';
export function useControls() {
  useEffect(() => {
    const key = (e: KeyboardEvent) => {
      const state = useNexus.getState();
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); useNexus.setState({ launcher: !state.launcher }); return; }
      if (e.key === 'Escape') { state.close(); useAssistant.setState({ visible: false }); window.dispatchEvent(new Event('nexus:stop-ai')); return; }
      if ((e.target as HTMLElement)?.closest('input,textarea,select,[contenteditable="true"]') || state.launcher || state.help) return;
      if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); state.rotate(e.key === 'ArrowRight' ? 1 : -1); }
      if (e.key === 'Enter' && !(e.target as HTMLElement)?.closest('button,a')) { e.preventDefault(); state.open(); }
      if (e.key.toLowerCase() === 'h') useNexus.setState({ hud: !state.hud });
      if (e.key === '?') useNexus.setState({ help: !state.help });
      if (e.key.toLowerCase() === 'g' && !state.expanded) state.setGrouped(!state.grouped);
    };
    window.addEventListener('keydown', key); return () => window.removeEventListener('keydown', key);
  }, []);
}
