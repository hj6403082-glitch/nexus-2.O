'use client';
import { useEffect, useState } from 'react';
type Telemetry = { cpuPercent: number | null; processors: number; cpuModel: string; totalMemory: number; freeMemory: number; uptime: number; platform: string; storage: { total: number; available: number } | null; at: string };
const gb = (bytes: number) => (bytes / 1024 ** 3).toFixed(1);
export function MachineTelemetry() {
  const [data, setData] = useState<Telemetry | null>(null), [error, setError] = useState('');
  useEffect(() => {
    const abort = new AbortController(); let active = false;
    const refresh = async () => { if (active || document.hidden) return; active = true; try { const response = await fetch('/api/system', { signal: abort.signal }); if (!response.ok) throw new Error(); const result = await response.json(); if (!abort.signal.aborted) { setData(result); setError(''); } } catch { if (!abort.signal.aborted) setError('Machine telemetry is unavailable.'); } finally { active = false; } };
    void refresh(); const timer = setInterval(() => void refresh(), 3000); return () => { abort.abort(); clearInterval(timer); };
  }, []);
  return <section className="knowledge"><h3>Machine telemetry</h3>{error && <p role="status">{error}</p>}{data ? <><div className="diagnostics"><div><span>CPU</span><strong>{data.cpuPercent === null ? 'Measuring' : `${data.cpuPercent.toFixed(0)}%`}</strong></div><div><span>Memory used</span><strong>{gb(data.totalMemory - data.freeMemory)}<small> / {gb(data.totalMemory)} GiB</small></strong></div><div><span>Disk available</span><strong>{data.storage ? gb(data.storage.available) : '—'}<small> GiB</small></strong></div><div><span>Uptime</span><strong>{Math.floor(data.uptime / 3600)}<small> hours</small></strong></div></div><p className="muted">{data.cpuModel} · {data.processors} logical processors · {data.platform}. Local OS counters, updated {new Date(data.at).toLocaleTimeString()}. Disk figures describe the project’s volume. GPU utilization and battery telemetry are not provided by this endpoint.</p></> : !error && <p className="muted">Reading local machine counters…</p>}</section>;
}
