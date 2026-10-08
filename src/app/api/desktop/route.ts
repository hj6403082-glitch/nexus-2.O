import { localRequestAllowed, readBoundedJson } from '@/ai/server';
import { DesktopError, executeDesktop, permissionMessage, validateDesktop, verbs } from '@/desktop/bridge';
export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';
export async function GET(request: Request) {
  if (!localRequestAllowed(request)) return Response.json({ error: 'Local requests only.' }, { status: 403 });
  return Response.json({ supported: process.platform === 'darwin', enabled: process.env.NEXUS_DESKTOP_ENABLED === 'true', verbs, message: process.platform === 'darwin' ? 'Desktop actions require NEXUS_DESKTOP_ENABLED=true on the server.' : 'The desktop bridge requires macOS. All spatial features remain available on Windows.' });
}
export async function POST(request: Request) {
  if (!localRequestAllowed(request, true)) return Response.json({ error: 'Same-origin loopback requests only.' }, { status: 403 });
  if (process.platform !== 'darwin') return Response.json({ error: 'Desktop control requires macOS. This machine is not supported.' }, { status: 501 });
  if (process.env.NEXUS_DESKTOP_ENABLED !== 'true') return Response.json({ error: 'Desktop control is off. Set NEXUS_DESKTOP_ENABLED=true in .env.local and restart to enable it.' }, { status: 403 });
  let input;
  try { input = validateDesktop(await readBoundedJson(request, 16000)); } catch { return Response.json({ error: 'Invalid action.' }, { status: 400 }); }
  if (!input) return Response.json({ error: 'Unknown or invalid desktop action.' }, { status: 400 });
  try { return Response.json(await executeDesktop(input)); }
  catch (error) { return Response.json({ error: error instanceof DesktopError ? error.message : permissionMessage(error) }, { status: error instanceof DesktopError ? 422 : 400 }); }
}
