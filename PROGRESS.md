# NEXUS implementation ledger

This is a working implementation, not a declaration that all seven phases have passed acceptance.

| Phase | Implemented | Remaining acceptance work |
| --- | --- | --- |
| 1 | Spatial orbit, local hand tracking, fallback controls, motion gating, adaptive rendering, ambient audio | Physical webcam testing and sustained hardware performance measurement |
| 2 | Gemini and local Ollama streaming, bounded memory/context, local commands, interruption-aware browser speech, model transformation tool | Gemini key verified; streaming provider returned temporary overload. Ollama installation pending. Studio TTS and spatial voice routing |
| 3 | Local project notes with IndexedDB image/video attachments, local agenda, audio-file playback, Open-Meteo forecast and Hacker News headlines; local portfolio valuation and sector allocation; native machine telemetry; credential-gated Finnhub, football-data fixtures/league standings and Instagram adapters | Provider credentials and live verification; historical portfolio performance, Instagram reach/growth insights, calendar sync and project-specific spatial scenes |
| 4 | Six distinct procedural environments, lighting and filmic grades, module presentation brackets and scan, two-hand zoom, weather-driven world selection and motion-gated rain | Two-hand grouping and full camera choreography |
| 5 | Opt-in macOS bridge with 16 enumerated execFile-only verbs (apps, displays, launch, quit, hide-others, website, media, volume, screenshot, clipboard, lock, sleep, Do Not Disturb, note, reminder); live installed-app resolution; NSScreen→AppleScript display enumeration with real names and second-display window placement; Chrome `--new-window`+id-diff and Safari document targeting; ⌘K palette ranking apps, websites, modules, personal destinations and actions; voice routing for every verb; Instagram follower back-accumulation, reach, engagement and top content; loopback/same-origin guards; translated permission errors; 501 off-macOS | macOS runtime testing of permissions, real multi-display placement and account-token verification |
| 6 | Exact spring rest, motion off by default, named spring intents, presentation clock, six grades | Full targeting/approach/settle scene synchronization and screenshot/performance acceptance |
| 7 | Rasterized card sources, reversible single-buffer bust, GPU bake, Poisson selection, rigid head motion, five-step voice jaw, fixed transformation count; baked hand with finger joints, viewport-relative panel anchor, edge-weighted erosion and two-panel pinning | Visual acceptance of hand articulation and two-panel layout, full phase screenshots and physical voice validation |

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

## Latest verification — 2026-10-03

TypeScript and 28 unit tests pass. Weather and News returned live data. Gemini accepted a minimal generation request; streamed generation later returned upstream 503, now handled with a bounded retry and a clear error. New UI additions still require final visual checks. Never interpret credential-gated adapters as verified account integrations.


The latest source adds recessed facial features, larger eye particles, and short-viewport layout fixes. Sports standings are validated with a mocked provider response; live league access still requires FOOTBALL_DATA_TOKEN. The locally configured account credentials were checked by presence only: Gemini is configured; Finnhub, football-data and Instagram are still missing.
