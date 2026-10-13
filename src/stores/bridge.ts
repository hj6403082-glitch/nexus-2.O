import { create } from 'zustand';

// Browser-side client for the local NEXUS Windows bridge (`bridge/windowsBridge.js`).
// The bridge runs on the user's own PC, on loopback, and requires a per-launch
// token. Nothing here reaches the network except the loopback origin the user
// pasted a token for. Connection state lives in this store; a hot `bridgeSignal`
// carries the current task load to the render loop without re-rendering React
// (Objective 5 thermal LUTs read it every frame).

export type BridgeStatus = 'disconnected' | 'connecting' | 'connected' | 'error';

export interface ScreenControl { type: string; name: string; auto: string; enabled: boolean; focus: boolean }
export interface ScreenContext { process: string; processId: number; title: string; controlCount: number; controls: ScreenControl[] }
export interface Diagnostics {
  cpuName: string; cores: number; logical: number; cpuLoad: number | null;
  gpuName: string; gpuDriver: string; gpuRamMB: number;
  totalMemMB: number; freeMemMB: number; uptimeSec: number;
  processes: { Name: string; Id: number; memMB: number; cpu: number }[];
}

const DEFAULT_URL = 'http://127.0.0.1:4517';
const STORE_KEY = 'nexus.bridge';

function persisted(): { url: string; token: string } {
  if (typeof localStorage === 'undefined') return { url: DEFAULT_URL, token: '' };
  try { const raw = localStorage.getItem(STORE_KEY); if (raw) { const v = JSON.parse(raw); return { url: v.url || DEFAULT_URL, token: v.token || '' }; } }
  catch { /* ignore unreadable storage */ }
  return { url: DEFAULT_URL, token: '' };
}
function persist(url: string, token: string) {
  try { localStorage.setItem(STORE_KEY, JSON.stringify({ url, token })); } catch { /* ignore */ }
}

interface BridgeState {
  status: BridgeStatus; url: string; token: string; error: string | null;
  verbs: string[]; screen: ScreenContext | null; diagnostics: Diagnostics | null; busy: boolean;
  setConfig: (url: string, token: string) => void;
  connect: () => Promise<void>;
  disconnect: () => void;
  readScreen: () => Promise<ScreenContext | null>;
  readDiagnostics: () => Promise<Diagnostics | null>;
}

// Hot signal read by the render loop. `load` ramps toward 1 while a bridge task
// is in flight and relaxes back to 0, driving the thermal colour grade.
export const bridgeSignal = { load: 0, target: 0 };

export const useBridge = create<BridgeState>((set, get) => {
  const initial = persisted();
  async function request<T>(path: string, body?: unknown): Promise<T> {
    const { url, token } = get();
    bridgeSignal.target = 1;
    set({ busy: true });
    try {
      const response = await fetch(url.replace(/\/$/, '') + path, {
        method: 'POST', headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify(body ?? {}), signal: AbortSignal.timeout(25000),
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.error || `Bridge request failed (${response.status}).`);
      return data as T;
    } finally { bridgeSignal.target = 0; set({ busy: false }); }
  }
  return {
    status: 'disconnected', url: initial.url, token: initial.token, error: null,
    verbs: [], screen: null, diagnostics: null, busy: false,
    setConfig: (url, token) => { set({ url: url || DEFAULT_URL, token }); persist(url || DEFAULT_URL, token); },
    connect: async () => {
      const { url, token } = get();
      if (!token) { set({ status: 'error', error: 'Paste the token printed by the bridge, then connect.' }); return; }
      set({ status: 'connecting', error: null });
      try {
        const health = await fetch(url.replace(/\/$/, '') + '/health', { signal: AbortSignal.timeout(6000) }).then(r => r.json());
        // A quick authenticated call confirms the token before we report success.
        await request('/diagnostics');
        set({ status: 'connected', verbs: Array.isArray(health.verbs) ? health.verbs : [], error: null });
        persist(url, token);
      } catch (err) {
        set({ status: 'error', error: err instanceof Error ? (/aborted|timeout|fetch/i.test(err.message) ? 'Cannot reach the bridge. Start it on this PC and check the URL.' : err.message) : 'Connection failed.' });
      }
    },
    disconnect: () => { bridgeSignal.target = 0; set({ status: 'disconnected', verbs: [], screen: null, diagnostics: null, error: null }); },
    readScreen: async () => {
      try { const result = await request<{ data: ScreenContext }>('/screen-context'); set({ screen: result.data, error: null }); return result.data; }
      catch (err) { set({ error: err instanceof Error ? err.message : 'Screen read failed.' }); return null; }
    },
    readDiagnostics: async () => {
      try { const result = await request<{ data: Diagnostics }>('/diagnostics'); set({ diagnostics: result.data, error: null }); return result.data; }
      catch (err) { set({ error: err instanceof Error ? err.message : 'Diagnostics failed.' }); return null; }
    },
  };
});
