'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const safety = require('./safety');

test('known verbs produce execFile plans with no shell and an argument array', () => {
  for (const verb of ['diagnostics', 'screen-context']) {
    const plan = safety.planCommand(verb, {});
    assert.equal(plan.shell, false);
    assert.equal(plan.command, 'powershell.exe');
    assert.ok(Array.isArray(plan.args) && plan.args.includes('-NoProfile'));
    assert.ok(typeof plan.timeout === 'number' && plan.timeout > 0);
  }
});

test('unknown verbs are rejected as safety errors', () => {
  assert.throws(() => safety.planCommand('run-anything', { cmd: 'whatever' }), /Unknown verb/);
  assert.throws(() => safety.planCommand('../../etc', {}), e => e.safety === true);
});

test('app.launch validates the target and screens protected paths', () => {
  const ok = safety.planCommand('app.launch', { app: 'notepad.exe' });
  assert.ok(ok.args.at(-1).includes('Start-Process'));
  assert.throws(() => safety.planCommand('app.launch', { app: 'C:\\Windows\\System32\\cmd.exe' }), e => e.safety === true);
  assert.throws(() => safety.planCommand('app.launch', { app: 'bad; rm -rf /' }), e => e.safety === true);
});

test('app.window only accepts the four known actions and a clean process name', () => {
  const ok = safety.planCommand('app.window', { action: 'minimize', process: 'chrome' });
  assert.equal(ok.command, 'powershell.exe');
  assert.throws(() => safety.planCommand('app.window', { action: 'nuke', process: 'chrome' }), /window action/);
  assert.throws(() => safety.planCommand('app.window', { action: 'focus', process: "x'; Remove-Item" }), e => e.safety === true);
});

test('forbidden executables can never be planned, even as a launch target', () => {
  for (const exe of ['format', 'diskpart.exe', 'reg', 'cmd.exe', 'wscript']) {
    assert.throws(() => safety.planCommand('app.launch', { app: exe }), e => e.safety === true, `expected ${exe} blocked`);
  }
});

test('destructive patterns inside an otherwise-allowed launch are blocked', () => {
  assert.throws(() => safety.planCommand('app.launch', { app: 'powershell', args: ['Remove-Item', '-Path', 'C:\\data', '-Recurse'] }), e => e.safety === true);
  assert.throws(() => safety.planCommand('app.launch', { app: 'app', args: ['reg', 'delete', 'HKLM\\x'] }), e => e.safety === true);
});

test('research URLs must be remote http(s) and never loopback or metadata', () => {
  assert.equal(safety.assertResearchUrlAllowed('https://example.com/docs'), 'https://example.com/docs');
  assert.throws(() => safety.assertResearchUrlAllowed('http://127.0.0.1:4517/task'), e => e.safety === true);
  assert.throws(() => safety.assertResearchUrlAllowed('http://169.254.169.254/latest'), e => e.safety === true);
  assert.throws(() => safety.assertResearchUrlAllowed('file:///etc/passwd'), e => e.safety === true);
  assert.throws(() => safety.assertResearchUrlAllowed('ftp://host/x'), e => e.safety === true);
});

test('the safety arrays are frozen so no later code can widen them', () => {
  assert.ok(Object.isFrozen(safety.FORBIDDEN_EXECUTABLES));
  assert.ok(Object.isFrozen(safety.FORBIDDEN_PATTERNS));
  assert.throws(() => { safety.FORBIDDEN_EXECUTABLES.push('safe-now'); }, TypeError);
});

test('app launch data never becomes PowerShell source and interpreters/arguments are blocked', () => {
  const first = safety.planCommand('app.launch', { app: 'Visual Studio Code' });
  const second = safety.planCommand('app.launch', { app: 'Calculator' });
  assert.deepEqual(first.args, second.args);
  assert.equal(first.env.NEXUS_LAUNCH_APP, 'Visual Studio Code');
  assert.match(first.args.at(-1), /Get-StartApps/);
  for (const app of ['powershell.exe', 'pwsh', 'node', 'python3', 'bash']) assert.throws(() => safety.planCommand('app.launch', { app }));
  assert.throws(() => safety.planCommand('app.launch', { app: 'notepad', args: ['anything'] }));
});
test('window state actions issue distinct Windows show commands', () => {
  for (const [action, code] of [['minimize', 6], ['maximize', 3], ['restore', 9]]) {
    const script = safety.planCommand('app.window', { action, process: 'notepad' }).args.at(-1);
    assert.ok(script.includes(`ShowWindowAsync($p.MainWindowHandle,${code})`));
    assert.doesNotMatch(script, /SendWait/);
  }
});
