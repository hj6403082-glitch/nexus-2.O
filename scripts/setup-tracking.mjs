import { mkdir, copyFile, readdir, writeFile } from 'node:fs/promises';
await mkdir('public/mediapipe', { recursive: true });
await mkdir('public/models', { recursive: true });
for (const file of await readdir('node_modules/@mediapipe/tasks-vision/wasm')) {
  if (/\.(wasm|js)$/.test(file)) await copyFile(`node_modules/@mediapipe/tasks-vision/wasm/${file}`, `public/mediapipe/${file}`);
}
const url = 'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task';
const response = await fetch(url);
if (!response.ok) throw new Error(`Model download failed: ${response.status}`);
await writeFile('public/models/hand_landmarker.task', Buffer.from(await response.arrayBuffer()));
console.log('Pinned MediaPipe runtime and hand landmark model installed locally.');
