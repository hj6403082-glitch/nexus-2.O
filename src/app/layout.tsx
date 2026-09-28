import type { Metadata } from 'next';
import './globals.css';
export const metadata: Metadata = {
  title: 'NEXUS — Spatial OS',
  description: 'A quieter interface between you and your digital world. Gesture-driven spatial computing.',
  icons: { icon: '/favicon.svg' },
};
export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
