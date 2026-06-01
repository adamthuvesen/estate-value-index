/**
 * Tests for the fetch-listing route's hardening: URL validation, upstream
 * timeout (504), and streaming body-size cap (502).
 */

import { NextRequest } from 'next/server';
import { POST } from '../route';

const VALID_URL = 'https://booli.se/annons/123';

function makeRequest(body: unknown): NextRequest {
  return new NextRequest('http://localhost/api/fetch-listing', {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
}

const realFetch = global.fetch;

afterEach(() => {
  global.fetch = realFetch;
  jest.useRealTimers();
});

describe('POST /api/fetch-listing — hardening', () => {
  it('rejects userinfo bypass with HTTP 400 before fetching', async () => {
    const fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await POST(makeRequest({ url: 'https://booli.se@evil.com/annons/123' }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects non-Booli host with HTTP 400 before fetching', async () => {
    const fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await POST(makeRequest({ url: 'https://example.com/annons/123' }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('rejects valid host but unrecognised path with HTTP 400', async () => {
    const fetchMock = jest.fn();
    global.fetch = fetchMock as unknown as typeof fetch;

    const res = await POST(makeRequest({ url: 'https://booli.se/profil/me' }));

    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('returns HTTP 504 when the upstream fetch is aborted on timeout', async () => {
    // Verify that when the upstream `fetch` is aborted (which is what the
    // route's 10s setTimeout triggers in production), the route maps the
    // resulting AbortError to HTTP 504. We simulate the abort by having the
    // mock receive the AbortController signal, fire it synchronously, and
    // reject with an AbortError — the same shape Node's fetch produces when
    // the signal trips. We also assert that the route did pass a signal.
    let capturedSignal: AbortSignal | undefined;
    global.fetch = jest.fn((_url, init?: RequestInit) => {
      capturedSignal = init?.signal ?? undefined;
      const err = new Error('The user aborted a request.');
      err.name = 'AbortError';
      return Promise.reject(err);
    }) as unknown as typeof fetch;

    const res = await POST(makeRequest({ url: VALID_URL }));

    expect(capturedSignal).toBeInstanceOf(AbortSignal);
    expect(res.status).toBe(504);
    const body = (await res.json()) as { error: string };
    expect(body.error.toLowerCase()).toContain('timeout');
  });

  it('schedules a timeout (setTimeout) before issuing the upstream fetch', async () => {
    // Belt-and-braces: confirm the route arms a setTimeout when it fetches.
    // This catches a regression where the AbortController/timeout pairing
    // gets dropped without a 504 test having to wait 10s.
    const setTimeoutSpy = jest.spyOn(global, 'setTimeout');
    global.fetch = jest.fn(async () => new Response('ok', { status: 404 })) as unknown as typeof fetch;

    await POST(makeRequest({ url: VALID_URL }));

    const armedTenSecondTimeout = setTimeoutSpy.mock.calls.some(
      ([, delay]) => delay === 10_000
    );
    expect(armedTenSecondTimeout).toBe(true);
    setTimeoutSpy.mockRestore();
  });

  it('returns HTTP 502 when the streaming body exceeds the 5MB cap', async () => {
    // Build a streamed body that yields 6MB total in 1MB chunks.
    const chunk = new Uint8Array(1024 * 1024); // 1MB
    let yielded = 0;
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        if (yielded >= 6) {
          controller.close();
          return;
        }
        yielded += 1;
        controller.enqueue(chunk);
      },
    });

    const response = new Response(stream, { status: 200 });
    global.fetch = jest.fn(async () => response) as unknown as typeof fetch;

    const res = await POST(makeRequest({ url: VALID_URL }));

    expect(res.status).toBe(502);
    const body = (await res.json()) as { error: string };
    expect(body.error.toLowerCase()).toContain('too large');
  });

  it('returns HTTP 502 when the upstream returns a non-OK status', async () => {
    global.fetch = jest.fn(async () => new Response('not found', { status: 404 })) as unknown as typeof fetch;

    const res = await POST(makeRequest({ url: VALID_URL }));

    expect(res.status).toBe(502);
  });
});
