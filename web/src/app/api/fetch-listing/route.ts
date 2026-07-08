import { NextRequest, NextResponse } from 'next/server';
import { extractListingId, type ParsedBooliListing } from '@/lib/booli-listing-parser';
import { validateBooliUrl } from '@/lib/booli-url';
import { titleCaseArea } from '@/lib/format';
import { getValueAnalysisData } from '@/lib/value-analysis-cache';
import type { ValueProperty } from '@/lib/value-finder-types';

export const runtime = 'nodejs';

// Booli sits behind Cloudflare, which serves a 403 challenge to any plain
// server-side fetch — and hardest of all from a datacenter IP like Cloud Run's.
// Live-scraping the page can't work here. Instead we prefill from our own
// analyzed dataset when we have the listing, and tell the user to fill in the
// fields by hand when we don't.

function toPrefill(property: ValueProperty, sourceUrl: string): ParsedBooliListing {
  return {
    listing_id: property.listing_id,
    listing_price: property.listing_price,
    living_area: property.living_area ?? null,
    rooms: property.rooms ?? null,
    monthly_fee: property.monthly_fee ?? null,
    construction_year: property.construction_year,
    days_on_market: property.days_on_market,
    property_type: property.property_type || 'Lägenhet',
    municipality: property.municipality || 'Stockholm',
    // The dataset's area field is an ASCII slug (e.g. "bromma_alsten"); title-case
    // it here so the predictor's Area dropdown doesn't show a raw slug next to
    // properly-cased options. normalize_area_for_model re-derives the slug
    // server-side before scoring, so the display transform is cosmetic-only.
    area: property.area ? titleCaseArea(property.area) : null,
    floor: property.floor,
    elevator: property.elevator,
    balcony: property.balcony,
    latitude: property.latitude ?? null,
    longitude: property.longitude ?? null,
    source_url: property.url ?? sourceUrl,
  };
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

    let data;
    try {
      data = await getValueAnalysisData();
    } catch (loadErr) {
      console.error('Listing prefill: dataset load failed', loadErr);
      return NextResponse.json(
        { error: 'Listing data is unavailable right now. Enter the details manually below.' },
        { status: 503 }
      );
    }

    const match = data.properties.find((property) => property.listing_id === listingId);
    if (!match) {
      return NextResponse.json(
        {
          error:
            'This listing isn’t in our dataset, and Booli blocks automated fetches. Enter the details manually below.',
        },
        { status: 404 }
      );
    }

    return NextResponse.json(toPrefill(match, validated.toString()));
  } catch (err) {
    console.error('Listing fetch error', err);
    return NextResponse.json(
      { error: 'Unexpected error while looking up listing data' },
      { status: 500 }
    );
  }
}
