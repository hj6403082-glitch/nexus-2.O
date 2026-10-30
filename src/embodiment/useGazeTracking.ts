'use client';
import { useCallback, useEffect, useMemo, useRef } from 'react';
import type { FaceLandmarker } from '@mediapipe/tasks-vision';
import { gazeSignal, estimateGaze, gazeTarget } from './gaze';
import { useForm, type GazeStatus } from '@/stores/form';

const setStatus = (gaze: GazeStatus) => { if (useForm.getState().gaze !== gaze) useForm.setState({ gaze }); };

// Drives the webcam gaze signal with MediaPipe FaceLandmarker so the humanoid
// keeps eye contact (Phase 8, Objective 3). Opt-in: nothing starts until
// `start()` is called (the Human-mode UI offers it), and the camera stops on
// return to spatial mode, tab hide, or `stop()`. Frames are processed locally
// with the bundled MediaPipe runtime; nothing is uploaded or recorded. The
// lifecycle is published as `useForm().gaze` so the UI never shows a stale state.
export function useGazeTracking() {
  const res = useRef<{ stream?: MediaStream; video?: HTMLVideoElement; detector?: FaceLandmarker; frame: number; gen: number }>({ frame: 0, gen: 0 });
  const stop = useCallback(() => {
    const r = res.current; r.gen++;
    cancelAnimationFrame(r.frame); r.stream?.getTracks().forEach(t => t.stop());
    r.detector?.close(); if (r.video) { r.video.pause(); r.video.srcObject = null; }
    r.stream = undefined; r.detector = undefined; r.video = undefined;
    gazeSignal.active = false; gazeSignal.confidence = 0;
    setStatus('off');
  }, []);
  const start = useCallback(async () => {
    stop(); const r = res.current; const gen = r.gen;
    setStatus('starting');
    try {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error('Webcam gaze needs a camera and a secure (localhost/HTTPS) context.');
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480, facingMode: 'user' }, audio: false });
      if (gen !== r.gen) { stream.getTracks().forEach(t => t.stop()); return; }
      r.stream = stream;
      const video = document.createElement('video'); video.muted = true; video.playsInline = true; video.srcObject = stream;
      r.video = video; await video.play();
      const { FilesetResolver, FaceLandmarker } = await import('@mediapipe/tasks-vision');
      const vision = await FilesetResolver.forVisionTasks('/mediapipe');
      if (gen !== r.gen) return;
      const detector = await FaceLandmarker.createFromOptions(vision, {
        baseOptions: { modelAssetPath: '/models/face_landmarker.task', delegate: 'CPU' },
        runningMode: 'VIDEO', numFaces: 1, minFaceDetectionConfidence: .5, minTrackingConfidence: .5,
      });
      if (gen !== r.gen) { detector.close(); return; }
      r.detector = detector; setStatus('searching');
      let lastTime = -1, lastFrame = 0;
      const tick = (now: number) => {
        if (gen !== r.gen) return;
        if (now - lastFrame > 55 && video.currentTime !== lastTime && video.readyState >= 2) {
          lastFrame = now; lastTime = video.currentTime;
          try {
            const result = detector.detectForVideo(video, now);
            const face = result.faceLandmarks?.[0];
            const g = face ? estimateGaze(face) : null;
            if (g) {
              const t = gazeTarget(g);
              gazeSignal.yaw += (t.yaw - gazeSignal.yaw) * .3;
              gazeSignal.pitch += (t.pitch - gazeSignal.pitch) * .3;
              gazeSignal.active = true; gazeSignal.confidence = 1;
            } else { gazeSignal.active = false; gazeSignal.confidence = 0; }
            setStatus(gazeSignal.active ? 'tracking' : 'searching');
          } catch { /* skip a bad frame */ }
        }
        r.frame = requestAnimationFrame(tick);
      };
      r.frame = requestAnimationFrame(tick);
    } catch (error) {
      if (gen !== r.gen) return; stop();
      useForm.setState({ error: error instanceof Error ? error.message : 'Gaze tracking could not start.' });
    }
  }, [stop]);
  useEffect(() => {
    const onVisibility = () => { if (document.hidden) stop(); };
    document.addEventListener('visibilitychange', onVisibility);
    return () => { document.removeEventListener('visibilitychange', onVisibility); stop(); };
  }, [stop]);
  return useMemo(() => ({ start, stop }), [start, stop]);
}
