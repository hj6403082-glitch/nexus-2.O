# NEXUS

A local spatial computing application built progressively from the seven-phase brief. **Current milestone: spatial foundation, Phase 2 AI implementation, and an early Phase 7 human-form prototype.** Later-phase integrations are explicitly marked as not connected; no fabricated live data is shown.

Use the **Human / Spatial** switch to try the reversible particle transformation. The prototype includes a GPU-baked bust, captured card colors, pointer-driven head motion and a browser-speech mouth signal. Its visual appearance and GPU compatibility still need runtime validation. Hand presentation and the complete Phase 7 choreography remain outstanding.

## Run

Node 22+ is recommended. From this directory:

```sh
npm install
node scripts/setup-tracking.mjs
npm run dev
```

Open http://127.0.0.1:3000. Tracking needs localhost or HTTPS and camera permission. The setup script copies the pinned MediaPipe WASM runtime and downloads Google's hand-landmarker model into `public/`; inference then runs on-device, without uploading camera frames. Model and runtime licenses remain those of their respective publishers.

## AI setup

Copy `.env.example` to `.env.local` and set `GEMINI_API_KEY`. The key stays on the server; do not use `NEXT_PUBLIC_` or paste it into the assistant. Restart the dev server after changing configuration. `GEMINI_MODEL` defaults to `gemini-3.8-flash`, and can be changed to a model available to your Google AI account.

Use **Ask NEXUS** or open the AI module. Direct commands such as “open system”, “rotate left”, “show calendar”, “freeze”, and “show controls” run immediately without a model call. General questions use Gemini's streaming API. The current module and bounded recent conversation are sent with the question; live System metrics are included when that module is focused. Other modules are clearly identified as not connected. No current news or market data is fabricated.

Voice and microphone access are separately opt-in. Recognition uses the browser's SpeechRecognition implementation, which may send audio to the browser vendor. The microphone initially listens for a question; after the active window ends, say “Nexus” to wake again. Circle detection opens the AI surface but never grants microphone permission. Use headphones to avoid speaker feedback triggering interruption. TTS uses the best available installed/browser voice, begins at completed sentence boundaries, and stops on interruption. Native speech synthesis cannot be routed through a Web Audio panner; studio TTS and true spatial voice remain follow-up work, and voice quality varies by browser/OS. The shared speech envelope supports later embodied rendering.

Conversation history is memory-only for this tab. Clear it using the trash control. Closing the assistant or pressing Escape stops voice input/output; hiding the tab also releases voice and camera activity. A persistent “MIC ON” indicator remains visible while listening. Network requests are abortable, have a 60-second server timeout, and are limited to bounded same-origin loopback requests with at most two concurrent generations.

```sh
npm run typecheck
npm test
npm run build
```

## Controls

- Enable hand tracking explicitly. Swipe an open hand to rotate, pinch to grab, release to return, and pull/push while pinching to open/close. Hold an open palm still to freeze ambient motion. Circle recognition wakes the AI interface.
- Arrow keys rotate. Enter opens. Escape returns. Click any card to select; click the centered card to open. Bottom navigation works with touch.
- Ctrl/⌘ K opens the searchable module launcher even with the HUD hidden. H toggles the HUD; ? opens the input guide.
- LOCKED is the default. DRIFT enables subtle motion with a spring ramp. Sound is opt-in and stops when the page is hidden.
- WebGL failures fall back to the accessible card interface. Camera denial, hardware absence, and model failures show recovery instructions.

## Architecture

- `src/rendering`: React Three Fiber scene, independent card transforms, atmospheric depth, grid and bloom, adaptive rendering quality.
- `src/gestures`: MediaPipe lifecycle and pure gesture recognition, hysteresis, cooldowns and tracking-loss cleanup.
- `src/animations`: shared motion vocabulary and deterministic spring integration.
- `src/stores`: low-frequency Zustand state plus a separate hot input signal.
- `src/components`: spatial card faces, HUD, module panels, accessible modal launcher and fallbacks.
- `src/hooks`: keyboard input and opt-in audio graph.
- `src/ai`: command matching/validation, streaming protocol, context limits, interruptible voice and assistant orchestration.
- `src/app/api/ai`: local-only Gemini streaming endpoint and connection status; secrets never enter the client bundle.

The later Phase 6 requirements supersede throwing physics: released cards use orbit springs; there are no Rapier bodies or throwing registries. Ambient motion starts off. GSAP, Lenis and additional spring libraries are not included merely to duplicate the animation primitives; add them only when a later phase needs them.

## Progressive roadmap

1. Spatial foundation, module shells, gesture control, fallback input, ambient audio.
2. Server-side Gemini streaming, interruption-aware browser speech, wake routing, command engine, conversation memory and module context implemented. Live Gemini and physical voice testing require a server-side key and microphone. Studio/spatial voice and richer particle text remain outstanding.
3. Real knowledge integrations: account-linked Instagram, calendar and music; market, sports, weather and source-linked news providers; project storage. Requires account access and provider configuration.
4. Cinematic worlds, transitions, two-hand interactions, reactive surfaces and richer lighting.
5. Opt-in macOS-only desktop bridge with enum verbs, installed-app resolution, origin/loopback checks and permission translation. Windows must return 501 for desktop capabilities. No shutdown, restart or deletion.
6. Master-clock targeting/approach/settle, world color grades, gold/warning isolation and measured stillness. Motion defaults and return-to-slot behavior already follow this phase.
7. Reversible single-buffer human transformation, async baked bust/hand surfaces, voice-driven mouth and anchored information panels.

## Verification limits

Automated tests cover gesture edges, cooldowns, relative depth, tracking loss, exact spring stillness, command allowlists, split UTF-8 streams, request size limits and loopback/origin checks. Browser checks cover desktop/mobile layout, direct card opening, orbit rotation, module search, System diagnostics and hidden-HUD launcher access. No live Gemini response is claimed without a configured key. Real camera accuracy, local audio output and sustained GPU performance require testing on the user's actual webcam and graphics hardware; the 60 FPS target is not a hardware-independent guarantee.
