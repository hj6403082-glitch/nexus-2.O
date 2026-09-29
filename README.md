# NEXUS

A local spatial computing application built with Next.js 15, React 19, Three.js, React Three Fiber and MediaPipe. See [PROGRESS.md](PROGRESS.md) for the exact implementation and acceptance status of all seven phases.

## Run

```sh
npm install
node scripts/setup-tracking.mjs
npm run dev -- --port 3001
```

Open http://127.0.0.1:3001/. For a production preview, run `npm run build` followed by `npm start -- --port 3001`. Node 22+ is recommended. The development disk cache is disabled because OneDrive may lock its files on Windows.

## AI: local or cloud

Copy `.env.example` to `.env.local` and choose a provider. Never commit `.env.local` or paste credentials into the assistant UI.

- **Ollama:** `AI_PROVIDER=ollama`. Install Ollama and download a local model with chat/tool support. Set `OLLAMA_MODEL` to its name, or leave it blank to select the first installed local model. Requests stay on loopback; no API key is needed. Installation and model downloads are separate from this repository.
- **Gemini:** `AI_PROVIDER=gemini`, plus `GEMINI_API_KEY`. The default model is `gemini-3.8-flash`; override `GEMINI_MODEL` for your account. Requests include recent conversation and the displayed module context.

Use Ask NEXUS to type or enable voice. Direct module, orbit and transformation commands work without either provider. Conversation history is memory-only. Microphone and speech output are opt-in. Browser recognition may use its vendor's servers; native speech synthesis varies by OS and is not routed through spatial audio. Escape stops active AI input/output.

## Modules

- Projects and Calendar store entries in this browser. They are not synced cloud accounts.
- Music plays a selected local audio file without uploading it.
- Weather uses [Open-Meteo](https://open-meteo.com/en/docs); News loads [Hacker News headlines](https://github.com/HackerNews/API). Requests are manual, source-labelled and timestamped.
- Stocks uses `FINNHUB_API_KEY`; Sports uses `FOOTBALL_DATA_TOKEN`.
- Instagram uses `INSTAGRAM_ACCESS_TOKEN`; Facebook-login tokens additionally require `INSTAGRAM_BUSINESS_ID`. Missing permissions or credentials appear as connection errors, never simulated data.
- System shows measured browser rendering diagnostics and desktop bridge availability.

## Controls

Arrows rotate, Enter opens, Escape closes, H toggles HUD, ? shows help, Ctrl/Command K opens the module launcher. Use Human / Spatial for the reversible particle form and the Environment selector for the six palettes. Ambient motion starts LOCKED. Sound is opt-in.

Hand tracking requires an explicit camera grant. Pinch grabs, release returns, swipe rotates, pull/push opens/closes, a still palm freezes drift, and a circle wakes NEXUS. Camera frames are processed locally using the bundled MediaPipe runtime/model. Tracking stops when the tab is hidden. Physical camera accuracy still needs device testing.

## Desktop bridge

The macOS bridge is off unless `NEXUS_DESKTOP_ENABLED=true`. Supported initial verbs are listed in the System module. Implementations use fixed executables and argument arrays, installed-app resolution, bounded input, same-origin and loopback checks. No arbitrary shell command, shutdown, restart or deletion exists. Other platforms return HTTP 501. macOS operations are unverified on this Windows development host; multi-display targeting and additional verbs remain in the progress ledger.

## Validation

```sh
npm run typecheck
npm test
npm run build
node scripts/check-ai-api.mjs
```

The HTTP check needs the server running on port 3001, or `NEXUS_TEST_URL`. It does not make a paid model request. Unit tests cover gestures, spring rest, transition timelines, local request boundaries, command validation, stream chunking, desktop resolution and provider routing. A passing test suite does not substitute for physical webcam, voice, provider-account or GPU performance testing.
