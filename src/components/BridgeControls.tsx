'use client';
import { useState } from 'react';
import { Cpu, MonitorSmartphone, Plug, PlugZap, RefreshCw } from 'lucide-react';
import { useBridge } from '@/stores/bridge';

// System-panel UI for connecting NEXUS to the local Windows bridge and reading
// live screen context / native diagnostics from it. The bridge runs on the
// user's own PC; this only ever talks to the loopback URL they configured.
export function BridgeControls() {
  const { status, url, token, error, verbs, screen, diagnostics, busy } = useBridge();
  const { setConfig, connect, disconnect, readScreen, readDiagnostics } = useBridge();
  const [showToken, setShowToken] = useState(false);
  const connected = status === 'connected';
  return <section className="knowledge bridge-controls">
    <h3><MonitorSmartphone size={16} /> Windows agent</h3>
    <p className="muted">Connect this PC to let NEXUS read the focused window and native GPU/CPU metrics, and orchestrate apps. Runs locally on loopback; nothing leaves your machine.</p>
    {!connected ? <div className="bridge-connect">
      <label>Bridge URL<input value={url} onChange={e => setConfig(e.target.value, token)} placeholder="http://127.0.0.1:4517" spellCheck={false} /></label>
      <label>Token<input type={showToken ? 'text' : 'password'} value={token} onChange={e => setConfig(url, e.target.value)} placeholder="Paste the token the bridge printed" spellCheck={false} onFocus={() => setShowToken(true)} onBlur={() => setShowToken(false)} /></label>
      <button className="text-button" onClick={() => void connect()} disabled={status === 'connecting'}><Plug size={15} /> {status === 'connecting' ? 'Connecting…' : 'Connect this PC'}</button>
    </div> : <div className="bridge-live">
      <div className="bridge-status"><span className="status-led" /> Connected · {verbs.length} capabilities</div>
      <div className="bridge-actions">
        <button className="text-button" onClick={() => void readScreen()} disabled={busy}><RefreshCw size={14} /> Read focused window</button>
        <button className="text-button" onClick={() => void readDiagnostics()} disabled={busy}><Cpu size={14} /> Refresh diagnostics</button>
        <button className="text-button" onClick={disconnect}><PlugZap size={14} /> Disconnect</button>
      </div>
      {diagnostics && <div className="diagnostics"><div><span>CPU load</span><strong>{diagnostics.cpuLoad == null ? '—' : `${Math.round(diagnostics.cpuLoad)}%`}</strong></div><div><span>GPU</span><strong title={diagnostics.gpuName}>{diagnostics.gpuName?.slice(0, 18) || '—'}</strong></div><div><span>Memory free</span><strong>{Math.round(diagnostics.freeMemMB / 1024)}<small> / {Math.round(diagnostics.totalMemMB / 1024)} GiB</small></strong></div><div><span>Cores</span><strong>{diagnostics.cores}<small> / {diagnostics.logical}t</small></strong></div></div>}
      {screen && <div className="bridge-screen"><span className="eyebrow">FOCUSED · {screen.process || 'unknown'}</span><p className="bridge-title">{screen.title || 'Untitled window'}</p><p className="muted">{screen.controlCount} UI elements · showing {screen.controls.length}</p>{!!screen.controls.length && <ul className="bridge-tree">{screen.controls.slice(0, 8).map((c, i) => <li key={i}><b>{c.type}</b>{c.name ? ` · ${c.name.slice(0, 48)}` : ''}{c.focus ? ' ◂ focus' : ''}</li>)}</ul>}</div>}
    </div>}
    {error && <p className="bridge-error" role="alert">{error}</p>}
  </section>;
}
