# NEXUS implementation ledger

This is a working implementation, not a declaration that all seven phases have passed acceptance.

## Verification — 2026-10-12

Merged `claude/project-thread-ynan24` into `codex/nexus-spatial-human`, preserving the keyboard disclosure fix. Added Grok streaming with server-only credentials, bounded SSE/tool parsing, explicit provider selection, and five provider tests. The combined 53-test suite passed, and the production build passed compilation and TypeScript validation after clearing stale generated desktop-route types. API checks passed for status, cross-origin rejection and malformed requests. A real xAI request rejected the supplied credential as an incorrect API key; live Grok generation is not verified.

Browser checks passed for launcher search, System panel opening, return to orbit, grouping, human transformation completion and return to spatial mode. No browser errors were captured during these checks. The human screenshot still shows coarse/uneven bead coverage; this is functional verification, not visual acceptance. Physical hand tracking, microphone/voice, connected accounts and sustained GPU performance remain unverified. The preview now serves the combined production build at port 3001.

| Phase | Implemented | Remaining acceptance work |
| --- | --- | --- |
| 1 | Spatial orbit, local hand tracking, fallback controls, motion gating, adaptive rendering, ambient audio | Physical webcam testing and sustained hardware performance measurement |
| 2 | Gemini and local Ollama streaming, bounded memory/context, local commands, interruption-aware browser speech, model transformation tool | Gemini key verified; streaming provider returned temporary overload. Ollama installation pending. Studio TTS and spatial voice routing |
| 3 | Local project notes with IndexedDB image/video attachments, local agenda, audio-file playback, Open-Meteo forecast and Hacker News headlines; local portfolio valuation, sector allocation and historical performance (from local daily snapshots); Instagram reach/growth/engagement; native machine telemetry; credential-gated Finnhub, football-data fixtures/league standings and Instagram adapters; per-project floating worlds (each project entered as its own deterministic 3D island — accent, filmic grade and ring/shard geometry hashed from its identity — with the orbit receding and a way back) | Provider credentials and live verification; calendar account sync (needs an external calendar account) |
| 4 | Six distinct procedural environments, lighting and filmic grades, module presentation brackets and scan, two-hand zoom, weather-driven world selection and motion-gated rain, AI-Worlds module→environment morphing, and two-hand grouping / multi-select (open hands together gather the cards into a grid, apart spread them back; also the G key, a HUD toggle, and shift-click on the orbit dots to pick which); cinematic camera choreography (composable shots: crane-down on module open, pull-back to frame the gathered grid, dolly-and-arc into a project world) | — |
| 5 | macOS desktop bridge removed (the project targets Windows). ⌘K palette ranking modules, websites and personal destinations (opens a new tab, or hands over a link after a voice request); voice routing for websites and personal destinations; Instagram follower back-accumulation, reach, engagement and top content | Live Instagram token verification |
| 6 | Measured stillness (motion off by default, 0..1 gate, exactly-zero zero-input drift, LOCKED/DRIFT indicator); no physics/throwing (cards return to orbit slot on a spring); master-clock targeting/approach/settle presentation with camera push and scan; six world-specific filmic grades splitting the blue ramp (violet shadows, warm highlights, 18%-grey contrast pivot, halation); earned gold at centre on a power curve, drawn dimmer than blue and gated entirely off warned cards so gold never reads as warning orange; named motion vocabulary | On-device GPU performance measurement; artist review of grade intensities |
| 7 | Rasterized card sources, reversible single-buffer bust, GPU bake, Poisson selection, rigid head motion, five-step voice jaw, fixed transformation count; baked hand with finger joints, viewport-relative panel anchor, edge-weighted erosion and two-panel pinning | Visual acceptance of hand articulation and two-panel layout, full phase screenshots and physical voice validation |

## Local AI

Ollama needs no API key. Install Ollama separately and download a compatible local chat/tool model. `AI_PROVIDER=ollama` uses the first installed local model, or set `OLLAMA_MODEL` explicitly. Cloud-tagged models are excluded. The app only contacts Ollama at `127.0.0.1:11434`.

Gemini remains optional: set `AI_PROVIDER=gemini` and `GEMINI_API_KEY` in `.env.local`. Never commit credentials. Browser speech recognition may still use the browser vendor's service even when the language model is local.

## Data and platform boundaries

Projects and Calendar currently use browser localStorage; they are not synced accounts. Local audio stays on the device. Weather is forecast-model output. News summaries see headlines, not full article text. Account tokens are server-only and never returned to clients.

## Preview

`npm run dev -- --port 3001` starts the development preview at http://127.0.0.1:3001/.
After a successful production build, use `npm start -- --port 3001` for a quieter preview.
The URL stays the same, but its local server must remain running.

## Latest verification — 2026-10-08

31 unit tests and TypeScript checks pass. Portfolio storage now also rejects corrupt records without overwriting them. Gemini streamed text and a completion event through the running NEXUS API after the server was restarted with network access and finished warming up. A preceding request timed out, so this confirms connectivity rather than sustained reliability.

The current checkpoint passes 30 unit tests, including grouping thresholds and corrupt saved-collection handling. Unreadable project/calendar storage is preserved with editing disabled. Browser acceptance of grouping and presentation remains pending.

TypeScript and 29 unit tests pass. Weather and News returned live data. Gemini accepted a minimal generation request; streamed generation later returned upstream 503, now handled with a bounded retry and a clear error. New UI additions still require final visual checks. Never interpret credential-gated adapters as verified account integrations.


The latest source adds recessed facial features, larger eye particles, and short-viewport layout fixes. Sports standings are validated with a mocked provider response; live league access still requires FOOTBALL_DATA_TOKEN. The locally configured account credentials were checked by presence only: Gemini is configured; Finnhub, football-data and Instagram are still missing.
