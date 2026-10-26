# Zeno Phase 3: Linux OS Integration

**Status:** approved by Boss 2026-10-26 with the defaults in section 9. Built; the code is the source of truth where details differ (noted inline).

Phase 3 makes Zeno a native administrator of the Linux machine it runs on:
- it starts with the OS as a systemd service;
- it reads system health, temperatures and processes;
- it runs commands, with your approval every time;
- it shows desktop notifications through D-Bus.

Everything here lands in the existing Pillar 4 tool registry (`zeno/agent/tools/`) and follows the rules the brain already has (section 1). Section 9 lists the choices this plan assumes; each has a default.

---

## 0. Where it fits

```
systemd --user ──starts──▶ python -m zeno serve ──sd_notify──▶ READY / WATCHDOG / STOPPING
                                  │
                       ZenoDaemon._boot()
                                  │
                ┌─────────────────┴──────────────────┐
           existing tools                 Phase 3 tools (Linux only, off until enabled)
                                          ├─ telemetry.py   READ_ONLY   psutil
                                          ├─ shell.py       PRIVILEGED  run_command
                                          └─ desktop.py     notify_desktop, service_status (D-Bus)
```

- **Linux only.** The new tools register only when `sys.platform == "linux"` and `ZENO_LINUX_TOOLS=true`. The Windows PC setup is unchanged.
- **Same flow as every other tool.** Calls go through the grammar, then Pydantic validation, then policy, then approval, then the audit log. The web app's approval card already shows MUTATING and PRIVILEGED calls; nothing changes there.

---

## 1. Rules carried over (unchanged)

- **No shell, ever.** `brain/CLAUDE.md` says never `shell=True` and never pass model-written text to a shell. `run_command` keeps this literally true (section 3).
- **Approval.** Anything that changes state needs your approval every time. PRIVILEGED tools never appear in runs Zeno starts on its own.
- **Audit.** Every call is written to `data/audit/agent.jsonl` before it runs. If the record can't be written, the call doesn't run.
- **Untrusted output.** Tool output is labelled as data, never instructions. Command output counts here too, because a file Zeno `cat`s could contain text written by someone else.
- **Off by default.** A fresh install behaves exactly like today.
- **Tests never touch the host.** Subprocesses, psutil and D-Bus are all behind injectable interfaces with fakes. The few real integration tests run only harmless commands, plus a private `dbus-daemon` that the test itself starts.

---

## 2. Telemetry tools (`zeno/agent/tools/telemetry.py`, READ_ONLY)

All of these read through `psutil` in a worker thread (`asyncio.to_thread`), so the event loop is never blocked. `psutil` is already pinned (7.2.2).

| Tool | Returns |
|---|---|
| `system_health()` | CPU % (sampled over 0.5 s), load average, memory and swap, each mounted disk's use, uptime, and battery if present |
| `system_temperatures()` | `psutil.sensors_temperatures()` and fans, flagging any sensor at or above its `high` / `critical` mark |
| `top_processes(sort_by, limit)` | The top N processes by `cpu` or `memory`. `limit` is 1 to 20. Shows pid, user, name, CPU %, RSS and status. No command lines by default, since those can contain secrets. |
| `process_info(pid)` | Details for one process: name, user, status, start time, threads, parent, memory, and its command line cut to 200 characters |

The existing `get_system_info` and `network_status` stay as they are. Phase 3 does not duplicate them.

---

## 3. `run_command` (`zeno/agent/tools/shell.py`)

### 3.1 How a command runs

1. **Arguments.** The model sends `command` (one line of at most 1,000 characters, no NUL), an optional `cwd` (must be inside an allowed folder, default `$HOME`) and an optional `timeout` (1 to 120 s, default 30).
2. **Parse.** `shlex.split(command)` produces an argument list (argv). There is **no shell**: the process starts with `asyncio.create_subprocess_exec(*argv)`.
   - Because there's no shell, shell syntax can't work (`|`, `;`, `&&`, `>`, `$( )`, backticks, `*`). The policy refuses it up front with a clear message, rather than letting it be passed through as literal text.
   - For a pipeline, Zeno runs the steps one at a time, or uses the program's own flags (for example `journalctl -n 50` instead of `| tail`).
3. **Policy check** (3.2). This is a pure function of the argument list. A refused command never reaches the approval card, never runs, and comes back to Zeno as an observation explaining why.
4. **Approval card.** It shows the command text exactly as it will be split (there is no shell to reinterpret it), the working folder and the timeout. The refusal check runs before this, through the tool's new `precheck` hook in the agent loop, so a refused command is answered with its reason and never reaches the card.
5. **Run.**
   - The process runs as Zeno's user, with `stdin` closed and a small environment (the same allowlist the script runner uses, so no brain secrets).
   - It starts in its own process group, so a timeout kills the program and everything it spawned.
6. **Result.** `stdout` and `stderr` are captured **separately**, each capped (default 4,000 characters), and returned together with the exit code:

   ```
   [run_command: exit 1 after 0.4 s]
   [stdout]
   ...
   [stderr]
   ls: cannot access '/nope': No such file or directory
   ```

   This goes back into the ReAct loop as the observation, so Zeno can read its own error, fix the command and try again. A timeout shows `[killed after 30 s]` and whatever output arrived first.

### 3.2 The policy: what is refused before approval

The check is deterministic: it works on the parsed argument list, so the result doesn't depend on how a command is spelled. For example, `rm -rf /`, `rm -fr /`, `rm -r -f /`, `rm --recursive --force /`, `rm -rf //`, `rm -rf /./` and `rm -rf -- /` are all the same command to the policy. Each rule is tested over every flag order and spelling (section 7).

1. **Shape.**
   - It must parse.
   - It may have at most 64 arguments, and no argument may contain a control character.
   - No shell operators or glob characters are allowed as tokens.
2. **The program.**
   - It must be a bare name found on `PATH` inside a trusted system folder: `/usr/bin`, `/bin`, `/usr/sbin`, `/sbin` or `/usr/local/bin`.
   - No `./tool` or `/tmp/x`, and no resolving to a file a user can write to.
3. **Programs that would run other code past the check are refused.**
   - Shells: `sh`, `bash`, `zsh`, `fish`, `dash`, `busybox`.
   - Interpreters: `python*`, `perl`, `ruby`, `node`, `php`, `lua`.
   - Wrappers: `env`, `xargs`, `nohup`, `setsid`, `timeout`, `watch`, `nice`, `stdbuf`, `chroot`, `nsenter`, `unshare`, `script`, `expect`.
   - Privilege tools: `sudo`, `su`, `doas`, `pkexec`, `run0`.
   - Argument flags that run code, such as `find -exec / -execdir / -ok / -delete`, `git -c core.*`, `tar --to-command / --use-compress-program`, and `rsync -e`.
   - Without these refusals, `bash -c "rm -rf /"` would slip past the rules.
4. **Catastrophic commands are refused outright**, even with your approval:
   - recursive `rm` on `/`, a top-level system folder (`/etc`, `/usr`, `/boot`, `/var`, `/home`, `/root`, `/bin`, `/lib*`, `/opt`, `/srv`, `/dev`, `/proc`, `/sys`) or your home folder itself, plus `--no-preserve-root`;
   - recursive `chmod` / `chown` / `chgrp` on those same folders, and `chmod 777` / `a+w` on them;
   - formatting and partitioning: `mkfs*`, `fdisk`, `sfdisk`, `parted`, `sgdisk`, `wipefs`, `blkdiscard`, `shred`;
   - `dd` with `of=/dev/...`; `cp`, `mv`, `tee` or `truncate` targeting `/dev/sd*`, `/dev/nvme*` or `/dev/mmcblk*`;
   - power and boot: `shutdown`, `reboot`, `poweroff`, `halt`, `init`, `telinit`, `kexec`, and `systemctl poweroff|reboot|halt|kexec|isolate|emergency|rescue`;
   - killing PID 1 or Zeno itself (`kill … 1`, `kill -1 …`, `pkill` / `killall` of `systemd`, `init` or `zeno`);
   - flushing the firewall (`iptables -F`, `nft flush ruleset`) and editing accounts (`userdel`, `passwd`, `chpasswd`, `visudo`, `usermod`);
   - `crontab -r`.
5. **Everything else goes to the approval card.** It is not run silently.

**What this does and doesn't guarantee.**
- **It does guarantee:** no command in the refused set can ever reach the approval card or run, whatever its spelling, flag order or quoting. This is proved by the tests in section 7.
- **It doesn't guarantee** that any other command is harmless. That is why every command still waits for your approval. A denylist is a seatbelt, not a judge.

### 3.3 Risk tier

`run_command` is **PRIVILEGED**. That means it needs your approval every time, like MUTATING. On top of that, a run Zeno starts on its own (a watcher, later) can't even name it. If you want watchers to suggest commands, they can notify you and you ask Zeno in chat. See decision 2.

### 3.4 What changes in the safety test

- `test_only_the_script_runner_starts_processes` will allow exactly two files: `tools/scripts.py` and `tools/shell.py`.
- A new check fails if `shell.py` calls anything except `create_subprocess_exec`, or passes `shell=`.

---

## 4. D-Bus (`zeno/desktop/dbus.py` + `zeno/agent/tools/desktop.py`)

**Library:** `dbus-fast`. It works natively with asyncio, is typed and maintained, has wheels and a pure-Python fallback, and needs no GLib or C toolchain. Home Assistant and bleak use it. See decision 3.

### Tools

| Tool | Bus | Risk | What it does |
|---|---|---|---|
| `notify_desktop(title, body, urgency)` | session | READ_ONLY | Calls `org.freedesktop.Notifications.Notify` with app name "Zeno". Title is at most 80 characters, body at most 400, urgency is `low`, `normal` or `critical`. It's rate-limited to 1 every 5 s and 30 an hour, so a loop can't flood the desktop. It counts as READ_ONLY because it can only show you text. |
| `service_status(name)` | system | READ_ONLY | Reads a unit's `ActiveState`, `SubState`, load state and the time it entered that state from `org.freedesktop.systemd1`. `name` must match `^[A-Za-z0-9@._-]{1,100}\.(service\|timer\|socket\|mount)$`. This is read-only D-Bus, no process. Starting or stopping units goes through `run_command` (`systemctl --user restart x`), so it still needs approval. |

### Behaviour

- **One connection per bus.** Each bus gets a single connection that is opened lazily and reconnects with backoff. If the session bus is missing (for example a headless server), `notify_desktop` replies "no desktop session"; it doesn't crash.
- **Phase 2 module B.** Once built, its watchers will use the same notifier through the `OwnerHub`, so an alert reaches both the web app and the desktop.

---

## 5. systemd: Zeno as a background service

### 5.1 Why a user service (decision 4)

Zeno runs as **your** user (`systemctl --user`), not as root, and not as a separate `zeno` account. The reasons:
- desktop notifications need your session bus;
- `run_command` should act with your permissions, which are exactly what you could do yourself;
- the brain's data stays in your home folder.

To start it at boot without logging in, run `loginctl enable-linger` once.

### 5.2 `brain/linux/zeno.service` (the file in the repo is the source of truth)

```ini
[Unit]
Description=Zeno brain (local AI assistant)
Documentation=file://%h/nexus-2.o/ZENO_LINUX_INTEGRATION.md
After=default.target
StartLimitIntervalSec=300
StartLimitBurst=5

[Service]
Type=notify
NotifyAccess=main
WorkingDirectory=%h/nexus-2.o/brain
ExecStart=%h/nexus-2.o/brain/.venv/bin/python -m zeno serve
Environment=PYTHONUNBUFFERED=1
Restart=on-failure
RestartSec=5
TimeoutStartSec=300
TimeoutStopSec=30
KillMode=mixed
WatchdogSec=60

# Hardening that works for user services (checked with: systemd-analyze --user security zeno)
NoNewPrivileges=yes
RestrictSUIDSGID=yes
LockPersonality=yes
RestrictRealtime=yes
PrivateTmp=yes
UMask=0077

[Install]
WantedBy=default.target
```

- **`Type=notify`.** The brain tells systemd it is `READY=1` only after every pillar has booted. A failed boot exits non-zero, and systemd restarts it at most 5 times in 5 minutes. The model can take a while to load, so the start timeout is 300 s.
- **`WatchdogSec=60`.** The brain sends `WATCHDOG=1` every 20 s from its event loop. If the loop freezes, systemd restarts Zeno.
- **`KillMode=mixed`.** Zeno gets SIGTERM first, so uvicorn finishes the lifespan cleanly (closing the device sockets, stopping the bus and freeing the model). Only leftover child processes are killed after that.
- **`NoNewPrivileges=yes`.** This also makes `sudo` impossible from anything Zeno runs, which matches the policy in 3.2.
- **Paths.** `%h` is your home folder. The install script writes the real repository path into the unit if the checkout isn't at `~/nexus-2.o`.

### 5.3 `sd_notify` without a dependency

`zeno/systemd.py` is about 30 lines. It writes `READY=1`, `STATUS=…`, `WATCHDOG=1` and `STOPPING=1` to `$NOTIFY_SOCKET`, a datagram socket, including Linux's abstract `@` addresses. When the variable isn't set (Windows, or a plain terminal), every call does nothing.

`ZenoDaemon` calls it at the following points:
- after boot;
- each watchdog tick;
- at shutdown.

### 5.4 `brain/linux/install-service.sh`

```
./linux/install-service.sh            # install + enable + start
./linux/install-service.sh --linger   # also start at boot without logging in
./linux/install-service.sh --remove   # stop, disable, delete the unit
```

1. It checks for `.venv` and `.env`.
2. It renders the unit with the real paths into `~/.config/systemd/user/zeno.service`.
3. It runs `systemd-analyze --user verify`, then `daemon-reload` and `enable --now`.

Logs go to the journal: `journalctl --user -u zeno -f`.

---

## 6. Configuration (`zeno/config.py`, `.env.example`)

| Setting | Default | Meaning |
|---|---|---|
| `ZENO_LINUX_TOOLS` | `false` | Turns on telemetry, `notify_desktop` and `service_status` (Linux only) |
| `ZENO_RUN_COMMAND` | `false` | Turns on `run_command`, separately, because it's the powerful one |
| `ZENO_COMMAND_ROOTS` | `["~"]` | Folders `cwd` may be inside |
| `ZENO_COMMAND_TIMEOUT` | `30` | Default timeout; at most 120 |
| `ZENO_COMMAND_MAX_OUTPUT` | `4000` | Cap for each of stdout and stderr |
| `ZENO_NOTIFY_PER_HOUR` | `30` | Desktop notification budget |

---

## 7. Tests first (TDD), all safe on any machine

| Area | Tests (written before the code) | How the host is protected |
|---|---|---|
| Policy | Each refused family, in every flag order, combined (`-rf`) and split (`-r -f`), long (`--recursive`) or after `--`, with path variants (`//`, `/./`, `/etc/../`, a trailing `/`). A property test generates thousands of spellings with `hypothesis` (dev only) and asserts each is refused. Safe commands pass. Shell syntax and wrapper programs are refused. | It's a pure function and nothing runs |
| `run_command` | A refused command never reaches the approval card or the runner. An approved command runs exactly the argv shown. stdout and stderr come back separately with the exit code. Output caps hold. A timeout kills the whole process group. The environment carries no brain secrets. `cwd` outside the roots is refused. PRIVILEGED means it's absent from the proactive registry. | A fake runner records argv. Two real runs use `/usr/bin/true` and `/usr/bin/printf`, plus `sleep` to test the timeout. |
| Telemetry | Output format; missing sensors or battery; a process vanishing mid-read; `limit` bounds | A fake `psutil` module is injected |
| D-Bus | The notify payload and app name; urgency mapping; rate limit; "no desktop session"; `service_status` name validation and state text | A fake bus. An integration test also starts its own private `dbus-daemon --session` with a tiny fake notification server, and skips if `dbus-daemon` isn't installed. |
| systemd | `sd_notify` sends the right datagrams to a socket made in `tmp_path`; it does nothing without `NOTIFY_SOCKET`; the daemon sends READY only after boot and STOPPING on shutdown; the unit file passes `systemd-analyze verify` (skipped where that isn't available) | A local datagram socket stands in for systemd |
| Grammar | The tiny-GGUF full-grammar compile test includes every new tool | — |

**Gate before the PR:** `pytest` (whole suite under the 30 s per-test limit), `ruff check`, `ruff format --check` and `mypy --strict`, all clean.

---

## 8. Dependencies and build order

- **Dependencies.**
  - `requirements.txt` adds `dbus-fast` (pinned at Step 2). It's installed on Linux only, through the `; sys_platform == "linux"` marker, so Windows installs stay the same.
  - `psutil` is already there.
  - `requirements-dev.txt` adds `hypothesis`.
- **Build order (one draft PR):**
  1. `sd_notify` plus the service files;
  2. telemetry;
  3. the policy, then `run_command`;
  4. D-Bus;
  5. wiring and docs (`brain/CLAUDE.md`, `.env.example`).
- **Relation to Phase 2.** PR #20 (Phase 2 module A) is still in your review. Phase 3 builds on it: it uses its PRIVILEGED tier. So the Phase 3 PR opens after #20 merges. Phase 2 modules B to D (watchers, vision, voice) resume after Phase 3 unless you'd rather interleave them.

---

## 9. Decisions for Boss (defaults this plan assumes)

1. **How commands run: as an argument list with no shell (default)**, versus `bash -c`. Static checks on real shell text can't be made reliable (aliases, expansions, `eval`, quoting), so "reject before approval" only holds when there's no shell. The cost is no pipes or redirects in v1. Piping that splits on `|` and checks each step can come later.
2. **`run_command` risk: PRIVILEGED (default)**, versus MUTATING. Both need your approval every time; PRIVILEGED also keeps it away from runs Zeno starts on its own.
3. **D-Bus library: `dbus-fast` (default).**
   - `dbus-python` needs `libdbus-1-dev` and a C build, and it's synchronous.
   - `pydbus` hasn't been maintained since 2018 and needs PyGObject.
4. **systemd: a user service with optional linger (default)**, versus a system service under a dedicated `zeno` account. The system service would isolate Zeno more, but desktop notifications would stop working and Zeno couldn't manage your own things.
5. **`sudo`: blocked (default).** Zeno administers as you. Root-level changes stay with you for now. A narrow, allowlisted `sudo -n` for specific `systemctl` units could come later if you want it.
6. **Read-only commands still ask (default).** Every `run_command` waits for approval, even `ls`. Reading the system without approval is what the telemetry tools are for. A later option could auto-allow a short list of read-only commands.
