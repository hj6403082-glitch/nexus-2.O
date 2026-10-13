import { mkdir, copyFile, readdir, writeFile } from 'node:fs/promises';
await mkdir('public/mediapipe', { recursive: true });
await mkdir('public/models', { recursive: true });
for (const file of await readdir('node_modules/@mediapipe/tasks-vision/wasm')) {
  if (/\.(wasm|js)$/.test(file)) await copyFile(`node_modules/@mediapipe/tasks-vision/wasm/${file}`, `public/mediapipe/${file}`);
}
async function download(url, out, label, required) {
  try {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`${response.status}`);
    await writeFile(out, Buffer.from(await response.arrayBuffer()));
    console.log(`Installed ${label}.`);
  } catch (error) {
    const message = `Could not download ${label} (${error.message}).`;
    if (required) throw new Error(message);
    console.warn(`${message} Webcam gaze will be unavailable until it is present.`);
  }
}
await download('https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task', 'public/models/hand_landmarker.task', 'hand landmark model', true);
// Face landmark model for Phase 8 webcam gaze tracking (optional).
await download('https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task', 'public/models/face_landmarker.task', 'face landmark model', false);
console.log('Pinned MediaPipe runtime and landmark models installed locally.');
