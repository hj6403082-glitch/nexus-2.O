# Zeno on Windows: always-on daemon, wake word, shell integration

**Status:** approved 2026-10-27. Building now. Builds on PR #21 (cross-platform OS integration), which is green on Ubuntu and Windows.

**Locked decisions (Boss, 2026-10-27):**
1. **Daemon privilege — standard user, never admin.** The background daemon runs under the normal user account. Elevation is per-command, via a Windows UAC prompt at the moment a command needs it, never a blanket-admin service. This keeps the Phase 3 safety net: Zeno can only touch what the user can, and the approval gate sits on top of that.
2. **Microphone — on by default.** The wake-word listener starts with the daemon and runs continuously on its own thread. It can be turned off with `ZENO_WAKEWORD=false`.

**One deliberate narrowing of request 3 (per-command elevation).** A generic "run any command as Administrator" tool (`Start-Process -Verb RunAs` on arbitrary text) is an escape hatch *out* of the whole sandbox: an elevated child runs outside Constrained Language Mode, outside the policy whitelist, as admin. Wiring that behind an agent — one that a voice wake word can reach — would remove exactly the safety net decision 1 says to keep. So `run_powershell` stays non-elevated and policy-checked. When a specific admin task is genuinely needed, the right design is a narrow, named, separately-approved elevated command with its own allowlist, not a general RunAs. Flagged to Boss.

This plan covers four pieces that run at once without blocking Zeno's async core: an invisible logon daemon, a wake-word listener, an approved-command PowerShell tool, and an Explorer right-click entry. The point throughout is that the parts that can change the machine stay behind the approval gate Phase 3 already built, and the always-on parts (microphone, auto-start) are explicit and easy to turn off.

---

## One decision I need from you first: privilege level

Everything in Phase 3 was deliberately built to run **as you, never elevated**. The PowerShell policy, the protected-path checks, Constrained Language Mode — those are defence in depth, but the real safety boundary is that Zeno can only touch what your own account can touch. Running the daemon as Administrator with `HighestPrivileges` removes that boundary: a mistake, a bad model step, or a malicious instruction smuggled in through a web page or a file then has the run of the whole machine, and the approval prompt is the only thing left between it and the OS.

My recommendation as architect: **run at your normal user level (the Phase 3 default), and elevate a single command only when it genuinely needs it (UAC prompt at that moment).** You keep "total control" for the things that need it, but the always-on background process is not itself admin. This is how real assistants and most well-behaved services do it.

I'll write the blueprint for the default (non-elevated daemon, per-command elevation). If you want the whole daemon elevated instead, say so and I'll adjust Task Scheduler to `HighestPrivileges` and note the trade-off in the file. Either way the HITL gate below is mandatory and unchanged.

Open question for you:
- **Privilege:** per-command elevation (recommended) · whole daemon as admin
- **Wake word always listening:** on by default · off until you enable it in `.env`

---

## 1. The daemon (invisible, starts at logon)

`brain/daemons/install_zeno_windows.ps1` — an extension of the existing `windows_setup.ps1`, not a replacement.

- Registers a Scheduled Task **Zeno** that runs at your logon.
- Runs `brain\.venv\Scripts\pythonw.exe -m zeno serve`. `pythonw.exe` has no console, so no window and no stdout — which is also why the logging rule below matters.
- Runs as you, `LogonType Interactive`. `RunLevel` is `Limited` (default) or `Highest` (if you pick whole-daemon admin above).
- Restarts on failure, every minute, and keeps running. `-Now` starts it immediately; `-Remove` stops and unregisters it.
- Already the case from Phase 3, carried forward: toast identity under `HKCU\...\Zeno.Brain`, logs to `brain\data\logs\zeno.log`.

**Absolute-silence constraint.** When `sys.stderr` is `None` (what `pythonw` gives), Zeno already routes logging to a rotating file and passes `log_config=None` to uvicorn (added in Phase 3, `zeno/__main__.py`). No code path may `print()` unconditionally. I'll add a test that boots with `stderr=None` and asserts nothing is written to a real stdout, and that every log line reaches the file.

## 2. The wake-word listener (own thread, never blocks the loop)

`brain/zeno/senses/audio_listener.py`.

- `openwakeword` + `pyaudio`, both new optional dependencies, Windows-gated in `requirements.txt` the way winrt already is. The model file `hey_zeno.onnx` is downloaded on demand (like the other Phase 2 models), never committed.
- Runs on a plain `threading.Thread`, not in the event loop. It reads fixed-size audio frames, scores each with the model, and does nothing else.
- **The thread boundary is one call.** On a detection over the confidence threshold the thread calls `loop.call_soon_threadsafe(bus.publish, WakeWordDetected(...))` and returns to listening. It never touches the EventBus, Chroma, or any async object directly — `call_soon_threadsafe` is the only safe bridge from a foreign thread into asyncio, and it is non-blocking. The loop reference is captured at startup via `asyncio.get_running_loop()`.
- Threshold is config (`ZENO_WAKEWORD_CONFIDENCE`, default 0.6), with a short refractory period so one word fires one event.
- Shutdown: the daemon sets a `threading.Event`; the thread checks it each frame, closes the PyAudio stream, and joins with a timeout. A stuck read can't hang the loop because it's on its own thread, and the loop never awaits the thread.
- **Off switch.** The listener only starts when enabled (`ZENO_WAKEWORD=true`), and when the mic is unavailable it logs one line and the rest of Zeno runs normally. An always-on microphone is a real privacy choice, so it's opt-in unless you say otherwise above.

Tests mock the PyAudio stream (a fake that yields canned frames) and the model (a fake scorer), assert the event lands on the bus via the threadsafe call, assert a low score fires nothing, and assert clean shutdown. No real microphone is touched in tests.

## 3. `powershell_execute` — total control, behind the gate

This is the existing Phase 3 `run_powershell` tool, which already does exactly what's asked: it is `MUTATING`, it parses the command with PowerShell's own parser, a whitelist policy refuses destructive and out-of-scope commands outright, and an approved command runs with stdout **and** stderr captured and fed back to the ReAct loop so Zeno can read its own errors. I'll:

- Confirm the HITL path fires the approval event for every mutating command (it does today via the tool's `Risk.MUTATING` + precheck), and add a test that a mutating command reaches the approval gate and does **not** run on denial.
- Keep the policy's hard refusals (protected paths, registry hives, Defender changes, recursive force-deletes) as a layer *below* approval: those are refused before the prompt, so a careless "yes" can't run them. This matters much more if you choose whole-daemon admin.
- If you pick per-command elevation, add an explicit, separately-approved path for a command that needs admin (a distinct, louder approval than an ordinary mutating command), rather than the whole daemon being elevated.

No new blind-execution path is introduced. "Total OS control" means the approval gate can authorise a lot, not that anything runs unprompted.

## 4. "Send to Zeno" in the right-click menu

`brain/zeno/hostos/windows/shell_integration.py` (a `winreg` script, with `--install` / `--remove`).

- Writes keys under **`HKCU\Software\Classes`** (per-user, no admin needed) for files and folders: a `shell\ZenoSendTo` entry whose command hands the selected path to a small client.
- Clicking it runs a short-lived `pythonw` client that connects to Zeno's existing WebSocket on `127.0.0.1` (loopback only, with the existing device token) and sends a `context_payload` with the path. It does not open a window.
- Zeno receives it as an event on the bus like any other input. The server stays bound to `127.0.0.1` only — no new listener, no new port.
- Tests mock `winreg` (a fake registry dict) and assert the right keys are written and fully removed, and that the payload is well-formed. No real registry is touched in tests.

---

## Threading & event-flow summary

```
 logon ──> Task Scheduler ──> pythonw -m zeno serve   (no window; logs to file)
                                      │
                                      ├── asyncio loop ── EventBus ── ReAct agent ── tools
                                      │        ▲                                   (run_powershell: parse → policy → APPROVAL → run)
                                      │        │ call_soon_threadsafe(publish, WakeWordDetected)
                                      └── audio thread (pyaudio + openwakeword)   ← the only thread→loop bridge
                                      
 Explorer right-click "Send to Zeno" ──> short-lived client ──> ws://127.0.0.1 (token) ──> EventBus
```

Invariants:
- The audio thread only ever calls `loop.call_soon_threadsafe`; it owns no async state.
- Nothing mutating runs without an approval event; hard-refused commands never reach the prompt.
- The windowless daemon writes no stdout; all logs go to `zeno_daemon.log` / `zeno.log`.
- Everything stays on `127.0.0.1`; shell integration and wake word add no network surface.

## Build order (Step 3, after approval)

1. `requirements.txt`: `openwakeword`, `pyaudio`, `numpy` (already present), Windows-gated.
2. `audio_listener.py` + tests (mocked stream/model).
3. `shell_integration.py` + tests (mocked winreg).
4. `install_zeno_windows.ps1` + its setup test.
5. Approval-gate test for `powershell_execute`; confirm elevation path per your choice.
6. Gate: `pytest` and `mypy --strict` clean on Ubuntu and Windows (the PR #21 CI matrix) before anything is called done.

All of this ships in PR #21's branch unless you'd rather a new PR.
