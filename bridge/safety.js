'use strict';
// NEXUS Windows bridge — immutable safety core.
//
// Everything the bridge is ever allowed to run funnels through this module.
// It is deliberately small, dependency-free and frozen at load so no later
// code (or injected request) can widen it. Two independent layers protect the
// host:
//
//   1. An ALLOWLIST of named verbs. The HTTP surface can only ask for a verb by
//      name; it can never hand the bridge a raw command line. Each verb maps to
//      a single fixed executable plus a validated, explicitly-built argument
//      array. PowerShell scripts are fixed; launch names are environment data,
//      never concatenated into executable source.
//   2. A hard BLACKLIST that rejects destructive executables and argument
//      patterns (disk formatting, registry deletion, recursive system-path
//      removal, boot-config edits, shadow-copy wipes, power-state changes...)
//      even if a future verb were ever mis-wired to reach them. Defence in
//      depth: the allowlist should already prevent these; the blacklist means a
//      mistake fails closed.
//
// Nothing in here reads the network, the environment or the filesystem, so it
// is unit-testable in isolation and behaves identically on every machine.

// --- Layer 2: the immutable blacklist ------------------------------------

// Executable basenames that are never permitted, whatever the verb.
const FORBIDDEN_EXECUTABLES = Object.freeze([
  'format', 'format.com', 'diskpart', 'fdisk', 'cipher', 'bcdedit', 'bootrec',
  'vssadmin', 'wbadmin', 'reg', 'regedit', 'regedt32', 'shutdown', 'logoff',
  'rundll32', 'mshta', 'wscript', 'cscript', 'at', 'schtasks', 'sc',
  'net', 'netsh', 'takeown', 'icacls', 'cacls', 'attrib', 'subst', 'fsutil',
  'wmic', 'cmd', 'command', 'rm', 'rmdir', 'rd', 'del', 'erase', 'move', 'ren',
]);

// Substrings that, if present anywhere in a resolved command + arguments
// (case-insensitively), abort execution. These catch destructive intent even
// when it is smuggled through an otherwise-allowed executable (e.g. a
// PowerShell script body, a Playwright target).
const FORBIDDEN_PATTERNS = Object.freeze([
  'format-volume', 'clear-disk', 'remove-partition', 'initialize-disk',
  'remove-item', 'rd /s', 'rmdir /s', 'del /', 'erase /', 'format ',
  'remove-itemproperty', 'remove-item -path', 'set-itemproperty hklm',
  'reg delete', 'reg add', 'regedit', 'bcdedit', 'diskpart', 'vssadmin delete',
  'cipher /w', 'takeown', 'icacls', 'invoke-expression', 'iex ', 'iex(',
  'downloadstring', 'start-process -verb runas', 'stop-computer',
  'restart-computer', 'remove-computer', 'disable-computerrestore',
  'set-executionpolicy', 'new-service', 'remove-service', 'stop-service',
  'uninstall-', '& {', 'rm -rf', 'mkfs', ':(){', 'shutdown',
]);

// System roots that may never be the target of a destructive verb. Used by
// callers that resolve a path argument.
const PROTECTED_ROOTS = Object.freeze([
  'c:\\windows', 'c:\\program files', 'c:\\program files (x86)',
  'c:\\programdata', '\\windows\\system32', '/system', '/windows',
]);

function baseName(executable) {
  const trimmed = String(executable).trim().replace(/["']/g, '');
  const tail = trimmed.split(/[\\/]/).pop() || trimmed;
  return tail.toLowerCase();
}

// Throws if the executable itself is forbidden. Note PowerShell IS allowed as
// an executable (we need it for diagnostics and UIA), but its *script body* is
// re-checked against FORBIDDEN_PATTERNS below.
function assertExecutableAllowed(executable) {
  const name = baseName(executable).replace(/\.(exe|com|bat|cmd|ps1)$/i, '');
  if (FORBIDDEN_EXECUTABLES.includes(name) || FORBIDDEN_EXECUTABLES.includes(baseName(executable))) {
    throw new SafetyError(`Executable "${executable}" is blocked by the NEXUS safety policy.`);
  }
}

function assertNoForbiddenPatterns(parts) {
  const haystack = parts.map(p => String(p)).join(' ').toLowerCase();
  for (const pattern of FORBIDDEN_PATTERNS) {
    if (haystack.includes(pattern)) {
      throw new SafetyError(`Request blocked: contains the forbidden pattern "${pattern.trim()}".`);
    }
  }
}

function assertPathNotProtected(target) {
  if (target == null) return;
  const normalized = String(target).toLowerCase().replace(/\//g, '\\');
  for (const root of PROTECTED_ROOTS) {
    const r = root.replace(/\//g, '\\');
    if (normalized === r || normalized.startsWith(r + '\\')) {
      throw new SafetyError(`Path "${target}" is a protected system location.`);
    }
  }
}

class SafetyError extends Error {
  constructor(message) { super(message); this.name = 'SafetyError'; this.safety = true; }
}

// --- Layer 1: the allowlist of verbs -------------------------------------
//
// Each verb is a pure function (params) -> { command, args, timeout, shell:false }.
// It validates and builds the argument array itself; the router never forwards
// user-supplied argv. `shell` is always false — execFile semantics only.

const PWSH = 'powershell.exe';
// -NoProfile -NonInteractive keeps startup deterministic; we never pass
// -ExecutionPolicy Bypass (that is in the pattern blacklist anyway).
const PWSH_BASE = Object.freeze(['-NoProfile', '-NonInteractive', '-NoLogo', '-Command']);

// A tiny, fixed PowerShell program that reads CPU/GPU/memory and the top
// processes via CIM/WMI and prints JSON. No user input is interpolated.
const DIAGNOSTICS_SCRIPT = [
  '$ErrorActionPreference="SilentlyContinue";',
  '$cpu=Get-CimInstance Win32_Processor|Select-Object -First 1;',
  '$load=(Get-CimInstance Win32_Processor|Measure-Object -Property LoadPercentage -Average).Average;',
  '$os=Get-CimInstance Win32_OperatingSystem;',
  '$gpu=Get-CimInstance Win32_VideoController|Select-Object -First 1;',
  '$procs=Get-Process|Sort-Object -Property WorkingSet64 -Descending|Select-Object -First 8 Name,Id,@{n="memMB";e={[math]::Round($_.WorkingSet64/1MB,1)}},@{n="cpu";e={[math]::Round($_.CPU,1)}};',
  '[pscustomobject]@{',
  '  cpuName=$cpu.Name; cores=$cpu.NumberOfCores; logical=$cpu.NumberOfLogicalProcessors; cpuLoad=$load;',
  '  gpuName=$gpu.Name; gpuDriver=$gpu.DriverVersion; gpuRamMB=[math]::Round($gpu.AdapterRAM/1MB);',
  '  totalMemMB=[math]::Round($os.TotalVisibleMemorySize/1KB); freeMemMB=[math]::Round($os.FreePhysicalMemory/1KB);',
  '  uptimeSec=[math]::Round(((Get-Date)-$os.LastBootUpTime).TotalSeconds); processes=$procs',
  '}|ConvertTo-Json -Depth 4 -Compress',
].join(' ');

// UIA inspection of the focused window: process, title, and a bounded control
// tree with text content. Uses the built-in UIAutomationClient / root
// automation element; reads only, never synthesises input here (input is a
// separate, explicitly-confirmed verb). No user input interpolated.
const SCREEN_CONTEXT_SCRIPT = [
  'Add-Type -AssemblyName UIAutomationClient,UIAutomationTypes,System.Windows.Forms;',
  'Add-Type @"\nusing System;using System.Runtime.InteropServices;public class NxWin{[DllImport("user32.dll")]public static extern IntPtr GetForegroundWindow();[DllImport("user32.dll")]public static extern int GetWindowThreadProcessId(IntPtr h,out int p);}\n"@;',
  '$h=[NxWin]::GetForegroundWindow(); $pid2=0; [void][NxWin]::GetWindowThreadProcessId($h,[ref]$pid2);',
  '$proc=Get-Process -Id $pid2 -ErrorAction SilentlyContinue;',
  '$root=[System.Windows.Automation.AutomationElement]::FromHandle($h);',
  '$title=if($root){$root.Current.Name}else{""};',
  '$cond=New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::IsControlElementProperty,$true);',
  '$els=if($root){$root.FindAll([System.Windows.Automation.TreeScope]::Descendants,$cond)}else{@()};',
  '$nodes=@(); $max=[Math]::Min($els.Count,120);',
  'for($i=0;$i -lt $max;$i++){$e=$els[$i]; $nodes+=[pscustomobject]@{type=$e.Current.ControlType.ProgrammaticName -replace "ControlType\\.","";name=$e.Current.Name;auto=$e.Current.AutomationId;enabled=$e.Current.IsEnabled;focus=$e.Current.HasKeyboardFocus}};',
  '[pscustomobject]@{process=$proc.ProcessName;processId=$pid2;title=$title;controlCount=$els.Count;controls=$nodes}|ConvertTo-Json -Depth 5 -Compress',
].join(' ');

// Windows snap/window verbs are expressed as nircmd-free, built-in PowerShell
// window operations against a target process, to avoid shipping a binary.
function windowActionScript(action, processName) {
  // processName is validated by the verb before this is called.
  const mode = { minimize: 6, restore: 9, focus: 9, maximize: 3 }[action];
  return [
    '$ErrorActionPreference="Stop";',
    'Add-Type -TypeDefinition \'using System; using System.Runtime.InteropServices; public class NxWindow { [DllImport("user32.dll")] public static extern bool ShowWindowAsync(IntPtr h,int n); [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }\';',
    `$p=Get-Process -Name '${processName}' -ErrorAction SilentlyContinue|Where-Object {$_.MainWindowHandle -ne 0}|Select-Object -First 1;`,
    'if(-not $p){Write-Output (@{ok=$false;reason="not found"}|ConvertTo-Json -Compress);return};',
    `$ok=[NxWindow]::ShowWindowAsync($p.MainWindowHandle,${mode});`,
    action === 'focus' ? '$ok=[NxWindow]::SetForegroundWindow($p.MainWindowHandle);' : '',
    '@{ok=$ok;process=$p.ProcessName;id=$p.Id}|ConvertTo-Json -Compress',
  ].join(' ');
}

const VALID_PROCESS_NAME = /^[A-Za-z0-9 ._-]{1,64}$/;
const VALID_APP_PATH = /^[A-Za-z0-9 ._:\\()\\/-]{1,256}$/;
const VALID_URL = /^https?:\/\/[^\s"'`<>]{1,2048}$/i;

const VERBS = Object.freeze({
  // System diagnostics via CIM/WMI.
  diagnostics() {
    return { command: PWSH, args: [...PWSH_BASE, DIAGNOSTICS_SCRIPT], timeout: 15000, shell: false };
  },
  // Focused-window UI Automation snapshot.
  'screen-context'() {
    return { command: PWSH, args: [...PWSH_BASE, SCREEN_CONTEXT_SCRIPT], timeout: 15000, shell: false };
  },
// Launch an installed application by exact display name. User data travels
// through the environment; the PowerShell source is identical for every name.
  'app.launch'(params) {
    const app = String(params && params.app ? params.app : '').trim();
    if (!/^[A-Za-z0-9 ._-]{1,80}$/.test(app)) throw new SafetyError('Use an installed application name, not a path or command.');
    assertPathNotProtected(app);
    // The launch target itself must not be a forbidden executable.
    assertExecutableAllowed(app);
    if (params?.args !== undefined && (!Array.isArray(params.args) || params.args.length)) throw new SafetyError('Application arguments are not supported.');
    if (/^(powershell|pwsh|node|python[0-9.]*|bash|sh)(\.exe)?$/i.test(app)) throw new SafetyError('Command interpreters are not launchable.');
    // Resolve Start-menu identities; never accept a caller-supplied executable.
    const script = [
      '$ErrorActionPreference="Stop";',
      '$name=$env:NEXUS_LAUNCH_APP;',
      '$builtins=@{notepad="notepad.exe";calculator="calc.exe";calc="calc.exe";paint="mspaint.exe"};',
      '$short=$name -replace "\\.exe$","";',
      'if($builtins.ContainsKey($short)){Start-Process -FilePath (Join-Path $env:SystemRoot ("System32/"+$builtins[$short]));}else{',
      '$matches=@(Get-StartApps | Where-Object {$_.Name -eq $name});',
      'if($matches.Count -ne 1){throw "No unique installed application matches this name."};',
      '$id=$matches[0].AppID;',
      'if($id -notmatch "^[A-Za-z0-9_.!{}-]+$"){throw "This application requires an unsupported launcher."};',
      'Start-Process -FilePath (Join-Path $env:SystemRoot "explorer.exe") -ArgumentList ("shell:AppsFolder\\"+$id);',
      '}; @{ok=$true;app=$name}|ConvertTo-Json -Compress',
    ].join(' ');
    return { command: PWSH, args: [...PWSH_BASE, script], env: { NEXUS_LAUNCH_APP: app }, timeout: 15000, shell: false, inspect: [app] };
  },
  // Window management: focus / minimize / restore / maximize a running app.
  'app.window'(params) {
    const action = String(params && params.action);
    if (!['focus', 'minimize', 'restore', 'maximize'].includes(action)) throw new SafetyError('Unknown window action.');
    const name = String(params && params.process ? params.process : '').trim();
    if (!VALID_PROCESS_NAME.test(name)) throw new SafetyError('Invalid process name.');
    return { command: PWSH, args: [...PWSH_BASE, windowActionScript(action, name.replace(/'/g, ''))], timeout: 10000, shell: false };
  },
});

// A URL validator exported for the headless-research verb, which runs inside
// the bridge process (Playwright) rather than as a child executable.
function assertResearchUrlAllowed(url) {
  const u = String(url || '').trim();
  if (!VALID_URL.test(u)) throw new SafetyError('Research targets must be http(s) URLs.');
  assertNoForbiddenPatterns([u]);
  try {
    const parsed = new URL(u);
    // Never let a "research" task reach the loopback control plane or metadata.
    const host = parsed.hostname.toLowerCase();
    if (['localhost', '127.0.0.1', '0.0.0.0', '::1', '169.254.169.254'].includes(host) || host.endsWith('.local')) {
      throw new SafetyError('Research cannot target local or link-local hosts.');
    }
  } catch (err) {
    if (err instanceof SafetyError) throw err;
    throw new SafetyError('Malformed research URL.');
  }
  return u;
}

// The single entry point the HTTP router uses. Given a verb name and params it
// returns a validated, ready-to-execFile plan, after running BOTH safety
// layers over the resolved command + arguments.
function planCommand(verb, params) {
  const builder = VERBS[verb];
  if (typeof builder !== 'function') throw new SafetyError(`Unknown verb "${verb}".`);
  const plan = builder(params || {});
  assertExecutableAllowed(plan.command);
  // Re-check the fully-resolved command line (incl. any script body) against
  // the destructive-pattern blacklist. `inspect` lets a verb add extra operands
  // (e.g. a launch target) that must also be screened.
  assertNoForbiddenPatterns([plan.command, ...plan.args, ...(plan.inspect || [])]);
  if (plan.shell !== false) throw new SafetyError('Internal: shell execution is not permitted.');
  delete plan.inspect;
  return plan;
}

function listVerbs() {
  return Object.keys(VERBS).concat(['research']);
}

module.exports = Object.freeze({
  SafetyError,
  planCommand,
  listVerbs,
  assertResearchUrlAllowed,
  // Exposed for unit tests / introspection; the arrays themselves are frozen.
  FORBIDDEN_EXECUTABLES,
  FORBIDDEN_PATTERNS,
  PROTECTED_ROOTS,
  _internal: Object.freeze({ assertExecutableAllowed, assertNoForbiddenPatterns, assertPathNotProtected, baseName }),
});
