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

- **Ollama (default):** Install Ollama, then run `ollama pull qwen3:1.7b`. Set `AI_PROVIDER=ollama` and `OLLAMA_MODEL=qwen3:1.7b` in `.env.local`, and restart NEXUS. Keep Ollama running while using AI. Requests stay on loopback; no API key is needed. The model download is approximately 1.4 GB and is separate from this repository. This compact model suits basic local assistance; response quality and speed differ from larger cloud models. You can select another installed chat/tool model with `OLLAMA_MODEL`.
- **Gemini:** `AI_PROVIDER=gemini`, plus `GEMINI_API_KEY`. The default model is `gemini-3.8-flash`; override `GEMINI_MODEL` for your account. Requests include recent conversation and the displayed module context.

Use Ask NEXUS to type or enable voice. Direct module, orbit and transformation commands work without either provider. Conversation history is memory-only. Microphone and speech output are opt-in. Browser recognition may use its vendor's servers; native speech synthesis varies by OS and is not routed through spatial audio. Escape stops active AI input/output.

## Modules

- Projects and Calendar store entries in this browser. Projects can attach local images and videos in IndexedDB. They are not synced cloud accounts.
- Music plays a selected local audio file without uploading it.
- Weather uses [Open-Meteo](https://open-meteo.com/en/docs); News loads [Hacker News headlines](https://github.com/HackerNews/API). Requests are manual, source-labelled and timestamped.
- Stocks includes a locally stored portfolio, quote-based valuation and sector allocation; quotes use `FINNHUB_API_KEY`. Sports uses `FOOTBALL_DATA_TOKEN`.
- Instagram uses `INSTAGRAM_ACCESS_TOKEN`; Facebook-login tokens additionally require `INSTAGRAM_BUSINESS_ID`. Missing permissions or credentials appear as connection errors, never simulated data.
- System shows browser rendering diagnostics, and local server CPU/RAM/storage measurements.

## Controls

Arrows rotate, Enter opens, Escape closes, H toggles HUD, ? shows help, Ctrl/Command K opens the module launcher. Use Human / Spatial for the reversible particle form and the Environment selector for the six procedural environments. In Human mode, use “Keep beside me · open another” to display two modules. Use Group modules to choose cards (or none for the whole orbit), then group/split with the button, the G key, or two open hands moving together/apart (two pinches still zoom). Ambient motion starts LOCKED. Sound is opt-in.

Hand tracking requires an explicit camera grant. Pinch grabs, release returns, swipe rotates, pull/push opens/closes, a still palm freezes drift, a circle wakes NEXUS, and pinching with both hands adjusts orbit scale. Camera frames are processed locally using the bundled MediaPipe runtime/model. Tracking stops when the tab is hidden. Physical camera accuracy still needs device testing.

## Validation

```sh
npm run typecheck
npm test
npm run build
node scripts/check-ai-api.mjs
```

The HTTP check needs the server running on port 3001, or `NEXUS_TEST_URL`. It does not make a paid model request. Unit tests cover gestures, spring rest, transition timelines, local request boundaries, command validation, stream chunking and provider routing. A passing test suite does not substitute for physical webcam, voice, provider-account or GPU performance testing.


Optional live AI verification: run `node scripts/check-ai-live.mjs` while NEXUS is running. This makes one real request through your configured model provider; provider usage charges can apply.

If a key verifies but requests from the app fail immediately, check that the terminal running the server has outbound network access. A server launched in a restricted development sandbox can serve the local interface while being unable to contact cloud providers. Restart the server in a normal terminal, wait for its Ready message, and rerun the live check.

## Grok provider

Set `AI_PROVIDER=grok`, `XAI_API_KEY` and optionally `XAI_MODEL` in `.env.local`, then restart the server. The default model is `grok-4.7`. Obtain an API key from the xAI API console; keep it server-side and never commit it. NEXUS uses streaming chat completions with validated navigation and form tools. It does not enable web/X search. Gemini and local Ollama remain selectable with `AI_PROVIDER=gemini` or `AI_PROVIDER=ollama`; no automatic provider fallback sends your context elsewhere.
