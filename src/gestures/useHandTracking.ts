'use client';
import { useCallback, useEffect, useRef } from 'react';
import type { HandLandmarker } from '@mediapipe/tasks-vision';
import { GestureEngine } from './engine';
import { BimanualZoom, BimanualGroup, BimanualSculpt } from './bimanual';
import { detectFlick } from '@/rendering/flick';
import { handSignal, useNexus } from '@/stores/nexus';
import { modules, wrapIndex, type ModuleId } from '@/lib/modules';
import { useAssistant } from '@/stores/assistant';
import { useForm } from '@/stores/form';
import { executeCommand } from '@/ai/commands';
import { OneEuro } from './oneEuro';

const DWELL_MS = 850;

export function useHandTracking() {
  const resources = useRef<{ stream?: MediaStream; video?: HTMLVideoElement; detector?: HandLandmarker; frame: number; generation: number }>({ frame: 0, generation: 0 });
  const engine = useRef(new GestureEngine());
  const bimanual = useRef(new BimanualZoom());
  const grouping = useRef(new BimanualGroup());
  const sculpting = useRef(new BimanualSculpt());
  const filterX = useRef(new OneEuro()), filterY = useRef(new OneEuro());
  const dwell = useRef<{ id: ModuleId | null; since: number }>({ id: null, since: 0 });
  const stop = useCallback(() => {
    const r = resources.current; r.generation++;
    cancelAnimationFrame(r.frame); r.stream?.getTracks().forEach(t => t.stop());
    r.detector?.close(); r.video?.pause(); if (r.video) r.video.srcObject = null;
    r.stream = undefined; r.detector = undefined; r.video = undefined;
    engine.current.reset(); bimanual.current.reset(); grouping.current.reset(); sculpting.current.reset(); filterX.current.reset(); filterY.current.reset(); Object.assign(handSignal, { visible: false, pinching: false, pointing: false, dwell: 0 });
    useNexus.setState({ tracking: 'off', gesture: 'None', confidence: 0, frozen: false, dragging: null });
  }, []);
  const start = useCallback(async () => {
    stop(); const r = resources.current; const generation = r.generation;
    useNexus.setState({ tracking: 'loading', trackingError: null });
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Camera tracking requires localhost or HTTPS and a browser with camera support.');
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user', frameRate: { ideal: 60 } }, audio: false });
      if (generation !== r.generation) { stream.getTracks().forEach(t => t.stop()); return; }
      r.stream = stream;
      const video = document.createElement('video'); video.muted = true; video.playsInline = true; video.srcObject = stream;
      r.video = video; await video.play();
      const { FilesetResolver, HandLandmarker } = await import('@mediapipe/tasks-vision');
      const vision = await FilesetResolver.forVisionTasks('/mediapipe');
      if (generation !== r.generation) return;
      // The GPU delegate runs the hand model several times faster; fall back to
      // the CPU where WebGL is unavailable.
      const options = (delegate: 'GPU' | 'CPU') => ({ baseOptions: { modelAssetPath: '/models/hand_landmarker.task', delegate },
        runningMode: 'VIDEO' as const, numHands: 2, minHandDetectionConfidence: .6, minHandPresenceConfidence: .6, minTrackingConfidence: .55 });
      const detector = await HandLandmarker.createFromOptions(vision, options('GPU')).catch(() => HandLandmarker.createFromOptions(vision, options('CPU')));
      if (generation !== r.generation) { detector.close(); return; }
      r.detector = detector; useNexus.setState({ tracking: 'searching' });
      useNexus.getState().log('Hand tracking · camera connected');
      let lastTime = -1, lastFrame = 0, lastSeen = 0, lastEvent = 0;
      const tick = (now: number) => {
        if (generation !== r.generation) return;
        // Every new camera frame is analysed (previously capped at ~15 per second).
        if (now - lastFrame > 12 && video.currentTime !== lastTime && video.readyState >= 2) {
          lastFrame = now; lastTime = video.currentTime;
          try {
            const result = detector.detectForVideo(video, now);
            if (useForm.getState().phase === 'NORMAL') {
              const grab = result.landmarks.length >= 2 ? grouping.current.update(result.landmarks) : null;
              if (grab) { useNexus.getState().setGrouped(grab === 'group'); useNexus.setState({ tracking: 'tracking', dragging: null, gesture: grab === 'group' ? 'Closed hand' : 'Open palm' }); engine.current.reset(); r.frame = requestAnimationFrame(tick); return; }
              // Two cupped hands sculpt: inward converges to a prism, outward
              // expands the workspace depth.
              const sculpt = result.landmarks.length >= 2 ? sculpting.current.update(result.landmarks) : null;
              if (sculpt) { if (sculpt === 'converge') useNexus.getState().converge(); else useNexus.getState().expand(); useNexus.setState({ tracking: 'tracking', dragging: null }); engine.current.reset(); r.frame = requestAnimationFrame(tick); return; }
            } else { grouping.current.reset(); sculpting.current.reset(); }
            const zoom = useForm.getState().phase === 'NORMAL' ? bimanual.current.update(result.landmarks, handSignal.zoom) : null;
            if (zoom !== null) { handSignal.zoom = zoom; useNexus.setState({ tracking: 'tracking', dragging: null }); engine.current.reset(); r.frame = requestAnimationFrame(tick); return; }
            const points = result.landmarks[0];
            const interpreted = points ? engine.current.update(points, now) : null;
            if (interpreted) {
              lastSeen = now;
              // One-euro smoothing: steady when the hand is still, no lag when it moves fast.
              const sx = filterX.current.filter(interpreted.x, now), sy = filterY.current.filter(interpreted.y, now);
              Object.assign(handSignal, { x: sx, y: sy, scale: interpreted.scale, visible: true, pinching: interpreted.pinching, pointing: interpreted.gesture === 'Point' });
              useNexus.setState({ tracking: 'tracking', confidence: result.handedness[0]?.[0]?.score ?? 0, frozen: interpreted.frozen,
                ...(now - lastEvent > 650 ? { gesture: interpreted.gesture } : {}) });
              const state = useNexus.getState();
              const hit = document.elementsFromPoint(sx * innerWidth, sy * innerHeight).map(e => e.closest<HTMLElement>('[data-module]')).find(Boolean)?.dataset.module as ModuleId | undefined;
              if (hit !== state.hovered) useNexus.setState({ hovered: hit ?? null });
              // Point and dwell: aiming at a card with one finger opens it after a
              // moment; the cursor ring fills to show the countdown.
              const aimed = interpreted.gesture === 'Point' && !state.expanded && useForm.getState().phase === 'NORMAL' ? hit ?? null : null;
              if (aimed !== dwell.current.id) dwell.current = { id: aimed, since: now };
              handSignal.dwell = aimed ? Math.min(1, (now - dwell.current.since) / DWELL_MS) : 0;
              if (aimed && handSignal.dwell >= 1) { state.open(aimed); handSignal.pulse = now; handSignal.label = 'Open'; dwell.current = { id: null, since: now }; }
              if (interpreted.event) {
                lastEvent = now; useNexus.setState({ gesture: interpreted.event }); handSignal.pulse = now; handSignal.label = interpreted.event;
                if (useForm.getState().phase !== 'NORMAL' && interpreted.event !== 'Circle' && interpreted.event !== 'Thumbs up') { r.frame = requestAnimationFrame(tick); return; }
                switch (interpreted.event) {
                  case 'Swipe left': state.rotate(1); break;
                  case 'Swipe right': state.rotate(-1); break;
                  case 'Pinch': { if (state.expanded) break; const id = hit ?? modules[wrapIndex(state.index)].id; state.select(id); useNexus.setState({ dragging: id }); break; }
                  case 'Release': { const held = state.dragging; const flick = detectFlick(interpreted.vx, interpreted.vy); if (held && flick && !state.grouped) state.fling(held); else useNexus.setState({ dragging: null }); break; }
                  case 'Pull': state.open(state.dragging ?? undefined); break;
                  case 'Push': state.close(); break;
                  case 'Circle': useAssistant.getState().wake(); state.log('Circle detected · Zeno awake'); break;
                  case 'Swipe up': if (!state.expanded) state.open(); break;
                  case 'Swipe down': state.close(); break;
                  case 'Peace': useNexus.setState({ drift: !state.drift }); state.log(`Peace sign · motion ${state.drift ? 'locked' : 'flowing'}`); break;
                  case 'Thumbs up': { const human = useForm.getState().target === 'human'; void executeCommand({ type: 'transform', form: human ? 'spatial' : 'human' }); state.log(`Thumbs up · ${human ? 'returning to spatial' : 'becoming human'}`); break; }
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
