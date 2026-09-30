import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BimanualZoom } from '../src/gestures/bimanual';
const hand = (x: number) => { const h = Array.from({ length: 21 }, () => ({ x, y: .2 })); h[0].y = 0; h[9].y = .4; return h; };
test('two pinches zoom relatively, clamp, and reacquire without a jump', () => { const zoom = new BimanualZoom(); assert.equal(zoom.update([hand(.2), hand(.8)], 1), 1); assert.ok(Math.abs(zoom.update([hand(.1), hand(.9)], 1)! - 4/3) < 1e-8); assert.equal(zoom.update([hand(0),hand(1)], 1), 1.35); assert.equal(zoom.update([],1), null); assert.equal(zoom.update([hand(.3), hand(.5)],1.2),1.2); });
test('one hand and unpinched hands do not change zoom', () => { const zoom = new BimanualZoom(); assert.equal(zoom.update([hand(.3)],1),null); const open = hand(.8); open[8].x = 1; assert.equal(zoom.update([hand(.2),open],1),null); });
