# NEXUS Windows bridge

A small, hardened daemon that lets the NEXUS web app act as an autonomous
**Windows** agent on the machine it runs on — reading the focused window with UI
Automation, reporting CPU/GPU diagnostics, launching and arranging apps, and
running headless background research. It is the Windows replacement for the
removed macOS desktop bridge.

It runs **only on your own PC**, only on **loopback**, and every privileged
action is funnelled through an immutable safety policy.

## Run

```sh
cd bridge
node windowsBridge.js
```

It prints a URL (`http://127.0.0.1:4517`) and a one-time **token**. Paste the
token into NEXUS under **System → Connect this PC**. For headless research,
also run `npm install` here once (pulls in Playwright).

## Why it is safe

* **Loopback only.** The server binds to `127.0.0.1`; it never listens on a LAN
  or public address, so nothing off this machine can reach it.
* **Token + origin + Host checks.** Requests must carry the per-launch bearer
  token, come from the local NEXUS origin, and present a loopback `Host`
  (anti-DNS-rebinding).
* **No shell, ever.** Commands run via `execFile` with explicit argument arrays.
  There is no `cmd.exe /c "..."`, so there is nothing to inject into.
* **Allowlisted verbs only.** There is no "run this command" endpoint. The app
  asks for a named verb (`diagnostics`, `screen-context`, `app.launch`,
  `app.window`, `research`); each verb validates its own parameters and builds
  its own argument array.
* **Immutable destructive blacklist.** `safety.js` hard-blocks disk formatting,
  registry deletion, recursive system-path removal, boot-config edits,
  shadow-copy wipes, power-state changes and more — frozen at load, so no later
  code or request can widen it. Defence in depth behind the allowlist.

See `safety.js` for the policy and `safety.test.js` for the tests
(`node --test`).

## Endpoints

| Method + path        | Verb            | What it does                                            |
| -------------------- | --------------- | ------------------------------------------------------- |
| `GET  /health`       | —               | Liveness + the verb list (local, no token).             |
| `POST /screen-context` | `screen-context` | UIA snapshot of the focused window (process, title, control tree, text). |
| `POST /diagnostics`  | `diagnostics`   | CPU/GPU/memory + top processes via `Get-CimInstance`/WMI. |
| `POST /app/launch`   | `app.launch`    | Launch an installed app by name or absolute path.       |
| `POST /app/window`   | `app.window`    | `focus` / `minimize` / `restore` / `maximize` a running app. |
| `POST /research`     | `research`      | Headless Playwright fetch of a remote page's text + links. |
| `POST /task`         | —               | Agentic loop: an ordered list of the verbs above (≤ 12 steps). |

The agentic task loop can only chain the same allowlisted verbs, so it can never
perform an action a single call could not.

## "Reply to this email saying I agree"

The intended flow for a request like *"reply to this email saying I agree"*:

1. `POST /screen-context` — NEXUS inspects the focused window (e.g. the mail
   client), reading its control tree to find the compose/reply affordance and
   the message text.
2. NEXUS (in the web app) composes the reply text with the language model.
3. A follow-up verb focuses the target input and submits.

> **Note on input synthesis.** This build implements screen *reading* (UIA) and
> window focus/activation fully. It deliberately **stubs keystroke/value
> injection into arbitrary third-party windows**: blindly synthesising
> keystrokes and "send" clicks into whatever happens to be focused is the one
> capability where the safety blacklist cannot meaningfully constrain the
> outcome (the target field, and what "send" does, are entirely context
> dependent). The hook (`app.window` focus + the control-tree the UIA snapshot
> returns) is in place so a per-app, user-confirmed typing adapter can be added
> deliberately rather than as a blanket "type anywhere" primitive. This is
> called out in the Phase 8 PR so the choice is explicit.
