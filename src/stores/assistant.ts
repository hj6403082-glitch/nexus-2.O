import { create } from 'zustand';
import type { AIStatus, Turn } from '@/ai/protocol';
interface AssistantState {
  visible: boolean; status: AIStatus; configured: boolean | null; model: string; provider: string; setup: string;
  // Local brain readiness: offline | no-model | model-missing | ready, and the model the user asked for.
  brain: string; wanted: string; pull: { model: string; status: string; percent: number | null } | null;
  messages: Turn[]; draft: string; error: string | null; microphone: boolean; voice: boolean;
  voiceURI: string; voiceStyle: 'ultron' | 'natural'; neural: { state: string; progress: number; message: string } | null; wakeAt: number; transcript: string; link: { label: string; url: string } | null;
  wake: () => void;
}
export const useAssistant = create<AssistantState>((set) => ({
  visible: false, status: 'Idle', configured: null, model: '', provider: 'ollama', setup: '', brain: '', wanted: '', pull: null, messages: [], draft: '', error: null,
  microphone: false, voice: false, voiceURI: '', voiceStyle: 'ultron', neural: null, wakeAt: 0, transcript: '', link: null,
  wake: () => set({ visible: true, wakeAt: Date.now() }),
}));
// Future embodied rendering reads this envelope without rerendering React.
export const voiceSignal = { level: 0 };
