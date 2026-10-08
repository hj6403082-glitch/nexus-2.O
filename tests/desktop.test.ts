import { test } from 'node:test';
import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { DesktopError, executeDesktop, resolveApp, validateDesktop, permissionMessage } from '../src/desktop/bridge';
import { cocoaToCarbon, describeDisplays, displayPhrase, linkDisplay, windowBounds } from '../src/desktop/displays';
import { matchCommand, validateCommand } from '../src/ai/protocol';
import { websiteUrl } from '../src/desktop/sites';
import { rank, rankEntries } from '../src/lib/rank';
import { matchDestination, resolveDestination } from '../src/knowledge/destinations';
const apps = [{ name: 'Music', path: '/System/Applications/Music.app' }, { name: 'Safari', path: '/Applications/Safari.app' }];
test('desktop verbs reject shell commands and destructive operations', () => {
  for (const verb of ['exec', 'shell', 'shutdown', 'restart', 'delete', 'rm', '__proto__']) assert.equal(validateDesktop({ verb }), null);
  assert.equal(resolveApp(apps, 'Music; touch /tmp/injected'), undefined);
  assert.equal(resolveApp(apps, '$(whoami)'), undefined);
  assert.equal(resolveApp(apps, 'music')?.name, 'Music');
});
test('an injected command string resolves to "no such application" and never executes', async () => {
  const marker = `/tmp/nexus-injection-${process.pid}`;
  for (const phrase of [`open Safari; touch ${marker}`, `launch Music && touch ${marker}`, `open $(touch ${marker})`, `open \`touch ${marker}\``]) {
    const command = matchCommand(phrase);
    assert.equal(command?.type, 'desktop', phrase);
    if (command?.type !== 'desktop') continue;
    assert.equal(command.request.verb, 'launch');
    await assert.rejects(executeDesktop(command.request, async () => apps), (error: Error) => error instanceof DesktopError && /^No such application/.test(error.message));
  }
  assert.equal(existsSync(marker), false);
});
test('desktop commands are local-only: the model stream cannot issue them', () => {
  assert.equal(validateCommand({ type: 'desktop', request: { verb: 'launch', value: 'Terminal' } }), null);
  assert.equal(validateCommand({ type: 'destination', destination: 'profile' }), null);
});
test('voice phrasing reaches every desktop capability', () => {
  const verb = (text: string) => { const c = matchCommand(text); return c?.type === 'desktop' ? `${c.request.verb}${c.request.value === undefined ? '' : `:${c.request.value}`}` : c?.type ?? null; };
  assert.equal(verb('Nexus, open Spotify'), 'launch:spotify');
  assert.equal(verb('quit Safari'), 'quit:safari');
  assert.equal(verb('close stocks'), 'close');
  assert.equal(verb('open youtube'), 'website:https://www.youtube.com/');
  assert.equal(verb('go to github.com/vercel/next.js'), 'website:https://github.com/vercel/next.js');
  assert.equal(verb('pause the music'), 'media:pause');
  assert.equal(verb('next track'), 'media:next');
  assert.equal(verb('set volume to 40%'), 'volume:40');
  assert.equal(verb('mute'), 'volume:0');
  assert.equal(verb('take a screenshot'), 'screenshot');
  assert.equal(verb('copy Hello World to clipboard'), 'clipboard-write:Hello World');
  assert.equal(verb("what's on my clipboard"), 'clipboard-read');
  assert.equal(verb('hide others'), 'hide-others');
  assert.equal(verb('lock the screen'), 'lock-screen');
  assert.equal(verb('sleep display'), 'sleep-display');
  assert.equal(verb('turn on do not disturb'), 'focus:on');
  assert.equal(verb('disable do not disturb'), 'focus:off');
  assert.equal(verb('create a note saying Buy Milk'), 'note:Buy Milk');
  assert.equal(verb('remind me to call Sam'), 'reminder:call Sam');
  assert.equal(verb('show displays'), 'displays');
  assert.equal(verb('open my reels'), 'destination');
  assert.equal(verb('open stocks'), 'open');
  // Questions still reach the model.
  assert.equal(verb('show me how MCP works'), null);
  assert.equal(verb('open the question of how gravity works in general relativity'), null);
});
test('websites accept only http(s)', () => {
  assert.equal(websiteUrl('javascript:alert(1)'), null);
  assert.equal(websiteUrl('file:///etc/passwd'), null);
  assert.equal(websiteUrl('example.com'), 'https://example.com/');
});
test('displays convert Cocoa frames to Carbon bounds and use real names', () => {
  // Laptop 1512×982 primary; LG ultrawide 3440×1440 above-right, Cocoa y up.
  const displays = describeDisplays([{ name: 'Built-in Retina Display', frame: { x: 0, y: 0, width: 1512, height: 982 } }, { name: 'LG ULTRAWIDE', frame: { x: 1512, y: 200, width: 3440, height: 1440 } }]);
  assert.deepEqual(cocoaToCarbon({ x: 1512, y: 200, width: 3440, height: 1440 }, 982), [1512, -658, 4952, 782]);
  assert.deepEqual(displays[1].bounds, [1512, -658, 4952, 782]);
  assert.equal(linkDisplay(displays).name, 'LG ULTRAWIDE');
  assert.equal(displayPhrase(displays[1]), 'on your LG ULTRAWIDE');
  assert.equal(displayPhrase(displays[0]), 'on your laptop');
  assert.deepEqual(windowBounds(displays[0]), [40, 65, 1472, 942]);
  // A display below the primary has a positive Carbon top.
  assert.deepEqual(cocoaToCarbon({ x: 0, y: -1080, width: 1920, height: 1080 }, 982), [0, 982, 1920, 2062]);
});
test('launcher ranks prefix, then initials, then word boundary, then substring', () => {
  assert.equal(rank('Google Chrome', 'goo'), 1);
  assert.equal(rank('Google Chrome', 'gc'), 2);
  assert.equal(rank('Google Chrome', 'chr'), 3);
  assert.equal(rank('Google Chrome', 'rom'), 4);
  assert.equal(rank('Google Chrome', 'xyz'), 99);
  const ranked = rankEntries([{ name: 'Visual Studio Code' }, { name: 'Activity Monitor' }, { name: 'Vscode Helper' }, { name: 'Calendar' }], 'vs');
  assert.deepEqual(ranked.map(e => e.name), ['Vscode Helper', 'Visual Studio Code']);
});
test('personal destinations resolve from the live feed, never a hardcoded profile', () => {
  assert.equal(matchDestination('my reels'), 'reels');
  assert.equal(matchDestination('my profile'), 'profile');
  assert.equal(matchDestination('reels'), null);
  const feed = { username: 'someone.creates', media: [{ permalink: 'https://www.instagram.com/p/older/', timestamp: '2026-01-01', media_type: 'IMAGE' }, { permalink: 'https://www.instagram.com/reel/newest/', timestamp: '2026-02-01', media_type: 'VIDEO', media_product_type: 'REELS' }] };
  assert.deepEqual(resolveDestination('reels', feed), { url: 'https://www.instagram.com/someone.creates/reels/', label: '@someone.creates reels' });
  assert.deepEqual(resolveDestination('latest-reel', feed), { url: 'https://www.instagram.com/reel/newest/', label: 'your latest reel' });
  assert.ok('error' in resolveDestination('profile', {}));
  assert.ok('error' in resolveDestination('profile', { username: '../evil' }));
  assert.ok('error' in resolveDestination('latest-post', { username: 'a', media: [{ permalink: 'https://evil.example/' }] }));
});
test('macOS permissions name the exact setting for the terminal', () => {
  assert.match(permissionMessage(new Error('execution error: Not authorized to send Apple events to System Events. (-1743)')), /terminal.*Automation/);
  assert.match(permissionMessage(new Error('could not create image from display')), /Screen Recording/);
  assert.match(permissionMessage(new Error('osascript is not allowed to send keystrokes. (1002)')), /Accessibility/);
  assert.match(permissionMessage(new Error('Couldn’t find shortcut “NEXUS Focus On”')), /Shortcuts/);
});
