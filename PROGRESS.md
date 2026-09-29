# NEXUS implementation ledger

This is a working implementation, not a declaration that all seven phases have passed acceptance.

| Phase | Implemented | Remaining acceptance work |
| --- | --- | --- |
| 1 | Spatial orbit, local hand tracking, fallback controls, motion gating, adaptive rendering, ambient audio | Physical webcam testing and sustained hardware performance measurement |
| 2 | Gemini and local Ollama streaming, bounded memory/context, local commands, interruption-aware browser speech, model transformation tool | Live model setup and response verification; studio TTS and spatial voice routing |
| 3 | Local project notes, local agenda, audio-file playback, Open-Meteo forecast and Hacker News headlines; credential-gated Finnhub, football-data and Instagram adapters | Provider credentials and live verification; portfolio accounting, sports standings, Instagram reach/growth insights, calendar sync and richer project media |
| 4 | Six selectable world palettes, lighting and filmic grades, module presentation brackets and scan | Distinct procedural world geometry, two-hand grouping/zoom, weather-driven effects and full camera choreography |
| 5 | Opt-in macOS bridge with explicit verbs, installed-app resolution, execFile-only execution, loopback/origin guards, permission errors; Windows 501 | macOS runtime testing, display enumeration and placement, remaining media/capture/focus verbs and complete voice/launcher routing |
| 6 | Exact spring rest, motion off by default, named spring intents, presentation clock, six grades | Full targeting/approach/settle scene synchronization and screenshot/performance acceptance |
| 7 | Rasterized card sources, reversible single-buffer bust, GPU bake, Poisson selection, rigid head motion, five-step voice jaw, fixed transformation count; initial baked hand and panel anchor | Hand articulation and screen-space rig refinement, two-panel layout, edge-first erosion, phase screenshots and physical voice validation |

## Local AI

Ollama needs no API key. Install Ollama separately and download a compatible local chat/tool model. `AI_PROVIDER=ollama` uses the first installed local model, or set `OLLAMA_MODEL` explicitly. Cloud-tagged models are excluded. The app only contacts Ollama at `127.0.0.1:11434`.

Gemini remains optional: set `AI_PROVIDER=gemini` and `GEMINI_API_KEY` in `.env.local`. Never commit credentials. Browser speech recognition may still use the browser vendor's service even when the language model is local.

## Data and platform boundaries

Projects and Calendar currently use browser localStorage; they are not synced accounts. Local audio stays on the device. Weather is forecast-model output. News summaries see headlines, not full article text. Account tokens are server-only and never returned to clients.

The desktop bridge is disabled unless `NEXUS_DESKTOP_ENABLED=true`, and mutating routes return 501 outside macOS. No desktop operations have been exercised on this Windows host.

## Preview

`npm run dev -- --port 3001` starts the development preview at http://127.0.0.1:3001/.
After a successful production build, use `npm start -- --port 3001` for a quieter preview.
The URL stays the same, but its local server must remain running.
