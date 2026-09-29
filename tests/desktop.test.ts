import { test } from 'node:test';
import assert from 'node:assert/strict';
import { resolveApp, validateDesktop, permissionMessage } from '../src/desktop/bridge';
test('desktop verbs reject shell commands and destructive operations', () => {
  for (const verb of ['exec', 'shutdown', 'restart', 'delete', '__proto__']) assert.equal(validateDesktop({ verb }), null);
  const apps = [{ name: 'Music', path: '/System/Applications/Music.app' }];
  assert.equal(resolveApp(apps, 'Music; touch /tmp/injected'), undefined);
  assert.equal(resolveApp(apps, '$(whoami)'), undefined);
  assert.equal(resolveApp(apps, 'music')?.name, 'Music');
});
test('macOS permissions name the terminal grant', () => {
  assert.match(permissionMessage(new Error('-1743')), /terminal.*Automation/);
  assert.match(permissionMessage(new Error('could not create image')), /Screen Recording/);
});
