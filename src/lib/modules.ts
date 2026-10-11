export const modules = [
  { id: 'instagram', name: 'Instagram', category: 'SOCIAL SIGNAL', subtitle: 'Your creative footprint.', icon: 'instagram', accent: '#ad9dff', phase: 3, description: 'Reach, audience growth, reels and engagement. Your personal feed will connect in the knowledge-engine phase.' },
  { id: 'stocks', name: 'Stocks', category: 'MARKET INTELLIGENCE', subtitle: 'A wider perspective.', icon: 'chart', accent: '#83a8ff', phase: 3, description: 'Portfolio, live prices, allocation and performance. Connect a market-data provider in Phase 3.' },
  { id: 'projects', name: 'Projects', category: 'CREATIVE WORKSPACE', subtitle: 'Room for your next idea.', icon: 'layers', accent: '#84c7ff', phase: 3, description: 'A spatial home for your projects, media, prompt history and repositories. Project storage arrives in Phase 3.' },
  { id: 'sports', name: 'Sports', category: 'LIVE MOMENTS', subtitle: 'Stay in the game.', icon: 'activity', accent: '#91d6ff', phase: 3, description: 'Scores, fixtures and standings will connect to a sports-data source in Phase 3.' },
  { id: 'calendar', name: 'Calendar', category: 'TIME & ATTENTION', subtitle: 'Make space for what matters.', icon: 'calendar', accent: '#a2c1ff', phase: 3, description: 'Your schedule, with context. Calendar account integration arrives in the personal-knowledge phase.' },
  { id: 'weather', name: 'Weather', category: 'OUTSIDE, BROUGHT IN', subtitle: 'Feel the atmosphere.', icon: 'cloud', accent: '#9de4ee', phase: 3, description: 'Location-based conditions and forecasts, followed by reactive weather environments.' },
  { id: 'ai', name: 'AI', category: 'CONTEXTUAL INTELLIGENCE', subtitle: 'A thought away.', icon: 'sparkles', accent: '#bab1ff', phase: 2, description: 'Streaming Gemini conversations, contextual commands and interruptible voice. This is the next development phase.' },
  { id: 'news', name: 'News', category: 'THE SIGNAL', subtitle: 'Understand what is changing.', icon: 'newspaper', accent: '#83b4ee', phase: 3, description: 'Source-linked stories and AI summaries. Live news integration arrives in Phase 3.' },
  { id: 'music', name: 'Music', category: 'YOUR FREQUENCY', subtitle: 'Set the tone.', icon: 'music', accent: '#aca8ed', phase: 3, description: 'A connected music library and playback controls will arrive with the knowledge engine.' },
  { id: 'system', name: 'System', category: 'UNDER THE SURFACE', subtitle: 'Everything in balance.', icon: 'cpu', accent: '#a4d6e6', phase: 1, description: 'Live rendering and input diagnostics with local machine telemetry.' },
] as const;
export type ModuleId = typeof modules[number]['id'];
export type NexusModule = typeof modules[number];
export const moduleById = (id: ModuleId) => modules.find(m => m.id === id)!;
export const wrapIndex = (i: number) => ((i % modules.length) + modules.length) % modules.length;
