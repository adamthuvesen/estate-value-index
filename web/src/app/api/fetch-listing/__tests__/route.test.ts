/**
 * Tests for the fetch-listing route: URL validation, and prefill by dataset
 * lookup (Booli is Cloudflare-gated, so there is no live fetch — a listing we
 * hold is prefilled, one we don't returns a clear manual-entry message).
 */

import { NextRequest } from 'next/server';
import type { ValueProperty } from '@/lib/value-finder-types';

const getValueAnalysisData = jest.fn();
jest.mock('@/lib/value-analysis-cache', () => ({
  getValueAnalysisData: () => getValueAnalysisData(),
}));

import { POST } from '../route';

const VALID_URL = 'https://booli.se/annons/123';

function makeRequest(body: unknown): NextRequest {
  return new NextRequest('http://localhost/api/fetch-listing', {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'content-type': 'application/json' },
  });
}

function property(overrides: Partial<ValueProperty> = {}): ValueProperty {
  return {
    listing_id: '123',
    url: 'https://www.booli.se/annons/123',
    address: 'Testgatan 1',
    area: 'sodermalm',
    municipality: 'Stockholm',
    living_area: 54,
    rooms: 2,
    property_type: 'Lägenhet',
    construction_year: 1939,
    monthly_fee: 4216,
    floor: 3,
    elevator: true,
    balcony: true,
    sold_price: 4_000_000,
    predicted_price: 4_500_000,
    prediction_delta_absolute: 500_000,
    prediction_delta_percentage: 12.5,
    is_undervalued: true,
    value_score: 90,
    value_tier: 'Excellent Value',
    sold_date: '2025-05-26',
    days_on_market: 59,
    listing_price: 3_900_000,
    price_per_sqm: 72_000,
    ...overrides,
  };
}

afterEach(() => {
  getValueAnalysisData.mockReset();
});

describe('POST /api/fetch-listing', () => {
  it('rejects userinfo bypass with HTTP 400 before any lookup', async () => {
    const res = await POST(makeRequest({ url: 'https://booli.se@evil.com/annons/123' }));

    expect(res.status).toBe(400);
    expect(getValueAnalysisData).not.toHaveBeenCalled();
  });

  it('rejects non-Booli host with HTTP 400', async () => {
    const res = await POST(makeRequest({ url: 'https://example.com/annons/123' }));

    expect(res.status).toBe(400);
    expect(getValueAnalysisData).not.toHaveBeenCalled();
  });

  it('rejects a valid host but unrecognised path with HTTP 400', async () => {
    const res = await POST(makeRequest({ url: 'https://booli.se/profil/me' }));

    expect(res.status).toBe(400);
    expect(getValueAnalysisData).not.toHaveBeenCalled();
  });

  it('returns HTTP 400 when the url field is missing', async () => {
    const res = await POST(makeRequest({}));

    expect(res.status).toBe(400);
    expect(getValueAnalysisData).not.toHaveBeenCalled();
  });

  it('prefills from the dataset when the listing is present', async () => {
    getValueAnalysisData.mockResolvedValue({ properties: [property()] });

    const res = await POST(makeRequest({ url: VALID_URL }));

    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toMatchObject({
      listing_id: '123',
      listing_price: 3_900_000,
      living_area: 54,
      rooms: 2,
      monthly_fee: 4216,
      construction_year: 1939,
      property_type: 'Lägenhet',
      area: 'sodermalm',
      floor: 3,
      elevator: true,
      balcony: true,
    });
    expect(body.error).toBeUndefined();
  });

  it('returns HTTP 404 with a manual-entry message when the listing is absent', async () => {
    getValueAnalysisData.mockResolvedValue({ properties: [property({ listing_id: '999' })] });

    const res = await POST(makeRequest({ url: VALID_URL }));

    expect(res.status).toBe(404);
    const body = (await res.json()) as { error: string };
    expect(body.error.toLowerCase()).toContain('manually');
  });

  it('returns HTTP 503 when the dataset cannot be loaded', async () => {
    getValueAnalysisData.mockRejectedValue(new Error('file missing'));

    const res = await POST(makeRequest({ url: VALID_URL }));

    expect(res.status).toBe(503);
    const body = (await res.json()) as { error: string };
    expect(body.error.toLowerCase()).toContain('manually');
  });
});
