import { smooth } from '@/embodiment/timeline';
export const presentation = { time: 0, active: false, module: '' };
export function presentationEnvelopes(time: number) {
  return { target: smooth(0, .35, time) * (1 - smooth(1.7, 2.4, time)), approach: smooth(.35, 1.4, time), push: smooth(.35, 1.4, time) * (1 - smooth(1.6, 2.4, time)), scan: smooth(.7, 1.5, time) };
}
