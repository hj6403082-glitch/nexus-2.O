'use client';
import { useCallback, useEffect, useRef } from 'react';
import { useNexus } from '@/stores/nexus';
export function useAudio() {
  const graph = useRef<{ context: AudioContext; gain: GainNode; voices: OscillatorNode[] } | null>(null);
  const toggle = useCallback(async () => {
    if (graph.current) { await graph.current.context.close(); graph.current = null; useNexus.setState({ audio: false }); return; }
    try {
      const context = new AudioContext(); await context.resume();
      const gain = context.createGain(); gain.gain.setValueAtTime(0, context.currentTime); gain.gain.linearRampToValueAtTime(.015, context.currentTime + 2); gain.connect(context.destination);
      const voices = [110, 164.81, 220.15].map(frequency => { const voice = context.createOscillator(); voice.type = 'sine'; voice.frequency.value = frequency; voice.connect(gain); voice.start(); return voice; });
      graph.current = { context, gain, voices }; useNexus.setState({ audio: true });
    } catch { useNexus.getState().log('Audio unavailable · continue without sound'); }
  }, []);
  useEffect(() => {
    const unsubscribe = useNexus.subscribe((s, previous) => {
      if (!graph.current || (s.index === previous.index && s.expanded === previous.expanded && s.gesture === previous.gesture)) return;
      if (s.gesture !== previous.gesture && !['Pinch', 'Release', 'Pull', 'Push', 'Swipe left', 'Swipe right'].includes(s.gesture)) return;
      const { context } = graph.current;
      const tone = context.createOscillator(), envelope = context.createGain();
      tone.frequency.setValueAtTime(s.expanded ? 660 : 440, context.currentTime);
      tone.frequency.exponentialRampToValueAtTime(330, context.currentTime + .16);
      envelope.gain.setValueAtTime(.025, context.currentTime); envelope.gain.exponentialRampToValueAtTime(.0001, context.currentTime + .22);
      tone.connect(envelope); envelope.connect(context.destination); tone.start(); tone.stop(context.currentTime + .25);
      tone.onended = () => { tone.disconnect(); envelope.disconnect(); };
    });
    const visibility = () => { if (!graph.current) return; if (document.hidden) void graph.current.context.suspend(); else void graph.current.context.resume(); };
    document.addEventListener('visibilitychange', visibility);
    return () => { unsubscribe(); document.removeEventListener('visibilitychange', visibility); void graph.current?.context.close(); graph.current = null; };
  }, []);
  return toggle;
}
