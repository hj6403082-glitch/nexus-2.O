'use client';
import { useEffect } from 'react';
import { useNexus } from '@/stores/nexus';
import { ambientSignal } from '@/rendering/environment';
import { voiceSignal } from '@/stores/assistant';

// Audio-reactive ambiance (Phase 8, Objective 5). When ambient sound is on
// (the same opt-in control as the drone), NEXUS also samples the room through
// the microphone and publishes a smoothed 0..1 loudness into `ambientSignal`,
// which drives fog density, dust drift and the floor caustics. The microphone
// is opt-in and never recorded; only a running loudness average leaves the
// analyser. NEXUS's own speaking voice also raises the level so the room
// breathes while it talks, even without the mic.
export function useAmbient() {
  const audio = useNexus(s => s.audio);
  useEffect(() => {
    let raf = 0; let stream: MediaStream | null = null; let context: AudioContext | null = null; let cancelled = false;
    let analyser: AnalyserNode | null = null; let bins: Uint8Array | null = null;
    const decay = () => { // without a mic, follow the voice envelope and relax
      ambientSignal.level += (Math.max(voiceSignal.level * 0.7, 0) - ambientSignal.level) * 0.08;
      raf = requestAnimationFrame(decay);
    };
    if (!audio) { ambientSignal.level = 0; raf = requestAnimationFrame(decay); return () => cancelAnimationFrame(raf); }
    (async () => {
      try {
        if (!navigator.mediaDevices?.getUserMedia) throw new Error('no mic');
        stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
        if (cancelled) { stream.getTracks().forEach(t => t.stop()); return; }
        context = new AudioContext();
        const source = context.createMediaStreamSource(stream);
        analyser = context.createAnalyser(); analyser.fftSize = 256; analyser.smoothingTimeConstant = 0.85;
        source.connect(analyser);
        bins = new Uint8Array(analyser.frequencyBinCount);
        const loop = () => {
          if (cancelled || !analyser || !bins) return;
          analyser.getByteFrequencyData(bins as Uint8Array<ArrayBuffer>);
          let sum = 0; for (let i = 0; i < bins.length; i++) sum += bins[i];
          const level = Math.min(1, (sum / bins.length / 255) * 2.2);
          // Mic loudness, with NEXUS's own voice as a floor.
          const target = Math.max(level, voiceSignal.level * 0.7);
          ambientSignal.level += (target - ambientSignal.level) * 0.12;
          raf = requestAnimationFrame(loop);
        };
        raf = requestAnimationFrame(loop);
      } catch {
        // Mic denied or unavailable: fall back to the voice-driven envelope.
        raf = requestAnimationFrame(decay);
      }
    })();
    return () => { cancelled = true; cancelAnimationFrame(raf); stream?.getTracks().forEach(t => t.stop()); void context?.close(); ambientSignal.level = 0; };
  }, [audio]);
}
