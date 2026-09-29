import type { NextConfig } from 'next';
const config: NextConfig = { reactStrictMode: true, poweredByHeader: false, distDir: process.env.NODE_ENV === 'development' ? '.next-dev' : '.next', webpack(config, { dev }) { if (dev) config.cache = false; return config; } };
export default config;
