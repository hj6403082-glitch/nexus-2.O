'use client';
import { useEffect } from 'react';
import { watchInstall } from '@/stores/app';
import { useAssistant } from '@/stores/assistant';
import { useForm } from '@/stores/form';
// Registers the app-shell service worker (production only; development always
// serves fresh code) and handles the app's Start-menu shortcuts.
export function AppShell() {
  useEffect(() => {
    const stop = watchInstall();
    if ('serviceWorker' in navigator) {
      if (process.env.NODE_ENV === 'production') navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(() => { /* Installing still works without offline support. */ });
      else void navigator.serviceWorker.getRegistrations().then(list => list.forEach(r => void r.unregister())).catch(() => {});
    }
    const params = new URLSearchParams(location.search);
    if (params.get('ask') === '1') useAssistant.getState().wake();
    // Wait for the orbit cards to exist before gathering them into a figure.
    const timer = params.get('form') === 'human' ? setTimeout(() => useForm.getState().request('human'), 2500) : null;
    if (params.has('source') || params.has('ask') || params.has('form')) history.replaceState(null, '', location.pathname);
    return () => { stop(); if (timer) clearTimeout(timer); };
  }, []);
  return null;
}
