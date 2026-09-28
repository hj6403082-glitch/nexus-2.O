import { Activity, CalendarDays, ChartNoAxesCombined, Cloud, Cpu, Instagram, Layers3, Music2, Newspaper, Sparkles } from 'lucide-react';
const icons = { instagram: Instagram, chart: ChartNoAxesCombined, layers: Layers3, activity: Activity, calendar: CalendarDays, cloud: Cloud, sparkles: Sparkles, newspaper: Newspaper, music: Music2, cpu: Cpu };
export function ModuleIcon({ name, size = 22 }: { name: string; size?: number }) { const Icon = icons[name as keyof typeof icons] ?? Layers3; return <Icon size={size} strokeWidth={1.35} aria-hidden="true" />; }
