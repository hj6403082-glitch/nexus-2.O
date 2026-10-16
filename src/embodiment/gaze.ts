// Real-time webcam gaze signal (Phase 8, Objective 3). A hot object the
// embodiment shader reads every frame: the user's head yaw/pitch (−1..1),
// whether a face is currently tracked, and a confidence. MediaPipe FaceMesh
// fills it; the humanoid's neck IK and optical flares follow it to hold eye
// contact. When no face is tracked the humanoid falls back to pointer-follow.
export const gazeSignal = { yaw: 0, pitch: 0, active: false, confidence: 0 };

// Convert a normalised face-landmark set into a gaze estimate. Landmarks are
// MediaPipe FaceMesh indices in normalised, unmirrored image space (x,y,z,
// origin top-left). `yaw`/`pitch` are the user's head turn, from the nose tip
// against the eye-corner midline and the face's vertical extent (no full PnP
// solve). `x`/`y` are where the face sits in the frame (−1..1, 0 = centred),
// which is what eye contact follows: lean left and NEXUS looks left with you.
export interface FacePoint { x: number; y: number; z?: number }
export interface GazeEstimate { yaw: number; pitch: number; x: number; y: number }
const clamp1 = (v: number) => Math.max(-1, Math.min(1, v));
export function estimateGaze(landmarks: FacePoint[]): GazeEstimate | null {
  if (!landmarks || landmarks.length < 468) return null;
  const noseTip = landmarks[1];
  const leftEye = landmarks[33], rightEye = landmarks[263];       // outer eye corners
  const top = landmarks[10], bottom = landmarks[152];             // forehead / chin
  if (!noseTip || !leftEye || !rightEye || !top || !bottom) return null;
  const eyeMidX = (leftEye.x + rightEye.x) / 2;
  const eyeSpan = Math.abs(rightEye.x - leftEye.x) || 1e-3;
  // Yaw: how far the nose sits from the eye midline, in eye-span units.
  const yaw = clamp1(((noseTip.x - eyeMidX) / eyeSpan) * 2.4);
  const faceHeight = Math.abs(bottom.y - top.y) || 1e-3;
  const eyeMidY = (leftEye.y + rightEye.y) / 2;
  // Pitch: nose vertical offset from the eye line, in face-height units.
  const pitch = clamp1(((noseTip.y - eyeMidY) / faceHeight - 0.18) * 4.5);
  // Face position: the eye midpoint relative to where eyes sit when someone is
  // seated centred in a webcam frame (horizontally centred, ~40% down).
  return { yaw, pitch, x: clamp1((eyeMidX - .5) * 2), y: clamp1((eyeMidY - .4) * 2) };
}

// Map an estimate onto the humanoid's neck target (−1..1 each axis, before the
// renderer scales it into a natural neck range). Mostly follows where the user
// is, with a little of their head turn mirrored back. The camera image is not
// mirrored, so a user moving to their left appears at larger x: negate it.
export function gazeTarget(g: GazeEstimate): { yaw: number; pitch: number } {
  return { yaw: clamp1(-g.x * 1.3 - g.yaw * .25), pitch: clamp1(g.y * 1.3 + g.pitch * .25) };
}
