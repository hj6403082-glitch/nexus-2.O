'use client';
import { ArrowUpRight } from 'lucide-react';
import { ModuleIcon } from './Icon';
import type { NexusModule } from '@/lib/modules';
import { useNexus } from '@/stores/nexus';
export function ModuleCard({ module, active, ordinal }: { module: NexusModule; active: boolean; ordinal: number }) {
  const open = useNexus(s => s.open); const select = useNexus(s => s.select);
  return <button className={`module-card ${active ? 'is-active' : ''}`} data-module={module.id}
    style={{ '--accent': module.accent } as React.CSSProperties}
    onClick={() => active ? open(module.id) : select(module.id)}
    onPointerEnter={() => useNexus.setState({ hovered: module.id })}
    onPointerLeave={() => useNexus.setState({ hovered: null })}
    aria-label={`${active ? 'Open' : 'Select'} ${module.name}`}>
    <div className="card-top"><span className="module-icon"><ModuleIcon name={module.icon} /></span><span className="mono">{String(ordinal + 1).padStart(2, '0')} / NX</span></div>
    <div className={`card-art art-${module.icon}`} aria-hidden="true"><svg viewBox="0 0 260 125" fill="none">
      {module.icon === 'layers' ? <>{[0, 1, 2].map(i => <path key={i} d={`M130 ${18 + i * 22} 208 ${49 + i * 22} 130 ${80 + i * 22} 52 ${49 + i * 22}Z`} fill="currentColor" fillOpacity={0.035 + i * 0.025} stroke="currentColor" strokeOpacity={0.65 - i * .16} />)}<path d="M130 18v106M52 49v44M208 49v44" stroke="currentColor" opacity=".14" /></> : module.icon === 'chart' || module.icon === 'activity' ? <>{[25, 55, 85, 115].map(y => <path key={y} d={`M20 ${y}h220`} stroke="currentColor" opacity=".1" />)}<path d="M20 98 43 91 65 100 90 65 112 74 139 40 161 58 183 32 204 44 240 15" stroke="currentColor" strokeWidth="1.5" /><path d="M20 98 43 91 65 100 90 65 112 74 139 40 161 58 183 32 204 44 240 15V125H20Z" fill="currentColor" opacity=".035" /></> : <>{[22, 36, 50].map((r, i) => <ellipse key={r} cx="130" cy="63" rx={r * 1.5} ry={r} transform={`rotate(${i * 45 - 45} 130 63)`} stroke="currentColor" opacity={.5 - i * .12} />)}<circle cx="130" cy="63" r="4" fill="currentColor" /><path d="M15 63h48m134 0h48M130 0v9m0 108v9" stroke="currentColor" opacity=".3" /></>}
    </svg></div>
    <div className="card-copy"><span className="eyebrow">{module.category}</span><h2>{module.name}</h2><p>{module.subtitle}</p></div>
    <div className="card-bottom"><span><i />{module.phase === 1 ? 'SYSTEM ONLINE' : `PHASE ${module.phase} · NOT CONNECTED`}</span><ArrowUpRight size={16} /></div>
  </button>;
}
