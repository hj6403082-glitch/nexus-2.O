// Real-time webcam gaze signal (Phase 8, Objective 3). A hot object the
// embodiment shader reads every frame: the user's head yaw/pitch (−1..1),
// whether a face is currently tracked, and a confidence. MediaPipe FaceMesh
// fills it; the humanoid's neck IK and optical flares follow it to hold eye
// contact. When no face is tracked the humanoid falls back to pointer-follow.
export const gazeSignal = { yaw: 0, pitch: 0, active: false, confidence: 0 };

// Convert a normalised face-landmark set into a head yaw/pitch estimate.
// Landmarks are MediaPipe FaceMesh indices in normalised image space (x,y,z,
// origin top-left). We use the nose bridge/tip against the eye-corner midline
// and the face vertical extent — robust enough to drive the neck without a full
// PnP solve. Mirrored x (selfie view) is handled by the caller.
export interface FacePoint { x: number; y: number; z?: number }
export function estimateGaze(landmarks: FacePoint[]): { yaw: number; pitch: number } | null {
  if (!landmarks || landmarks.length < 468) return null;
  const noseTip = landmarks[1], noseBridge = landmarks[168] ?? landmarks[6];
  const leftEye = landmarks[33], rightEye = landmarks[263];       // outer eye corners
  const top = landmarks[10], bottom = landmarks[152];             // forehead / chin
  if (!noseTip || !leftEye || !rightEye || !top || !bottom) return null;
  const eyeMidX = (leftEye.x + rightEye.x) / 2;
  const eyeSpan = Math.abs(rightEye.x - leftEye.x) || 1e-3;
  // Yaw: how far the nose sits from the eye midline, in eye-span units.
  const yaw = Math.max(-1, Math.min(1, ((noseTip.x - eyeMidX) / eyeSpan) * 2.4));
  const faceHeight = Math.abs(bottom.y - top.y) || 1e-3;
  const eyeMidY = (leftEye.y + rightEye.y) / 2;
  // Pitch: nose vertical offset from the eye line, in face-height units.
  const pitch = Math.max(-1, Math.min(1, ((noseTip.y - eyeMidY) / faceHeight - 0.18) * 4.5));
  return { yaw, pitch: (noseBridge ? pitch : pitch) };
}
