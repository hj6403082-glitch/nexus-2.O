import type { NextConfig } from 'next';
const config: NextConfig = { reactStrictMode: true, poweredByHeader: false, distDir: process.env.NODE_ENV === 'development' ? '.next-dev' : '.next' };
export default config;
