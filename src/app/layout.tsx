import type { Metadata, Viewport } from 'next';
import './globals.css';
import './futuristic.css';
import './liquid.css';
export const metadata: Metadata = {
  title: 'Zeno — Spatial OS',
  applicationName: 'Zeno',
  description: 'A quieter interface between you and your digital world. Gesture-driven spatial computing.',
  icons: { icon: [{ url: '/favicon.svg', type: 'image/svg+xml' }, { url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' }], apple: '/icons/apple-touch-icon.png' },
  appleWebApp: { capable: true, title: 'Zeno', statusBarStyle: 'black-translucent' },
  formatDetection: { telephone: false },
};
export const viewport: Viewport = { themeColor: '#06041a', colorScheme: 'dark', width: 'device-width', initialScale: 1, viewportFit: 'cover' };
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
