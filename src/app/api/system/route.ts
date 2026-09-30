import os from 'node:os';
import { statfs } from 'node:fs/promises';
import { localRequestAllowed } from '@/ai/server';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
let previous: { idle: number; total: number } | null = null;
export async function GET(request: Request) {
  if (!localRequestAllowed(request)) return Response.json({ error: 'Local requests only.' }, { status: 403 });
  const cpus = os.cpus(); const sample = cpus.reduce((s, cpu) => ({ idle: s.idle + cpu.times.idle, total: s.total + Object.values(cpu.times).reduce((a, b) => a + b, 0) }), { idle: 0, total: 0 });
  const elapsed = previous ? sample.total - previous.total : 0;
  const cpu = previous && elapsed > 0 ? Math.max(0, Math.min(100, (1 - (sample.idle - previous.idle) / elapsed) * 100)) : null; previous = sample;
  const disk = await statfs(process.cwd()).catch(() => null);
  return Response.json({ cpuPercent: cpu, processors: cpus.length, cpuModel: cpus[0]?.model ?? 'Unavailable', totalMemory: os.totalmem(), freeMemory: os.freemem(), uptime: os.uptime(), platform: process.platform, storage: disk ? { total: disk.blocks * disk.bsize, available: disk.bavail * disk.bsize } : null, at: new Date().toISOString() }, { headers: { 'Cache-Control': 'no-store' } });
}
