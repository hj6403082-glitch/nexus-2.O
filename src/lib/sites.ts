// Well-known websites the launcher and voice can name. Personal destinations
// are not here: they resolve from the live account feed (see knowledge/destinations).
export const sites = [
  { name: 'YouTube', url: 'https://www.youtube.com/' }, { name: 'GitHub', url: 'https://github.com/' }, { name: 'Gmail', url: 'https://mail.google.com/' },
  { name: 'Google', url: 'https://www.google.com/' }, { name: 'Google Calendar', url: 'https://calendar.google.com/' }, { name: 'Google Drive', url: 'https://drive.google.com/' },
  { name: 'Instagram', url: 'https://www.instagram.com/' }, { name: 'X', url: 'https://x.com/' }, { name: 'Reddit', url: 'https://www.reddit.com/' },
  { name: 'Hacker News', url: 'https://news.ycombinator.com/' }, { name: 'Wikipedia', url: 'https://www.wikipedia.org/' }, { name: 'LinkedIn', url: 'https://www.linkedin.com/' },
  { name: 'Netflix', url: 'https://www.netflix.com/' }, { name: 'Figma', url: 'https://www.figma.com/' }, { name: 'Notion', url: 'https://www.notion.so/' },
] as const;
export const siteByName = (name: string) => sites.find(site => site.name.toLowerCase() === name.trim().toLowerCase());
// A bare domain such as "github.com" or "docs.python.org/3" becomes an HTTPS URL.
export function websiteUrl(text: string) {
  const value = text.trim();
  if (/^https?:\/\//i.test(value)) { try { const url = new URL(value); return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null; } catch { return null; } }
  if (!/^[a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,}(?:\/\S*)?$/i.test(value)) return null;
  try { return new URL(`https://${value}`).href; } catch { return null; }
}
