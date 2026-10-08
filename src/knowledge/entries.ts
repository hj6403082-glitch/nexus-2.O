export type LocalEntry = { id: string; title: string; detail: string };

export function parseEntries(raw: string | null): LocalEntry[] {
  if (raw === null) return [];
  const value: unknown = JSON.parse(raw);
  if (!Array.isArray(value) || !value.every(entry => entry !== null && typeof entry === 'object' && typeof entry.id === 'string' && typeof entry.title === 'string' && typeof entry.detail === 'string')) {
    throw new Error('Saved entries have an unsupported format.');
  }
  return value;
}
