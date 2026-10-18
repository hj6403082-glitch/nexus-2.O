# NEXUS

A local spatial computing application built with Next.js 15, React 19, Three.js, React Three Fiber and MediaPipe. See [PROGRESS.md](PROGRESS.md) for the exact implementation and acceptance status of all seven phases.

## Run

```sh
npm install
node scripts/setup-tracking.mjs
npm run dev -- --port 3001
```

Open http://127.0.0.1:3001/. For a production preview, run `npm run build` followed by `npm start -- --port 3001`. Node 22+ is recommended. The development disk cache is disabled because OneDrive may lock its files on Windows.

## Open NEXUS as an app (Windows, no terminal)

1. Download the repository (Code → Download ZIP) and extract it, or keep your existing NEXUS folder.
2. Double-click **Start NEXUS.cmd**. The first run installs Node.js if needed (via winget), installs components and builds NEXUS; this takes a few minutes once. Later starts take seconds and only rebuild after updates.
3. NEXUS opens in its own app window (Edge or Chrome app mode, no tabs or address bar). The launcher also adds a **NEXUS** shortcut to your Desktop and Start menu, and starts the Ollama app if it is installed.

The engine keeps running quietly in the background on `127.0.0.1:3001`; double-click **Stop NEXUS.cmd** to stop it. Its log is in `%LOCALAPPDATA%\NEXUS\engine.log`.

NEXUS is also an installable web app: in the app window or browser, use **INSTALL APP** (top right) or the install icon in the address bar to pin it to the taskbar and Start menu. If the engine is not running when you open it, the window shows a reconnect screen and opens NEXUS by itself once the engine is up. The AI brain only works where Ollama runs, so use NEXUS from your own computer rather than a hosted copy when you want local AI.

If Ollama is running without a model, Ask NEXUS shows a **Download** button that fetches the model (with progress) without a terminal.

## AI: local or cloud

Copy `.env.example` to `.env.local` and choose a provider. Never commit `.env.local` or paste credentials into the assistant UI.

- **Ollama (default):** Install Ollama, then run `ollama pull qwen3:1.7b`. Set `AI_PROVIDER=ollama` and `OLLAMA_MODEL=qwen3:1.7b` in `.env.local`, and restart NEXUS. Keep Ollama running while using AI. Requests stay on loopback; no API key is needed. The model download is approximately 1.4 GB and is separate from this repository. This compact model suits basic local assistance; response quality and speed differ from larger cloud models. You can select another installed chat/tool model with `OLLAMA_MODEL`.
- **Gemini:** `AI_PROVIDER=gemini`, plus `GEMINI_API_KEY`. The default model is `gemini-3.8-flash`; override `GEMINI_MODEL` for your account. Requests include recent conversation and the displayed module context.

Use Ask NEXUS to type or enable voice. Direct module, orbit and transformation commands work without either provider. Conversation history is memory-only. Microphone and speech output are opt-in. Browser recognition may use its vendor's servers; native speech synthesis varies by OS and is not routed through spatial audio. Escape stops active AI input/output.

**Speed.** NEXUS keeps the Ollama model loaded (`OLLAMA_KEEP_ALIVE`, default `30m`), warms it when the app opens, sends only the recent conversation, and keeps the system prompt identical between questions so Ollama reuses its prompt cache. Answers are kept short unless you ask for depth. The first answer after starting your PC is still slower while the model loads.

**Voice.** With voice on, NEXUS speaks with a local neural voice (Kokoro, `am_michael` by default; change it with `NEXUS_VOICE_ID`). The first time, it downloads about 90 MB into `.nexus-cache/models`, so it needs internet once; until then, and whenever it is unavailable, the browser's best natural voice is used. In Ask NEXUS, **Character** picks *Ultron-style synthetic* (an original deep, metallic, slightly doubled character voice, not a copy of any actor) or *Natural human*. Set `ELEVENLABS_API_KEY` to use ElevenLabs instead, or `NEXUS_LOCAL_VOICE=off` to skip the neural voice. Speech starts on the first phrase and the next sentences are prepared while one plays.

**Sound effects.** Transformations have synthesized sound cues (no audio files). Toggle them with **FX** in the bottom bar; the choice is remembered.

**The core.** In spatial mode a living energy sphere sits at the centre of the orbit. It breathes while idle, swirls while NEXUS thinks, ripples with the voice while it speaks and swells toward your pointer. Click it to talk to NEXUS.

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
