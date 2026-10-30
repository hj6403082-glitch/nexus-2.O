import type { MetadataRoute } from 'next';
// Installable app: Zeno opens in its own window from the Start menu, taskbar or
// desktop instead of a browser tab.
export default function manifest(): MetadataRoute.Manifest {
  return {
    id: '/', name: 'Zeno — Spatial OS', short_name: 'Zeno',
    description: 'Gesture-driven spatial operating system with a local AI brain.',
    start_url: '/?source=app', scope: '/',
    display: 'standalone', display_override: ['window-controls-overlay', 'standalone'],
    orientation: 'any', background_color: '#030f0a', theme_color: '#030f0a', categories: ['productivity', 'utilities'],
    icons: [
      { src: '/icons/icon-192.png', sizes: '192x192', type: 'image/png', purpose: 'any' },
      { src: '/icons/icon-512.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
      { src: '/icons/maskable-512.png', sizes: '512x512', type: 'image/png', purpose: 'maskable' },
      { src: '/icons/icon.svg', sizes: 'any', type: 'image/svg+xml' },
    ],
    shortcuts: [
      { name: 'Ask Zeno', url: '/?source=app&ask=1', icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }] },
      { name: 'Human form', url: '/?source=app&form=human', icons: [{ src: '/icons/icon-192.png', sizes: '192x192' }] },
    ],
  };
}
