import { NextRequest, NextResponse } from 'next/server';
import {
  extractListingId,
  parseBooliListingFromHtml,
} from '@/lib/booli-listing-parser';
import { validateBooliUrl } from '@/lib/booli-url';

export const runtime = 'nodejs';

const UPSTREAM_TIMEOUT_MS = 10_000;
const MAX_RESPONSE_BYTES = 5 * 1024 * 1024;

class ResponseTooLargeError extends Error {
  constructor() {
    super('response too large');
    this.name = 'ResponseTooLargeError';
  }
}

async function readBodyWithCap(response: Response, maxBytes: number): Promise<string> {
  const reader = response.body?.getReader();
  if (!reader) {
    return response.text();
  }

  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      if (!value) continue;
      total += value.byteLength;
      if (total > maxBytes) {
        await reader.cancel();
        throw new ResponseTooLargeError();
      }
      chunks.push(value);
    }
  } finally {
    try {
      reader.releaseLock();
    } catch {
      /* lock already released */
    }
  }

  const combined = new Uint8Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    combined.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder('utf-8').decode(combined);
}

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json().catch(() => ({}))) as { url?: unknown };
    const url = typeof body.url === 'string' ? body.url.trim() : '';

    if (!url) {
      return NextResponse.json({ error: 'Missing required field: url' }, { status: 400 });
    }

    const validated = validateBooliUrl(url);
    if (!(validated instanceof URL)) {
      return NextResponse.json(
        { error: `Invalid Booli listing URL: ${validated.error}` },
        { status: 400 }
      );
    }

    const listingId = extractListingId(validated);
    if (!listingId) {
      return NextResponse.json(
        {
          error:
            'Invalid Booli listing URL. Supported formats: /annons/123456, /bostad/123456',
        },
        { status: 400 }
      );
    }

    const upstreamUrl = validated.toString();
    const controller = new AbortController();
    const timeout = setTimeout(
      () => controller.abort(new Error('upstream timeout')),
      UPSTREAM_TIMEOUT_MS
    );

    let response: Response;
    let html: string;
    try {
      response = await fetch(upstreamUrl, {
        headers: {
          'User-Agent':
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:128.0) Gecko/20100101 Firefox/128.0',
          Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
          'Accept-Language': 'sv-SE,sv;q=0.9,en-US;q=0.8,en;q=0.7',
        },
        cache: 'no-store',
        signal: controller.signal,
      });

      if (!response.ok) {
        return NextResponse.json(
          { error: `Failed to load listing (status ${response.status})` },
          { status: 502 }
        );
      }

      html = await readBodyWithCap(response, MAX_RESPONSE_BYTES);
    } catch (fetchErr) {
      if (fetchErr instanceof ResponseTooLargeError) {
        return NextResponse.json(
          { error: 'Upstream response too large (>5MB cap)' },
          { status: 502 }
        );
      }
      const isAbort =
        (fetchErr instanceof Error && fetchErr.name === 'AbortError') ||
        controller.signal.aborted;
      if (isAbort) {
        return NextResponse.json(
          { error: 'Upstream timeout while fetching listing' },
          { status: 504 }
        );
      }
      throw fetchErr;
    } finally {
      clearTimeout(timeout);
    }

    const parsed = parseBooliListingFromHtml(html, listingId, upstreamUrl);
    if ('error' in parsed) {
      return NextResponse.json({ error: parsed.error }, { status: 502 });
    }

    return NextResponse.json(parsed);
  } catch (err) {
    console.error('Listing fetch error', err);
    return NextResponse.json({ error: 'Unexpected error while fetching listing data' }, { status: 500 });
  }
}
