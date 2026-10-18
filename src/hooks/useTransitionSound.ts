'use client';
import { useEffect } from 'react';
import { useForm } from '@/stores/form';
import { useApp } from '@/stores/app';
import { setSfxEnabled, sfx, unlockSfx } from '@/animations/sfx';
// Plays the transformation sound cues on phase changes and keeps the effects
// mute switch in sync. Effects are on by default and remembered per browser.
export function useTransitionSound() {
  useEffect(() => {
    try { const saved = localStorage.getItem('nexus-sfx'); if (saved === 'off') useApp.setState({ sfx: false }); } catch { /* default on */ }
    setSfxEnabled(useApp.getState().sfx);
    const unlock = () => unlockSfx();
    window.addEventListener('pointerdown', unlock); window.addEventListener('keydown', unlock);
    const offApp = useApp.subscribe((s, p) => { if (s.sfx !== p.sfx) { setSfxEnabled(s.sfx); try { localStorage.setItem('nexus-sfx', s.sfx ? 'on' : 'off'); } catch { /* storage blocked */ } } });
    const offForm = useForm.subscribe((s, p) => {
      if (s.phase === p.phase) return;
      if (s.phase === 'COLLAPSING' && p.phase !== 'RETURNING') sfx.gather();
      else if (s.phase === 'PARTICLE_CORE') sfx.ignite();
      else if (s.phase === 'SKELETON_FORMING') sfx.scan();
      else if (s.phase === 'HUMANOID_ACTIVE') sfx.present();
      else if (s.phase === 'RETURNING') sfx.disperse();
    });
    return () => { window.removeEventListener('pointerdown', unlock); window.removeEventListener('keydown', unlock); offApp(); offForm(); };
  }, []);
}
