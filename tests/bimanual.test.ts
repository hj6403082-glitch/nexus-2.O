import { test } from 'node:test';
import assert from 'node:assert/strict';
import { BimanualZoom, BimanualGroup, BimanualSculpt } from '../src/gestures/bimanual';
const hand = (x: number) => { const h = Array.from({ length: 21 }, () => ({ x, y: .2 })); h[0].y = 0; h[9].y = .4; return h; };
test('two pinches zoom relatively, clamp, and reacquire without a jump', () => { const zoom = new BimanualZoom(); assert.equal(zoom.update([hand(.2), hand(.8)], 1), 1); assert.ok(Math.abs(zoom.update([hand(.1), hand(.9)], 1)! - 4/3) < 1e-8); assert.equal(zoom.update([hand(0),hand(1)], 1), 1.35); assert.equal(zoom.update([],1), null); assert.equal(zoom.update([hand(.3), hand(.5)],1.2),1.2); });
test('one hand and unpinched hands do not change zoom', () => { const zoom = new BimanualZoom(); assert.equal(zoom.update([hand(.3)],1),null); const open = hand(.8); open[8].x = 1; assert.equal(zoom.update([hand(.2),open],1),null); });

// Two open hands, palms at a given horizontal separation.
function openHands(separation: number) {
  const hand = (cx: number) => {
    const p = Array.from({ length: 21 }, () => ({ x: cx, y: .5, z: 0 }));
    p[0] = { x: cx, y: .78, z: 0 };            // wrist
    p[9] = { x: cx, y: .55, z: 0 };            // palm — hands[i][9] is the span anchor
    for (const tip of [8, 12, 16, 20]) p[tip] = { x: cx, y: .12, z: 0 }; // fingers extended
    p[4] = { x: cx - .14, y: .4, z: 0 };       // thumb out (not pinched)
    return p;
  };
  return [hand(.5 - separation / 2), hand(.5 + separation / 2)];
}
test('two open hands moving together group, moving apart split, once each', () => {
  const g = new BimanualGroup();
  assert.equal(g.update(openHands(.6)), null);   // anchor at a wide separation
  assert.equal(g.update(openHands(.5)), null);   // partway in, not yet
  assert.equal(g.update(openHands(.25)), 'group'); // closed past the threshold
  assert.equal(g.update(openHands(.2)), null);   // only once per gesture
  const s = new BimanualGroup();
  assert.equal(s.update(openHands(.2)), null);   // anchor close together
  assert.equal(s.update(openHands(.5)), 'split'); // opened past the threshold
  assert.equal(s.update(openHands(.6)), null);
  // Pinched hands (zoom) never trigger grouping.
  const pinched = openHands(.3).map(h => { h[4] = { ...h[8] }; return h; });
  assert.equal(new BimanualGroup().update(pinched), null);
});

// Two cupped hands (fingertips curled back toward the wrist), at a separation.
function cuppedHands(separation: number) {
  const hand = (cx: number) => {
    const p = Array.from({ length: 21 }, () => ({ x: cx, y: .5, z: 0 }));
    p[0] = { x: cx, y: .60, z: 0 };            // wrist
    p[9] = { x: cx, y: .55, z: 0 };            // palm (span anchor)
    for (const tip of [8, 12, 16, 20]) p[tip] = { x: cx, y: .58, z: 0 }; // fingers curled near wrist
    p[4] = { x: cx, y: .57, z: 0 };            // thumb tucked
    return p;
  };
  return [hand(.5 - separation / 2), hand(.5 + separation / 2)];
}
test('two cupped hands drawn inward converge, pushed outward expand, once each', () => {
  const c = new BimanualSculpt();
  assert.equal(c.update(cuppedHands(.6)), null);      // anchor wide
  assert.equal(c.update(cuppedHands(.3)), 'converge'); // drawn in
  assert.equal(c.update(cuppedHands(.2)), null);       // only once
  const e = new BimanualSculpt();
  assert.equal(e.update(cuppedHands(.2)), null);       // anchor close
  assert.equal(e.update(cuppedHands(.5)), 'expand');   // pushed out
  // Open hands (fingers extended) never sculpt — that is the gather gesture.
  assert.equal(new BimanualSculpt().update(openHands(.3)), null);
});
