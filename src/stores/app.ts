import { create } from 'zustand';
// App-window state: whether NEXUS runs as an installed app and whether the
// browser is offering to install it.
type InstallPrompt = Event & { prompt: () => Promise<void>; userChoice: Promise<{ outcome: 'accepted' | 'dismissed' }> };
interface AppState { standalone: boolean; installable: boolean; installed: boolean; deferred: InstallPrompt | null; install: () => Promise<void>; }
export const useApp = create<AppState>((set, get) => ({
  standalone: false, installable: false, installed: false, deferred: null,
  install: async () => {
    const prompt = get().deferred; if (!prompt) return;
    set({ deferred: null, installable: false });
    try { await prompt.prompt(); const choice = await prompt.userChoice; if (choice.outcome === 'accepted') set({ installed: true }); }
    catch { /* The browser withdrew the prompt; the install menu item still works. */ }
  },
}));
export function watchInstall() {
  const standalone = () => matchMedia('(display-mode: standalone)').matches || matchMedia('(display-mode: window-controls-overlay)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true;
  const update = () => { const on = standalone(); useApp.setState({ standalone: on }); document.documentElement.dataset.app = on ? 'standalone' : 'browser'; };
  const offer = (event: Event) => { event.preventDefault(); useApp.setState({ deferred: event as InstallPrompt, installable: true }); };
  const installed = () => useApp.setState({ installed: true, installable: false, deferred: null });
  const query = matchMedia('(display-mode: standalone)');
  update(); query.addEventListener('change', update);
  window.addEventListener('beforeinstallprompt', offer); window.addEventListener('appinstalled', installed);
  return () => { query.removeEventListener('change', update); window.removeEventListener('beforeinstallprompt', offer); window.removeEventListener('appinstalled', installed); };
}
