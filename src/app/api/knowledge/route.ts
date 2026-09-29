import { localRequestAllowed } from '@/ai/server';
export const dynamic = 'force-dynamic';
async function json(url: string) {
  const response = await fetch(url, { signal: AbortSignal.timeout(12000), next: { revalidate: 300 } });
  if (!response.ok) throw new Error('The data provider is temporarily unavailable.');
  return response.json();
}
export async function GET(request: Request) {
  if (!localRequestAllowed(request, false)) return Response.json({ error: 'Local requests only.' }, { status: 403 });
  const params = new URL(request.url).searchParams;
  try {
    if (params.get('module') === 'weather') {
      const city = params.get('city')?.trim();
      if (!city || city.length > 100) return Response.json({ error: 'Enter a city name.' }, { status: 400 });
      const locations = await json(`https://geocoding-api.open-meteo.com/v1/search?name=${encodeURIComponent(city)}&count=1&language=en&format=json`);
      const place = locations.results?.[0];
      if (!place) return Response.json({ error: 'No city found. Try adding the region.' }, { status: 404 });
      const data = await json(`https://api.open-meteo.com/v1/forecast?latitude=${place.latitude}&longitude=${place.longitude}&current=temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m&daily=temperature_2m_max,temperature_2m_min&forecast_days=5&timezone=auto`);
      return Response.json({ place: `${place.name}, ${place.country}`, current: data.current, daily: data.daily, source: 'Open-Meteo', sourceUrl: 'https://open-meteo.com/', fetchedAt: new Date().toISOString() });
    }
    if (params.get('module') === 'news') {
      const ids: number[] = await json('https://hacker-news.firebaseio.com/v0/topstories.json');
      const items = await Promise.all(ids.slice(0, 8).map(id => json(`https://hacker-news.firebaseio.com/v0/item/${id}.json`)));
      return Response.json({ items: items.filter(i => i && !i.deleted && !i.dead).map(i => ({ id: i.id, title: i.title, score: i.score, time: i.time, url: /^https?:\/\//.test(i.url ?? '') ? i.url : `https://news.ycombinator.com/item?id=${i.id}` })), source: 'Hacker News', sourceUrl: 'https://news.ycombinator.com/', fetchedAt: new Date().toISOString() });
    }
    return Response.json({ error: 'Unknown data module.' }, { status: 400 });
  } catch { return Response.json({ error: 'The provider could not be reached. Check your connection and retry.' }, { status: 502 }); }
}
