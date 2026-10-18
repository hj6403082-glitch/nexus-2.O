import type { Metadata, Viewport } from 'next';
import './globals.css';
import './futuristic.css';
export const metadata: Metadata = {
  title: 'NEXUS — Spatial OS',
  applicationName: 'NEXUS',
  description: 'A quieter interface between you and your digital world. Gesture-driven spatial computing.',
  icons: { icon: [{ url: '/favicon.svg', type: 'image/svg+xml' }, { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' }], apple: '/icons/apple-touch-icon.png' },
  appleWebApp: { capable: true, title: 'NEXUS', statusBarStyle: 'black-translucent' },
  formatDetection: { telephone: false },
};
export const viewport: Viewport = { themeColor: '#05080e', colorScheme: 'dark', width: 'device-width', initialScale: 1, viewportFit: 'cover' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
