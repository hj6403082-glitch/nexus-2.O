// NSScreen reports frames in Cocoa space: origin at the bottom-left of the
// primary display, Y growing upward. AppleScript window bounds are Carbon
// space: origin at the top-left of the primary display, Y growing downward.
export type CocoaFrame = { x: number; y: number; width: number; height: number };
export type Display = { index: number; name: string; builtIn: boolean; main: boolean; frame: CocoaFrame; bounds: [number, number, number, number] };
export function cocoaToCarbon(frame: CocoaFrame, primaryHeight: number): [number, number, number, number] {
  const top = primaryHeight - (frame.y + frame.height);
  return [Math.round(frame.x), Math.round(top), Math.round(frame.x + frame.width), Math.round(top + frame.height)];
}
const builtInName = /built-?in|retina|color lcd/i;
export function describeDisplays(raw: { name: string; frame: CocoaFrame }[]): Display[] {
  // NSScreen.screens[0] is always the primary display, the one holding the menu bar origin.
  const primaryHeight = raw[0]?.frame.height ?? 0;
  return raw.map((screen, index) => ({ index, name: screen.name || `Display ${index + 1}`, builtIn: builtInName.test(screen.name), main: index === 0, frame: screen.frame, bounds: cocoaToCarbon(screen.frame, primaryHeight) }));
}
export const displayPhrase = (display: Display) => display.builtIn ? 'on your laptop' : `on your ${display.name}`;
// Links go to a display the user is not looking at: the first external one
// that is not the primary, otherwise any non-primary, otherwise the primary.
export function linkDisplay(displays: Display[]) {
  return displays.find(d => !d.main && !d.builtIn) ?? displays.find(d => !d.main) ?? displays[0];
}
// A dedicated window inset from the display edges, below the menu bar.
export function windowBounds(display: Display): [number, number, number, number] {
  const [left, top, right, bottom] = display.bounds, inset = 40, menu = display.main ? 25 : 0;
  return [left + inset, top + menu + inset, right - inset, bottom - inset];
}
