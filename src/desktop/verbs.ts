// The complete desktop surface. Shared by the server bridge and the browser,
// so it must stay free of Node imports. Adding a verb here is a type error in
// the bridge's handler table and the launcher's label table until both exist.
export const verbs = ['apps', 'displays', 'launch', 'quit', 'hide-others', 'website', 'media', 'volume', 'screenshot', 'clipboard-read', 'clipboard-write', 'lock-screen', 'sleep-display', 'focus', 'note', 'reminder'] as const;
export type DesktopVerb = typeof verbs[number];
export type DesktopRequest = { verb: DesktopVerb; value?: string };
export const mediaActions = ['playpause', 'play', 'pause', 'next', 'previous'] as const;
export type MediaAction = typeof mediaActions[number];
export const verbLabels: Record<DesktopVerb, string> = {
  apps: 'List installed apps', displays: 'List displays', launch: 'Launch app', quit: 'Quit app gracefully', 'hide-others': 'Hide other apps',
  website: 'Open website window', media: 'Media: play / pause / next / previous', volume: 'Set volume 0–100', screenshot: 'Capture screen to Desktop',
  'clipboard-read': 'Read clipboard', 'clipboard-write': 'Write clipboard', 'lock-screen': 'Lock screen', 'sleep-display': 'Sleep display',
  focus: 'Do Not Disturb on / off', note: 'Create note', reminder: 'Create reminder',
};
// Verbs that need no value can be offered as one-step launcher actions.
export const valueless: readonly DesktopVerb[] = ['apps', 'displays', 'hide-others', 'screenshot', 'clipboard-read', 'lock-screen', 'sleep-display'];
