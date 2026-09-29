import { create } from 'zustand';
export const useKnowledge = create<{ snapshots: Record<string, { text: string; at: string }>; publish: (id: string, data: unknown) => void }>((set) => ({
  snapshots: {}, publish: (id, data) => set(s => ({ snapshots: { ...s.snapshots, [id]: { text: JSON.stringify(data).slice(0, 3500), at: new Date().toISOString() } } })),
}));
