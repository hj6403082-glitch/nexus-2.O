'use client';
import { useEffect, useState } from 'react';
import { readAssets, writeAsset, deleteAssets, type ProjectAsset } from '@/knowledge/media';
export function ProjectMedia({ project }: { project: string }) {
  const [assets, setAssets] = useState<(ProjectAsset & { url: string })[]>([]), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const load = async () => { const records = await readAssets(project); setAssets(records.map(a => ({ ...a, url: URL.createObjectURL(a.blob) }))); };
  useEffect(() => { let mounted = true; void readAssets(project).then(records => { if (mounted) setAssets(records.map(a => ({ ...a, url: URL.createObjectURL(a.blob) }))); }).catch(() => { if (mounted) setError('Project media storage is unavailable.'); }); return () => { mounted = false; }; }, [project]);
  useEffect(() => () => assets.forEach(a => URL.revokeObjectURL(a.url)), [assets]);
  return <details className="project-media"><summary>Images & videos · {assets.length}</summary><p className="muted">Stored on this device. Up to 10 files per project, 20 MB each.</p><input type="file" accept="image/*,video/*" multiple disabled={busy} aria-label="Add project images or videos" onChange={async e => { const files = [...(e.target.files ?? [])]; e.target.value = ''; if (assets.length + files.length > 10 || files.some(f => f.size > 20 * 1024 ** 2 || !/^(image|video)\//.test(f.type))) { setError('Choose up to 10 images/videos, each under 20 MB.'); return; } setBusy(true); setError(''); try { for (const file of files) await writeAsset({ id: crypto.randomUUID(), project, name: file.name, type: file.type, blob: file }); await load(); } catch { setError('Could not save media. Browser storage may be full or unavailable.'); await load().catch(() => {}); } finally { setBusy(false); } }} />{error && <p role="alert">{error}</p>}
    {assets.map(asset => <figure key={asset.id}>{asset.type.startsWith('video/') ? <video controls preload="metadata" src={asset.url} /> : <img src={asset.url} alt={asset.name} loading="lazy" />}<figcaption>{asset.name}</figcaption><button className="text-button" disabled={busy} onClick={async () => { setBusy(true); try { await deleteAssets([asset.id]); await load(); } catch { setError('Could not remove this file.'); } finally { setBusy(false); } }}>Remove media</button></figure>)}
  </details>;
}
