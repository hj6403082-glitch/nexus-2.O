'use client';
import { useCallback, useEffect, useRef } from 'react';
import type { HandLandmarker } from '@mediapipe/tasks-vision';
import { GestureEngine } from './engine';
import { handSignal, useNexus } from '@/stores/nexus';
import { modules, wrapIndex, type ModuleId } from '@/lib/modules';
import { useAssistant } from '@/stores/assistant';
import { useForm } from '@/stores/form';

export function useHandTracking() {
  const resources = useRef<{ stream?: MediaStream; video?: HTMLVideoElement; detector?: HandLandmarker; frame: number; generation: number }>({ frame: 0, generation: 0 });
  const engine = useRef(new GestureEngine());
  const stop = useCallback(() => {
    const r = resources.current; r.generation++;
    cancelAnimationFrame(r.frame); r.stream?.getTracks().forEach(t => t.stop());
    r.detector?.close(); r.video?.pause(); if (r.video) r.video.srcObject = null;
    r.stream = undefined; r.detector = undefined; r.video = undefined;
    engine.current.reset(); handSignal.visible = false; handSignal.pinching = false;
    useNexus.setState({ tracking: 'off', gesture: 'None', confidence: 0, frozen: false, dragging: null });
  }, []);
  const start = useCallback(async () => {
    stop(); const r = resources.current; const generation = r.generation;
    useNexus.setState({ tracking: 'loading', trackingError: null });
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera tracking requires localhost or HTTPS and a browser with camera support.');
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false });
      if (generation !== r.generation) { stream.getTracks().forEach(t => t.stop()); return; }
      r.stream = stream;
      const video = document.createElement('video'); video.muted = true; video.playsInline = true; video.srcObject = stream;
      r.video = video; await video.play();
      const { FilesetResolver, HandLandmarker } = await import('@mediapipe/tasks-vision');
      const vision = await FilesetResolver.forVisionTasks('/mediapipe');
      if (generation !== r.generation) return;
      const detector = await HandLandmarker.createFromOptions(vision, {
        baseOptions: { modelAssetPath: '/models/hand_landmarker.task', delegate: 'CPU' },
        runningMode: 'VIDEO', numHands: 1, minHandDetectionConfidence: .65, minHandPresenceConfidence: .65, minTrackingConfidence: .6,
      });
      if (generation !== r.generation) { detector.close(); return; }
      r.detector = detector; useNexus.setState({ tracking: 'searching' });
      useNexus.getState().log('Hand tracking · camera connected');
      let lastTime = -1, lastFrame = 0, lastSeen = 0, lastEvent = 0;
      const tick = (now: number) => {
        if (generation !== r.generation) return;
        if (now - lastFrame > 65 && video.currentTime !== lastTime && video.readyState >= 2) {
          lastFrame = now; lastTime = video.currentTime;
          try {
            const result = detector.detectForVideo(video, now);
            const points = result.landmarks[0];
            const interpreted = points ? engine.current.update(points, now) : null;
            if (interpreted) {
              lastSeen = now;
              Object.assign(handSignal, { x: interpreted.x, y: interpreted.y, scale: interpreted.scale, visible: true, pinching: interpreted.pinching });
              useNexus.setState({ tracking: 'tracking', confidence: result.handedness[0]?.[0]?.score ?? 0, frozen: interpreted.frozen,
                ...(now - lastEvent > 650 ? { gesture: interpreted.gesture } : {}) });
              const state = useNexus.getState();
              const hit = document.elementsFromPoint(interpreted.x * innerWidth, interpreted.y * innerHeight).map(e => e.closest<HTMLElement>('[data-module]')).find(Boolean)?.dataset.module as ModuleId | undefined;
              if (hit !== state.hovered) useNexus.setState({ hovered: hit ?? null });
              if (interpreted.event) {
                lastEvent = now; useNexus.setState({ gesture: interpreted.event });
                if (useForm.getState().phase !== 'NORMAL' && interpreted.event !== 'Circle') { r.frame = requestAnimationFrame(tick); return; }
                switch (interpreted.event) {
                  case 'Swipe left': state.rotate(1); break;
                  case 'Swipe right': state.rotate(-1); break;
                  case 'Pinch': { if (state.expanded) break; const id = hit ?? modules[wrapIndex(state.index)].id; state.select(id); useNexus.setState({ dragging: id }); break; }
                  case 'Release': useNexus.setState({ dragging: null }); break;
                  case 'Pull': state.open(state.dragging ?? undefined); break;
                  case 'Push': state.close(); break;
                  case 'Circle': useAssistant.getState().wake(); state.log('Circle detected · NEXUS awake'); break;
                }
              }
            } else if (now - lastSeen > 250) {
              handSignal.visible = false; handSignal.pinching = false; engine.current.reset();
              useNexus.setState({ tracking: 'searching', confidence: 0, gesture: 'None', frozen: false, dragging: null, hovered: null });
            }
          } catch { stop(); useNexus.setState({ tracking: 'error', trackingError: 'Tracking stopped. Try enabling the camera again, or use the keyboard controls.' }); return; }
        }
        r.frame = requestAnimationFrame(tick);
      };
      r.frame = requestAnimationFrame(tick);
    } catch (error) {
      if (generation !== r.generation) return;
      stop();
      const name = error instanceof Error ? error.name : '';
      const message = name === 'NotAllowedError' ? 'Camera access was denied. Allow the camera in your browser’s site settings, then try again.' : name === 'NotFoundError' ? 'No camera was found. Connect a webcam, or use the keyboard and pointer controls.' : name === 'NotReadableError' ? 'The camera is in use by another app. Close it there and try again.' : error instanceof Error ? error.message : 'Could not start tracking. Try again.';
      useNexus.setState({ tracking: 'error', trackingError: message }); useNexus.getState().log('Camera unavailable · fallback controls ready');
    }
  }, [stop]);
  useEffect(() => {
    const onVisibility = () => { if (document.hidden && resources.current.stream) { stop(); useNexus.getState().log('Tracking stopped · tab hidden'); } };
    document.addEventListener('visibilitychange', onVisibility);
    return () => { document.removeEventListener('visibilitychange', onVisibility); stop(); };
  }, [stop]);
  return { start, stop };
}
