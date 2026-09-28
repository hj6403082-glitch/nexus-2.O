import { create } from 'zustand';
import { Matrix4 } from 'three';
import type { FormPhase } from '@/embodiment/timeline';
interface FormState { target: 'spatial' | 'human'; phase: FormPhase; ready: boolean; error: string | null; progress: string; request: (target: 'spatial' | 'human') => void; }
export const useForm = create<FormState>(set => ({ target: 'spatial', phase: 'NORMAL', ready: false, error: null, progress: '', request: target => set({ target, error: null }) }));
export const formSignal = { time: 0, dim: 0, dissolve: 0, presence: 0, headX: 0, headY: 0 };
export const cardMatrices = Array.from({ length: 10 }, () => new Matrix4());
