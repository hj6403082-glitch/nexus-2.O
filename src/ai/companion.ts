// Zeno's companion layer: what makes it feel like it knows you. It remembers
// your name and what you tell it across restarts, notices the time of day and
// how long you have been away, and reads the mood of a message so the model can
// answer the way a friend would. Everything here is local and deterministic;
// the notes ride to the model as data with the newest message, never as rules.
export type Memory = { name: string | null; facts: string[]; lastChatAt: number; chats: number };
export type Mood = 'excited' | 'frustrated' | 'down' | null;
export const emptyMemory = (): Memory => ({ name: null, facts: [], lastChatAt: 0, chats: 0 });
const MAX_FACTS = 30;
const tidy = (text: string) => text.trim().replace(/\s+/g, ' ').replace(/[.!?]+$/, '').trim();
const capitalise = (name: string) => name.split(/([ '-])/).map(part => part.charAt(0).toUpperCase() + part.slice(1)).join('');
const remember = (facts: string[], fact: string) => {
  const clean = tidy(fact); if (!clean) return facts;
  const rest = facts.filter(f => f.toLowerCase() !== clean.toLowerCase());
  return [...rest, clean].slice(-MAX_FACTS);
};
// Joins a list the way people say it: "a", "a and b", "a, b and c".
const spoken = (items: string[]) => items.length < 2 ? items.join('') : `${items.slice(0, -1).join(', ')} and ${items.at(-1)}`;
// Facts are stored in the user's words; read back, they are turned to "you".
const toYou = (fact: string) => fact.replace(/\bI am\b/gi, 'you are').replace(/\bI'm\b/gi, "you're").replace(/\bI\b/g, 'you').replace(/\bmy\b/gi, 'your').replace(/\bme\b/gi, 'you').replace(/\bmine\b/gi, 'yours').replace(/\bmyself\b/gi, 'yourself');

// Explicit memory requests get an instant local answer; everything else may
// still teach Zeno something quietly (likes, dislikes, work) and then goes on
// to the model as usual.
export function learn(text: string, memory: Memory): { memory: Memory; reply: string | null } {
  const raw = tidy(text.replace(/^(?:hey\s+)?(?:zeno|nexus)[\s,:.!]*/i, '')), t = raw.toLowerCase();
  if (/^(?:forget everything|forget all about me|wipe your memory|clear your memory)$/.test(t)) return { memory: { ...emptyMemory(), chats: memory.chats, lastChatAt: memory.lastChatAt }, reply: "Done, I've wiped everything I knew about you. Fresh start." };
  if (/^(?:what do you (?:know|remember) about me|what do you remember|do you remember me)$/.test(t)) {
    const parts = [...(memory.name ? [`your name's ${memory.name}`] : []), ...memory.facts.slice(-8).map(toYou)];
    return { memory, reply: parts.length ? `Let's see. I know ${spoken(parts)}. Anything you want me to add or forget?` : "Honestly, not much yet. Tell me your name or say \"remember that\" and I'll hang on to it." };
  }
  const name = raw.match(/^(?:my name is|my name's|call me|you can call me)\s+([a-z][a-z' -]{0,30})$/i);
  if (name) { const next = capitalise(name[1].trim()); return { memory: { ...memory, name: next }, reply: `Nice to meet you properly, ${next}. I'll remember that.` }; }
  const keep = raw.match(/^(?:please )?remember (?:that )?(.{3,200})$/i);
  if (keep) return { memory: { ...memory, facts: remember(memory.facts, keep[1]) }, reply: "Got it, I'll remember that." };
  const drop = raw.match(/^forget (?:that |about )?(.{2,100})$/i);
  if (drop) {
    const needle = drop[1].toLowerCase(), facts = memory.facts.filter(f => !f.toLowerCase().includes(needle));
    const clearsName = !!memory.name && (needle === 'my name' || memory.name.toLowerCase() === needle);
    if (facts.length === memory.facts.length && !clearsName) return { memory, reply: "I didn't have anything saved about that, so we're good." };
    return { memory: { ...memory, facts, name: clearsName ? null : memory.name }, reply: "Okay, it's forgotten." };
  }
  // Quiet learning from ordinary conversation.
  let facts = memory.facts;
  for (const m of raw.matchAll(/\bI (?:really |absolutely |kinda |kind of )?(love|like|enjoy|hate|can't stand|cannot stand)\s+([^.,!?;]{2,60})/gi)) {
    const verb = m[1].toLowerCase(), what = m[2].trim();
    if (/^(?:it|that|this|to know|you)$/i.test(what)) continue;
    facts = remember(facts, `I ${verb} ${what}`);
  }
  const job = raw.match(/\bI (?:work as|work at|am studying|study)\s+([^.,!?;]{2,60})/i);
  if (job) facts = remember(facts, job[0]);
  return { memory: facts === memory.facts ? memory : { ...memory, facts }, reply: null };
}

export function readMood(text: string): Mood {
  const t = text.toLowerCase();
  if (/\b(?:ugh|argh|annoy\w*|frustrat\w*|hate this|doesn'?t work|not working|broken|wtf|so stupid|fed up|again\?!)/.test(t)) return 'frustrated';
  if (/\b(?:sad|tired|exhausted|lonely|bad day|stressed|depressed|upset|anxious|worried|rough day)\b/.test(t)) return 'down';
  if (/!{2,}|\b(?:awesome|amazing|yay|let'?s go|so excited|great news|i did it|nailed it|woo+)\b/.test(t)) return 'excited';
  return null;
}
const moodHint: Record<Exclude<Mood, null>, string> = {
  frustrated: 'They sound frustrated: be calm, brief and practical, and acknowledge it in a few words.',
  down: 'They sound a bit down: be warm and gentle, check in on them like a friend would.',
  excited: 'They sound excited: match their energy and celebrate with them.',
};

export function partOfDay(now: Date) {
  const h = now.getHours();
  return h < 5 ? 'night' : h < 12 ? 'morning' : h < 17 ? 'afternoon' : h < 21 ? 'evening' : 'night';
}
function since(ms: number) {
  const minutes = Math.round(ms / 60000);
  if (minutes < 2) return 'just now'; if (minutes < 60) return `${minutes} minutes ago`;
  const hours = Math.round(minutes / 60); if (hours < 24) return `${hours} hour${hours === 1 ? '' : 's'} ago`;
  const days = Math.round(hours / 24); return `${days} day${days === 1 ? '' : 's'} ago`;
}

// Notes for the model, sent as data with the newest message.
export function companionNotes(memory: Memory, now: Date, mood: Mood) {
  const when = `${now.toLocaleDateString('en-US', { weekday: 'long' })} ${partOfDay(now)}, ${now.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`;
  const parts = [
    memory.name ? `The user's name is ${memory.name}.` : "You don't know the user's name yet; if it comes up naturally, you can ask.",
    memory.facts.length ? `Things they've told you: ${memory.facts.slice(-12).join('; ')}.` : '',
    `It's ${when} for them.`,
    memory.lastChatAt ? `You last talked ${since(now.getTime() - memory.lastChatAt)}; this is conversation turn ${memory.chats + 1} overall.` : 'This is your first conversation.',
    mood ? moodHint[mood] : '',
    'Use these naturally when relevant; never recite them.',
  ];
  return parts.filter(Boolean).join(' ').slice(0, 1500);
}

// The panel greeting: time-aware, personal, and different after a long break.
export function greeting(memory: Memory, now: Date) {
  const part = partOfDay(now), who = memory.name ? `, ${memory.name}` : '';
  const away = memory.lastChatAt ? now.getTime() - memory.lastChatAt : 0;
  const eyebrow = part === 'night' ? 'LATE NIGHT' : `GOOD ${part.toUpperCase()}`;
  if (!memory.lastChatAt) return { eyebrow, title: `Hey${who}, I'm Zeno.`, line: "Ask me anything, tell me about yourself, or just say hi. I'll remember what matters." };
  if (away > 3 * 86400000) return { eyebrow, title: `Hey${who}, long time no see!`, line: "I missed having someone to talk to. What've you been up to?" };
  if (part === 'night') return { eyebrow, title: `Still up${who}?`, line: "I'm here. What's keeping you busy?" };
  return { eyebrow, title: `${part === 'morning' ? 'Morning' : part === 'afternoon' ? 'Hey' : 'Evening'}${who}!`, line: away > 6 * 3600000 ? 'Good to see you again. What are we getting into?' : "What's on your mind?" };
}

export function loadMemory(): Memory {
  try {
    const v = JSON.parse(localStorage.getItem('zeno-memory') || 'null');
    if (!v || typeof v !== 'object') return emptyMemory();
    return { name: typeof v.name === 'string' ? v.name.slice(0, 40) : null, facts: Array.isArray(v.facts) ? v.facts.filter((f: unknown): f is string => typeof f === 'string').map((f: string) => f.slice(0, 200)).slice(-MAX_FACTS) : [], lastChatAt: Number(v.lastChatAt) || 0, chats: Number(v.chats) || 0 };
  } catch { return emptyMemory(); }
}
export function saveMemory(memory: Memory) { try { localStorage.setItem('zeno-memory', JSON.stringify(memory)); } catch { /* storage blocked */ } }
