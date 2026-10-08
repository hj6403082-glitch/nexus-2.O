import test from 'node:test';
import assert from 'node:assert/strict';
import { GET } from '../src/app/api/accounts/route';

test('standings select overall results and reject unsupported league paths', async () => {
  const originalFetch = globalThis.fetch, originalToken = process.env.FOOTBALL_DATA_TOKEN;
  process.env.FOOTBALL_DATA_TOKEN = 'test-token';
  let calls = 0;
  globalThis.fetch = async (input, init) => {
    calls++;
    assert.equal(String(input), 'https://api.football-data.org/v4/competitions/PL/standings');
    assert.equal((init?.headers as Record<string, string>)['X-Auth-Token'], 'test-token');
    return Response.json({ competition: { name: 'Test league' }, standings: [
      { type: 'HOME', table: [] },
      { type: 'TOTAL', table: [{ position: 1, team: { id: 7, name: 'Test team' }, playedGames: 3, won: 2, draw: 1, lost: 0, points: 7, goalDifference: 4 }] },
    ] });
  };
  try {
    const response = await GET(new Request('http://127.0.0.1:3001/api/accounts?module=sports&view=standings&competition=PL', { headers: { host: '127.0.0.1:3001' } }));
    assert.equal(response.status, 200);
    const result = await response.json();
    assert.equal(result.standings.length, 1);
    assert.equal(result.standings[0].points, 7);
    assert.equal(JSON.stringify(result).includes('test-token'), false);
    const invalid = await GET(new Request('http://127.0.0.1:3001/api/accounts?module=sports&view=standings&competition=../matches', { headers: { host: '127.0.0.1:3001' } }));
    assert.equal(invalid.status, 400);
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = originalFetch;
    if (originalToken === undefined) delete process.env.FOOTBALL_DATA_TOKEN; else process.env.FOOTBALL_DATA_TOKEN = originalToken;
  }
});
