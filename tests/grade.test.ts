import { test } from 'node:test';
import assert from 'node:assert/strict';
import { Color } from 'three';
import { cardTint, goldAmount, goldBloom, GOLD, WARNING, type CardTint } from '../src/rendering/gold';
import { worlds } from '../src/stores/world';
const tint = (): CardTint => ({ color: new Color(), intensity: 0 });
test('Rule 1: a warned card is never gold, whatever its centred position', () => {
  for (const frontal of [-1, 0, .5, .9, 1]) assert.equal(goldAmount(frontal, true), 0);
  assert.equal(goldBloom(1, true), 0);
  const warned = cardTint('#90c6e7', 1, true, tint());
  // A fully centred, warned card wears warning orange, not gold.
  assert.equal(warned.color.getHexString(), new Color(WARNING).getHexString());
});
test('Rule 3: gold is earned continuously, not switched', () => {
  assert.equal(goldAmount(-0.2, false), 0);          // behind the user: no gold
  assert.equal(goldAmount(0, false), 0);
  assert.ok(goldAmount(.5, false) > 0 && goldAmount(.5, false) < goldAmount(.8, false)); // monotone rise
  assert.equal(goldAmount(1, false), 1);             // dead centre: full gold
  // No binary jump: closely spaced inputs give closely spaced outputs.
  assert.ok(Math.abs(goldAmount(.7, false) - goldAmount(.72, false)) < .1);
});
test('Rule 2: gold is drawn dimmer than blue and never clips a channel', () => {
  const centredGold = cardTint('#90c6e7', 1, false, tint());   // dead-centre, unwarned → gold
  const nearCentreBlue = cardTint('#90c6e7', .6, false, tint()); // bright blue, gold barely risen
  // Prominence comes from hue, not brightness: the card is brightest in blue just
  // before it centres, then DIMS as it earns gold.
  assert.ok(centredGold.intensity < nearCentreBlue.intensity, `gold ${centredGold.intensity} should be dimmer than blue ${nearCentreBlue.intensity}`);
  // Every emissive intensity stays below 1, so no border multiplier clips red/green to white.
  for (const f of [-1, 0, .3, .6, 1]) { assert.ok(cardTint('#90c6e7', f, false, tint()).intensity < 1); assert.ok(cardTint('#90c6e7', f, true, tint()).intensity < 1); }
  // A centred unwarned card has moved toward the gold hue.
  assert.notEqual(centredGold.color.getHexString(), new Color('#90c6e7').getHexString());
});
test('gold and warning orange are distinct hues (~18° apart), never the same', () => {
  const hsl = (hex: string) => { const o = { h: 0, s: 0, l: 0 }; new Color(hex).getHSL(o); return o.h * 360; };
  const gap = Math.abs(hsl(GOLD) - hsl(WARNING));
  assert.ok(gap > 8 && gap < 30, `gold/warning hue gap ${gap.toFixed(1)}° should be small but non-zero`);
});
test('six world grades are present, distinct and filmic', () => {
  assert.equal(worlds.length, 6);
  assert.equal(new Set(worlds.map(w => w.name)).size, 6);
  for (const w of worlds) {
    assert.match(w.fog, /^#[0-9a-f]{6}$/i);
    assert.equal(w.grade.shadow.length, 3);
    assert.equal(w.grade.highlight.length, 3);
    assert.ok(w.grade.halation >= 0 && w.grade.contrast > 0);
  }
  // The Fog Chamber bleeds most and sits below 1.0 contrast; the Command Center is hard and warm.
  const fog = worlds.find(w => w.name === 'Fog Chamber')!, deck = worlds.find(w => w.name === 'Industrial Command Center')!;
  assert.ok(fog.grade.halation === Math.max(...worlds.map(w => w.grade.halation)));
  assert.ok(fog.grade.contrast < 1);
  assert.ok(deck.grade.warmth > 0 && deck.grade.contrast > 1);
});
import { moduleWorld } from '../src/stores/world';
test('Phase 4 AI Worlds: modules map to valid, distinct-enough environments', () => {
  for (const [id, index] of Object.entries(moduleWorld)) {
    assert.ok(index >= 0 && index < worlds.length, `${id} → ${index} is a real world`);
  }
  // The spec's named cases: Stocks takes the market-grid floor; Projects a creative room.
  assert.equal(worlds[moduleWorld.stocks].name, 'Industrial Command Center');
  assert.equal(worlds[moduleWorld.projects].name, 'Glass Observatory');
  // Modules the spec leaves open (system, calendar, instagram) stay on the base world.
  assert.equal(moduleWorld.system, undefined);
  assert.equal(moduleWorld.calendar, undefined);
});
