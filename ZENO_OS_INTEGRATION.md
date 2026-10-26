# Zeno Phase 3: Cross-Platform OS Integration (Windows + Linux)

**Status:** draft. Waiting for Boss's approval. Section 10 lists the decisions this plan assumes; each one has a default.

Phase 3 makes Zeno a native administrator of the machine it runs on, whether that machine is Windows or Linux, from one codebase. The Linux half is already built (draft PR #21, design in `ZENO_LINUX_INTEGRATION.md`). This plan:
- adds the Windows half;
- adds an OS loader that picks the right toolset at boot;
- reorganises the Linux code so the two halves are strictly isolated.

It does not rewrite the Linux design, so the Linux details stay in that document.

---

## 0. Where it fits

```
                         ZenoDaemon._boot()
                                │
                 os_loader.load_os_tools(settings)        platform.system()
                                │
        ┌───────────────────────┼─────────────────────────────┐
     "Linux"                "Windows"                  anything else
  tools/os_linux.py      tools/os_windows.py          (macOS etc.)
  ├ run_command          ├ run_powershell             telemetry only,
  ├ notify_desktop       ├ notify_desktop             plus a log warning
  └ service_status       └ service_status
        └──────────── shared: tools/telemetry.py (psutil, READ_ONLY) ─────┘
                                │
                     Pillar 4 ToolRegistry (unchanged)
```

- **One loader, one decision.** `load_os_tools` calls `platform.system()` once and imports only that OS's module. The other OS's code is never imported, and neither are its libraries.
- **Same tool names where the job is the same.** `notify_desktop` and `service_status` keep the same names and argument schemas on both OSes, so prompts, examples and the web app's approval card don't care which OS is running. Only the execution tool differs (`run_command` or `run_powershell`), because the model must write a different language for each.
- **Same flow as every other tool.** Each call goes through the grammar, then Pydantic validation, then the precheck (the PR #21 hook that refuses a call before approval is asked), then approval, then the audit log.

---

## 1. Rules carried over

All the rules from `ZENO_LINUX_INTEGRATION.md` section 1 still apply:
- approval every time for anything that changes state;
- audit before run;
- tool output is labelled as data;
- everything is off by default;
- servers bind 127.0.0.1 only;
- no LangChain, LlamaIndex or Ollama.

One rule needs care on Windows: `brain/CLAUDE.md` says to never pass model-written text to a shell. On Linux, `run_command` avoids that by running argv with no shell. On Windows, PowerShell *is* the shell, so `run_powershell` meets the rule's intent a different way:
- PowerShell's own parser turns the text into a syntax tree;
- a fixed policy accepts only a small, static subset of the language;
- the command then runs in Constrained Language Mode (section 4).

`brain/CLAUDE.md` gets one line documenting that exception.

---

## 2. File layout (strict isolation)

```
brain/zeno/agent/tools/
  telemetry.py         shared, psutil (exists; small Windows additions, section 3)
  os_loader.py         NEW  platform.system() → toolset
  os_linux.py          NEW  the Linux toolset: run_command, notify_desktop, service_status
  os_windows.py        NEW  the Windows toolset: run_powershell, notify_desktop, service_status
brain/zeno/hostos/     NEW  the OS back ends the toolsets use
  process.py           shared runner: capture stdout/stderr, cap, timeout, output format
  linux/
    command_policy.py  moved from tools/command_policy.py (unchanged)
    dbus.py            moved from zeno/desktop/dbus.py
    systemd.py         moved from zeno/systemd.py
  windows/
    ps_policy.py       NEW  pure policy over the PowerShell syntax tree
    ps_parse.ps1       NEW  fixed helper: parse only, print the tree as JSON
    toast.py           NEW  WinRT toast back end
brain/daemons/         NEW  (replaces brain/linux/)
  zeno.service         moved from brain/linux/
  install-service.sh   moved from brain/linux/
  windows_setup.ps1    NEW
```

- `tools/shell.py` and `tools/desktop.py` from PR #21 are split. Their OS-neutral parts (argument models, rate limiter, output format) go into `hostos/process.py` and a small shared section of `os_loader.py`. Their Linux parts go into `os_linux.py`.
- **Isolation is enforced by tests, not just convention:**
  - an AST test checks that nothing under `hostos/linux` or `os_linux.py` imports from `hostos/windows` or `os_windows.py`, and the reverse;
  - a subprocess test imports `os_linux` and checks that no Windows module or `winrt` landed in `sys.modules`, and the reverse for `os_windows` and `dbus_fast`.
- `zeno/desktop/` disappears. `daemon.py`'s `_linux_tools()` becomes one call to `load_os_tools()`.

Because PR #21 has not merged, this work goes into PR #21 itself. The moves then never touch the base branch twice. Decision 1 in section 10 covers this.

---

## 3. Telemetry (shared, READ_ONLY)

`telemetry.py` already works through psutil and is injectable for tests. On Windows:
- `system_temperatures` already returns "not available on this platform", because psutil has no sensors there. The plan keeps it rather than adding WMI's `MSAcpi_ThermalZoneTemperature`, which needs admin and is often wrong.
- `system_health` reports disks by drive letter rather than mount point. That is one branch on `psutil.disk_partitions()` (`opts` contains `cdrom` or `fstype == ""` → skip).
- `process_info` adds the Windows owner and service name when psutil gives them.

Tests reuse the fake psutil and add a Windows-shaped one.

---

## 4. `run_powershell` (Windows, `os_windows.py`)

### 4.1 How a command runs

1. **Validate.** `PowerShellArgs` has these fields:
   - `command`: one line, at most 1000 characters;
   - `cwd`: must resolve inside the allowed roots, which default to the user's profile, exactly like `run_command`;
   - `timeout`: 1 to 120 s.
2. **Parse (no execution).**
   - The command text is sent on stdin to a fixed helper, `powershell.exe -NoProfile -NonInteractive -File ps_parse.ps1`.
   - The helper calls `[System.Management.Automation.Language.Parser]::ParseInput` and prints the syntax tree as JSON: pipelines, commands, parameters, arguments and every node type it meets.
   - Parsing never runs the code, and a parse error means the call is refused.
   - Using PowerShell's real parser instead of a homemade lexer is the core safety decision. PowerShell has backtick escapes, splatting, `&` and `.` invocation, sub-expressions and `-EncodedCommand`, so a regex-level check would be bypassable.
3. **Policy (pure Python, `ps_policy.check(tree, ctx)`).** Runs as the `Tool.precheck` from PR #21, so a refusal happens before the approval card exists. It is audited as `refused`, the reason is fed back to Zeno, and if the check itself fails the call is refused (fail closed). Section 4.2 lists the rules.
4. **Approve.** The approval card shows the exact command text and the folder.
5. **Run.**
   - Command line: `powershell.exe -NoLogo -NoProfile -NonInteractive -ExecutionPolicy Restricted -EncodedCommand <base64>`. The flags mean the following:

     | Flag | Effect |
     |---|---|
     | `-NoLogo` | No startup banner in the output. |
     | `-NoProfile` | No profile scripts run. |
     | `-NonInteractive` | Nothing can wait for input. |
     | `-ExecutionPolicy Restricted` | No `.ps1` file can be loaded, which blocks write-a-script-then-run-it indirection. |
     | `-EncodedCommand <base64>` | Avoids Windows argv quoting problems. |

   - The encoded script is a fixed preamble followed by the approved text. The preamble sets `[Console]::OutputEncoding` to UTF-8 and switches `$ExecutionContext.SessionState.LanguageMode` to `ConstrainedLanguage`. That blocks .NET method calls, `Add-Type` and COM for the rest of the session, as a second wall behind the policy.
   - The process is created with `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`, with a small environment (profile, temp, `SystemRoot`, a fixed `PATH` of the System32 and PowerShell folders), and stdin closed.
   - `pwsh.exe` (PowerShell 7) is used when it is installed in Program Files. Otherwise the built-in Windows PowerShell 5.1 is used. Both have the same parser API.
6. **Observe.** The shared runner in `hostos/process.py` (moved from PR #21) does the following:
   - captures stdout and stderr separately;
   - caps each to `max_output`;
   - on timeout, kills the whole process tree with `psutil.Process(pid).children(recursive=True)` (Windows has no process groups to signal);
   - returns the same observation format as Linux:
     ```
     [run_powershell: exit N after X.X s]
     [stdout]
     …
     [stderr]
     …
     ```
   PowerShell's error stream ends up in stderr, so Zeno sees a failed cmdlet's error text and can fix its next attempt.

### 4.2 The policy: what is refused before approval

**Structural rules.** Every node in the tree must be one of a short allowed list:
- pipelines;
- commands with a **static name** (no `& $x`, no `. script`, no variables as command names);
- constant strings and numbers, including expandable strings that contain no `$( )`;
- parameters;
- arrays of those;
- script blocks, only as the argument of `Where-Object`, `ForEach-Object`, `Sort-Object`, `Select-Object`, `Group-Object` or `Measure-Object`. Their contents are checked recursively with the same rules, plus access to `$_` and `$PSItem` properties and comparison operators, but no method calls.

Refused node types include the following:
- `InvokeMemberExpressionAst`, i.e. `[IO.File]::Delete(...)` and `.Kill()`;
- sub-expressions `$( )`;
- assignments;
- redirections to files (`>`, `>>`);
- `;` and newlines (one pipeline only);
- `&&`, `||` and `&` background jobs;
- `-EncodedCommand` anywhere;
- type literals other than in parameters.

**Commands that run other code (refused by name).** The name is resolved through PowerShell's built-in alias table, which `ps_parse.ps1` also emits, so `iex`, `icm`, `saps`, `start` and the rest are caught:
- `Invoke-Expression`, `Invoke-Command`, `Start-Process`, `Start-Job`, `Start-ThreadJob`;
- `Add-Type`, `New-Object -ComObject`, `Invoke-WmiMethod`, `Invoke-CimMethod`;
- `Register-ScheduledTask`, `New-Service`, `Set-ExecutionPolicy`, `Import-Module`, `Install-Module`;
- the native runners: `cmd`, `powershell`, `pwsh`, `wscript`, `cscript`, `mshta`, `rundll32`, `regsvr32`, `msiexec`, `wsl`, `bash`, `python`, `py`, `node`.

Native programs are checked on the bare name and on any path to them.

**Catastrophic rules.** These mirror the Linux list, with the Windows paths:

| Area | Refused |
|---|---|
| Recursive delete | `Remove-Item` and its aliases `rm`, `del`, `erase`, `rd`, `rmdir`, `ri`, with `-Recurse` (any unambiguous prefix, e.g. `-r`, `-Rec`), on a protected path or on a wildcard whose parent is protected (`C:\*`). Also `cmd`-style `rd /s` is already refused as a runner. |
| Protected paths | Drive roots (`C:\`), anything of depth ≤ 1 (`C:\Windows`, `C:\Users`, `C:\Program Files`), the user profile and its ancestors, `%WINDIR%` and `%ProgramFiles%` subtrees, UNC share roots. Paths are compared case-insensitively after `ntpath.normpath`, with `~`, `$HOME`, `$env:USERPROFILE` and relative paths resolved against `cwd`. |
| Registry | `Remove-Item` and `Remove-ItemProperty` / `Set-ItemProperty` under `HKLM:`, and `reg delete` / `reg add` on HKLM. |
| Disks | `Format-Volume`, `Clear-Disk`, `Initialize-Disk`, `Remove-Partition`, `Set-Partition`, `diskpart`, `format`, `cipher /w`, `vssadmin delete`, `wbadmin delete`. |
| Power | `Stop-Computer`, `Restart-Computer`, `shutdown`, `Suspend-BitLocker`, `Disable-BitLocker`. |
| Processes | `Stop-Process` and its aliases `kill` and `spps`, and `taskkill`, on Zeno's own PID, on critical processes (`csrss`, `wininit`, `winlogon`, `lsass`, `services`, `smss`, `svchost`), or by wildcard name. |
| Security and firewall | `Set-MpPreference -Disable*`, `Add-MpPreference -Exclusion*`, `Set-NetFirewallProfile`, `netsh advfirewall`. |
| Accounts and permissions | `net user`, `net localgroup`, `New-LocalUser`, `Remove-LocalUser`, `Set-LocalUser`, `Add-LocalGroupMember`, `Set-Acl`, `icacls`, `takeown`. |
| Boot | `bcdedit`, `bcdboot`. |

Elevation is out entirely: `Start-Process -Verb RunAs` is already refused as a runner, and Zeno never runs elevated. This matches the Linux decision that blocks sudo.

The policy is a pure function of (syntax-tree JSON, context). Unit tests therefore feed it JSON trees and run on any OS.

### 4.3 Risk tier

`run_powershell` is **PRIVILEGED**, the same as `run_command`. Boss's brief says MUTATING; PRIVILEGED is MUTATING plus one more guarantee:
- both tiers need approval on every call;
- only PRIVILEGED is also hidden from runs Zeno starts on its own (proactive turns), so a watcher event can never queue a shell command.

This is what Boss approved for Linux in PR #21. Decision 3 in section 10 covers it.

---

## 5. Desktop notifications

| | Linux (exists) | Windows (new) |
|---|---|---|
| Back end | `hostos/linux/dbus.py`, dbus-fast `Notify` | `hostos/windows/toast.py`, WinRT `ToastNotificationManager` |
| Package | `dbus-fast` | `winrt-runtime`, `winrt-Windows.UI.Notifications`, `winrt-Windows.Data.Xml.Dom` |
| Tool | `notify_desktop(title, body, urgency)` READ_ONLY, rate-limited | same tool, same limits |

- **Why WinRT and not the two libraries Boss named:**
  - `win10toast` has had no release since 2017. It pulls in pywin32 and setuptools, and it shows toasts by spawning a tray icon on a thread, which leaks icons and blocks.
  - `winsdk` is archived; its maintainers replaced it with the per-namespace `winrt-*` packages above.
  - Decision 4 in section 10 covers this.
- **Notifier ID.** Toasts need an AppUserModelID registered on a Start-menu shortcut. `windows_setup.ps1` creates that shortcut with AUMID `Zeno.Brain`. If it is missing, `toast.py` falls back to PowerShell's own AUMID, so toasts still show (labelled "Windows PowerShell"), and logs a hint.
- **Urgency.** `critical` maps to `scenario="urgent"` with the default sound; `low` maps to silent.
- **`service_status`.**
  - On Windows it is `psutil.win_service_get(name)`: no subprocess, no admin. It returns the status, start type, binary path and PID.
  - The name pattern is checked the same way as on Linux, with letters, digits, `_ . - @`.
  - Same tool name and arguments as Linux. The `scope` argument (user or system) is ignored on Windows, where services are machine-wide.

---

## 6. Daemons (`brain/daemons/`)

### 6.1 Linux (moved, unchanged)

`zeno.service` and `install-service.sh` move from `brain/linux/` to `brain/daemons/`. They are still a systemd user service with `Type=notify` and the watchdog, as approved for PR #21.

### 6.2 Windows: `windows_setup.ps1` with Task Scheduler (decision 5)

- **What it registers.**
  - A Scheduled Task named `Zeno`, for the current user, triggered **at logon**.
  - The action is `brain\.venv\Scripts\pythonw.exe -m zeno serve`. `pythonw` means no console window, and the working directory is `brain\`.
  - Settings:
    - restart on failure every 1 minute, up to 999 times;
    - no execution time limit;
    - start when available;
    - do not stop on battery;
    - run only when the user is logged on;
    - `RunLevel Limited`, so no admin is needed and Zeno never runs elevated.
- **Flags.** `-Remove` unregisters the task and the shortcut. `-Now` starts it immediately.
- **Toast shortcut.** It also creates the Start-menu shortcut with AUMID `Zeno.Brain` (section 5).
- **Checks.**
  - The script validates that `.venv` exists, and tells you to run `setup.ps1` first if not.
  - It prints the task's state at the end.
- **Logs** go to `brain\data\logs\` because there is no journald; the daemon already writes there.
- **Why not NSSM:**
  - NSSM needs admin and a third-party binary download.
  - NSSM runs Zeno as a Windows *service* in session 0, where toasts can't appear and the user profile paths differ.
  - A logon task is the closest Windows equivalent of a systemd *user* service.
- **Health checks.** There is no sd_notify equivalent on Windows. `hostos/linux/systemd.py` stays Linux-only, and the loader skips it on Windows. Restart-on-failure comes from the task settings.

---

## 7. Configuration (`zeno/config.py`, `.env.example`)

Nothing from PR #21 has shipped yet, so the Linux-named settings are renamed now:

| Setting | Default | Meaning |
|---|---|---|
| `ZENO_OS_TOOLS` | false | telemetry, notifications and service status for this OS (was `ZENO_LINUX_TOOLS`) |
| `ZENO_RUN_COMMAND` | false | enables `run_command` on Linux or `run_powershell` on Windows |
| `ZENO_RUN_COMMAND_ROOTS` | `~` | folders commands may run in |
| `ZENO_RUN_COMMAND_TIMEOUT` / `_MAX_OUTPUT` | 30 s / 16000 | unchanged |
| `ZENO_DESKTOP_NOTIFY_PER_HOUR` | 30 | unchanged, both OSes |

---

## 8. Tests first (TDD), safe on any machine

Every test below runs on Linux **and** Windows without changing the host:

| Area | How it stays safe |
|---|---|
| OS loader | `system=` is injected ("Linux", "Windows", "Darwin"). Asserts the tool names per OS and that the other OS's module is never imported. |
| Isolation | AST import test plus a `sys.modules` subprocess test (section 2). |
| PowerShell policy | Pure function over JSON trees. Covers the table-driven refusals in section 4.2 (aliases, parameter prefixes, wildcards, case, `~`/`$env:` paths, script-block contents). Hypothesis property tests generate `Remove-Item -Recurse` against protected paths × aliases × prefixes × quoting, as the Linux rm tests do. |
| Real parser | `ps_parse.ps1` is run through a real `pwsh` when one is installed (`pytest.mark.skipif` otherwise). PowerShell 7 for Linux uses the same parser, so this container can check the JSON shape and the bypass cases (backticks, splatting, `&`, `.`, encoded commands) against the real thing. Saved JSON fixtures from those runs drive the pure policy tests everywhere else. |
| `run_powershell` tool | `unittest.mock` stands in for the parser call and the runner. Checks that the precheck refuses before approval, that the encoded command carries the Constrained Language preamble and the exact flags, that stdout and stderr both reach the observation, and the timeout path (tree kill through a fake psutil). |
| Toasts | A fake WinRT module tree is injected into `sys.modules` (`winrt.windows.ui.notifications`, etc.). Asserts the toast XML, AUMID fallback, urgency mapping and rate limit. |
| `service_status` (Windows) | Fake `psutil.win_service_get`. |
| `windows_setup.ps1` | Parsed by the real `pwsh` parser (syntax only) where available, and a test asserts the key task settings appear in it. |
| Linux tests (existing 995) | Already mock dbus and subprocess. Real-process tests (`setsid`, `dbus-daemon`, `systemd-analyze`) keep their `skipif` guards, so they skip on Windows. `test_systemd.py` gets an explicit Linux-only skip rather than relying on `AF_UNIX` being absent. |

- **Type checking.** `mypy --strict zeno` runs twice: once with `--platform linux` and once with `--platform win32`, so each OS's branches are type-checked on this Linux box. The WinRT packages are typed; if a stub is missing on Linux, `toast.py` declares a small Protocol and mypy ignores only that import.
- **CI on real Windows (decision 6).** The repo has no GitHub Actions today. A small workflow, `brain-tests.yml`, runs ruff, `mypy --strict` and pytest on `ubuntu-latest` and `windows-latest` for changes under `brain/`. That gives a real Windows run of the mocked tests on every push, without llama.cpp model downloads: the tiny GGUF fixture already covers that.

---

## 9. Dependencies and build order

**`requirements.txt`:**

```
psutil==7.2.2                                              # exists, both OSes
dbus-fast==5.2.0; sys_platform == "linux"                  # exists
winrt-runtime==<pin>; sys_platform == "win32"              # NEW
winrt-Windows.UI.Notifications==<pin>; sys_platform == "win32"
winrt-Windows.Data.Xml.Dom==<pin>; sys_platform == "win32"
```

The exact versions are pinned in step 2 from PyPI, as for every other dependency. `test_environment.py` gains checks that the markers are present.

**Build order**, one commit each, tests first:
1. Move the Linux code into `hostos/linux` and `os_linux.py`, and move the unit and scripts to `brain/daemons/`. Behaviour is unchanged and all 995 tests still pass.
2. Add `os_loader.py`, the isolation tests and the config renames; the daemon uses the loader.
3. Add the Windows telemetry additions.
4. Add `ps_parse.ps1` and `ps_policy.py`, with tests and the real-parser fixtures.
5. Add `run_powershell` (runner tree-kill, encoded command, precheck).
6. Add the toast back end and `service_status` for Windows.
7. Add `windows_setup.ps1`.
8. Add the CI workflow, the docs (`brain/CLAUDE.md`, `.env.example`, the PR #21 description) and both mypy platforms.

The gate is the same as always: all tests pass, ruff and format are clean, and `mypy --strict` is clean (now on both platforms).

---

## 10. Decisions for Boss (defaults this plan assumes)

| # | Decision | Default |
|---|---|---|
| 1 | Where it ships | Into PR #21 (unmerged), retitled "Phase 3: cross-platform OS integration". This avoids moving the Linux files twice. |
| 2 | Linux execution | Keep `run_command` as approved: argv with no shell, rather than a literal `bash -c`. It is safer and already built. |
| 3 | Execution tier | PRIVILEGED on both OSes: approval on every call, never in proactive runs. |
| 4 | Windows toasts | `winrt-*` packages, not `win10toast` or `winsdk`. |
| 5 | Windows background start | Task Scheduler at logon, current user, no admin. Not NSSM. |
| 6 | Windows verification | Add a GitHub Actions matrix (Ubuntu + Windows) for `brain/`. |
| 7 | Windows PowerShell | Use `pwsh` 7 when installed, else built-in 5.1. Constrained Language Mode on. |

**Known limits, stated up front:**
- I can't run Zeno on a real Windows desktop from here. The Windows parts are verified by:
  - mocks;
  - the real PowerShell parser (pwsh for Linux);
  - `mypy --platform win32`;
  - the Windows CI job.

  The first real toast and Scheduled Task run will be on your PC.
- As on Linux, multi-step indirection relies on approval. For example, Zeno could edit a file that a later approved command reads. Constrained Language Mode and `-ExecutionPolicy Restricted` remove the most common Windows forms of this (`.ps1` and .NET calls).
