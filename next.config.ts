import type { NextConfig } from 'next';
// The local neural voice runs in Node with native ONNX Runtime: keep it out of
// the bundle, and out of hosted (Vercel) function traces where it cannot fit.
const voiceModules = ['kokoro-js', '@huggingface/transformers', 'onnxruntime-node', 'phonemizer'];
const config: NextConfig = { reactStrictMode: true, serverExternalPackages: voiceModules,
  ...(process.env.VERCEL ? { outputFileTracingExcludes: { '*': ['node_modules/onnxruntime-node/**', 'node_modules/onnxruntime-web/**', 'node_modules/@huggingface/transformers/**', 'node_modules/kokoro-js/**', 'node_modules/phonemizer/**'] } } : {}), poweredByHeader: false, distDir: process.env.NODE_ENV === 'development' ? '.next-dev' : '.next', webpack(config, { dev }) { if (dev) config.cache = false; return config; } };
export default config;
