# NEXUS implementation ledger

This is a working implementation, not a declaration that all seven phases have passed acceptance.

## Phase 8 corrections — 2026-10-13

Integrated the Phase 8 branch while keeping Ollama/Qwen3 as the local default. Fixed window-state verbs to call Windows ShowWindowAsync, with foreground activation limited to focus. App launch now resolves an exact installed Start-menu name (or a small set of Windows utilities); raw executable paths, caller arguments and command interpreters are rejected, and user input travels as environment data rather than PowerShell source. Research now fetches static public page text with checked/pinned DNS addresses, redirect revalidation, size/time limits and no script/subresource execution. IPv6 research is conservatively unsupported.

Serialized voice synthesis/playback, replaced the fallback's one-shot timer with completion-driven queue advancement, flushed final unpunctuated text, and made interruption abort in-flight synthesis. Removed silent baseline fluid displacement and added exact settling, released old GPU simulations on repeated transforms, and guarded the shader when GPU computation is unavailable. Installed the missing MediaPipe face model.

Regression checks: 56 application tests and 13 bridge tests passed. The Windows native helper compiled and correctly rejected a nonexistent test window without changing a real application. Full physical webcam, premium voice account playback, and real application window-state acceptance still need device testing.

Production build completed successfully, including TypeScript validation. The rebuilt preview serves port 3001. API boundary checks and a live Ollama streamed reply passed after restart. Browser reload succeeded and human transformation started with no recorded browser errors; screenshot capture failed during the final check, so completed Phase 8 visual acceptance is not claimed.

## Phase 8 — Windows agent, fluid kinetics & the sentient swarm (2026-10-11)

- **Objective 1 — Native Windows "do my work" engine (`bridge/`).** A hardened
  loopback daemon (`bridge/windowsBridge.js`) replacing the removed macOS bridge.
  `/screen-context` (UI Automation snapshot of the focused window),
  `/diagnostics` (CPU/GPU/memory + processes via `Get-CimInstance`/WMI),
  `/app/launch` and `/app/window` (launch/focus/minimize/restore/maximize),
  `/research` (headless Playwright background fetch), and `/task` (an agentic
  loop that can only chain the allowlisted verbs, ≤12 steps). Safety is a frozen
  core (`bridge/safety.js`, `node --test`): binds to 127.0.0.1 only; token +
  origin + loopback-Host checks; `execFile` with explicit argument arrays (no
  shell); an allowlist of named verbs (no raw-command endpoint); and an
  immutable destructive blacklist (format/registry-delete/recursive
  system-path-removal/boot-config/shadow-copy/power-state). The browser talks to
  it from System → "Connect this PC". **Scope note:** screen *reading* and
  window focus are implemented; blind keystroke/value injection into arbitrary
  third-party windows is deliberately stubbed (the blacklist cannot constrain
  "type anything into whatever is focused"), with the UIA control tree + focus
  hooks left in place for a later per-app, user-confirmed typing adapter.
- **Objective 2 — Advanced kinetic gestures.** Tension/elastic card bending via
  a vertex-shader bow+stretch toward the fingertip (`cardBend.ts`, on a
  tessellated card face); velocity flick that flings a card to a dimmed outer
  orbit ring with recall (`flick.ts`, hand-velocity from the gesture engine);
  two-handed spatial sculpting (`BimanualSculpt`): cup inward → data-convergence
  3D prism, cup outward → depth-expansion (orbit scales, focused card unpacks
  sub-panels). Keyboard: P prism, E expand, R recall. All pure detectors tested.
- **Objective 3 — Neural swarm & ferrofluid humanoid.** Real GPGPU FBO
  ping-pong (`ferrofluid.ts`, `GPUComputationRenderer`) drives a per-particle
  displacement field (magnetic fluid in zero-g), sampled in the embodiment
  shader; FFT bands modulate surface displacement (cymatic neck/jaw ripple);
  real-time webcam gaze via MediaPipe FaceLandmarker (`gaze.ts`,
  `useGazeTracking.ts`) drives the neck and optical-flare brightness to hold eye
  contact, with pointer fallback.
- **Objective 4 — The voice of NEXUS.** A bold/brave/authoritative commander
  persona shared across Grok/Gemini/Ollama (`persona.ts`). Premium TTS via
  ElevenLabs (`/api/tts`, deep authoritative default voice) routed through a Web
  Audio cinematic graph (`audio.ts`): sub-bass lift, spatial reverb + HRTF
  panner for in-room presence, and the FFT analyser that drives the face.
  `CinematicSpeaker` falls back to browser speech when no key is set.
- **Objective 5 — Adaptive kinetic environment.** Mic-reactive fog density and
  dust drift (`useAmbient.ts`); dynamic floor caustics with refractive
  dispersion and soft shadow blooms tracking the panels (`FloorCaustics.tsx`);
  system-load thermal LUTs that blend the grade from cobalt toward violet/cyan
  while the Windows bridge processes a task (`environment.ts` + `WorldGrade`).

Validated 2026-10-11: `npm run typecheck` clean, `npm test` 54/54, `npm run
build` clean (adds `/api/tts`), `node --test` in `bridge/` 8/8. Browser-verified
(Playwright + SwiftShader): orbit renders, System panel + Windows-agent connect
UI render, Human transform begins, zero page errors. Not verifiable in the
cloud container: the Windows bridge itself (runs on the user's PC), physical
webcam gaze, microphone reactivity, premium-voice playback, and sustained GPU
performance.

## Verification — 2026-10-12

Local AI setup completed: Ollama installed on Windows and `qwen3:1.7b` downloaded and checksum-verified. NEXUS restarted with `AI_PROVIDER=ollama`; `/api/ai/status` reports configured. API boundary checks and a real streamed request through `/api/ai` passed (text plus completion event). No cloud API key is needed for this provider. This verifies connectivity, not sustained response quality or rendering performance during longer inference. The repository setup now defaults to Ollama; local credentials remain ignored.

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
