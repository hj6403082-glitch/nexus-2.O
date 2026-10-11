'use client';
import { LogOut } from 'lucide-react';
import { useProject } from '@/stores/project';
import { useForm } from '@/stores/form';
// When a project world is entered, a slim banner names it and offers the way
// back. Hidden in embodied (humanoid) mode, where the form controls own the
// lower screen.
export function ProjectWorldBanner() {
  const focused = useProject(s => s.focused);
  const accent = useProject(s => s.world?.accent);
  const embodied = useForm(s => s.phase !== 'NORMAL');
  if (!focused || embodied) return null;
  return <div className="project-world-banner" style={{ borderColor: `${accent}55` }}>
    <span className="eyebrow" style={{ color: accent }}>IN PROJECT WORLD</span>
    <strong>{focused.title}</strong>
    <button className="text-button" onClick={() => useProject.getState().exit()}>Exit world <LogOut size={15} /></button>
  </div>;
}
