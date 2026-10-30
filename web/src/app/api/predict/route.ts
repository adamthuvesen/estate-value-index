import { NextRequest, NextResponse } from 'next/server';
import {
  estimateRange,
  estimateRangeFactorsFromArtifact,
  type EstimateRangeFactors,
} from '@/lib/estimate-range';
import type { PredictionResponse } from '@/lib/generated/api-types';

const API_BASE_URL = process.env.PREDICTION_API_URL || 'http://localhost:8000';
const API_TIMEOUT = 30000; // 30 seconds
const PRICE_RANGE_STEP = 100_000;
const SAFE_UPSTREAM_STATUSES = new Set([400, 422, 429, 503]);

type JsonObject = Record<string, unknown>;

function isRecord(value: unknown): value is JsonObject {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function badRequest(message: string) {
  return NextResponse.json({ error: message }, { status: 400 });
}

/**
 * Turn the form body into the FastAPI request. FastAPI validates every field and
 * applies the defaults; here only form blanks become absent fields.
 */
function toPredictionRequest(body: JsonObject): JsonObject {
  const request: JsonObject = {};
  for (const [field, raw] of Object.entries(body)) {
    if (field === 'listing_id') continue;
    const value = typeof raw === 'string' ? raw.trim() : raw;
    if (value === undefined || value === null || value === '') continue;
    request[field] = value;
  }
  return request;
}

function predictionRange(predictedPrice: number, factors?: EstimateRangeFactors) {
  // estimateRange is the single source of truth for the displayed window: an
  // empirical per-bucket q35/q65 interval. The client recomputes from
  // predicted_price with the same factors, so both agree.
  const range = estimateRange(predictedPrice, factors);
  return {
    rounded_predicted_price: range.center,
    price_range_min: Math.max(0, range.min),
    price_range_max: range.max,
    price_range_step: PRICE_RANGE_STEP,
  };
}

function rejectedFields(errorData: unknown): string[] {
  if (!isRecord(errorData) || !Array.isArray(errorData.detail)) return [];
  const fields = errorData.detail.flatMap((issue: unknown) => {
    if (!isRecord(issue) || !Array.isArray(issue.loc)) return [];
    const field = issue.loc[issue.loc.length - 1];
    return typeof field === 'string' ? [field] : [];
  });
  return [...new Set(fields)];
}

function upstreamErrorMessage(status: number, errorData: unknown): string {
  if (status === 429) return 'Prediction service rate limit exceeded.';
  if (status === 503) return 'Prediction service unavailable.';
  if (status === 422) {
    const fields = rejectedFields(errorData);
    return fields.length
      ? `Check these fields: ${fields.join(', ')}.`
      : 'Prediction request was rejected.';
  }
  if (status === 400) return 'Prediction request was rejected.';
  return 'Prediction service returned an unexpected error.';
}

// Lock to the Node runtime so localhost `fetch` to the FastAPI sidecar works.
export const runtime = 'nodejs';

export async function POST(request: NextRequest) {
  try {
    let body: unknown;
    try {
      body = await request.json();
    } catch {
      return badRequest('Request body must be valid JSON');
    }
    if (!isRecord(body)) {
      return badRequest('Request body must be a JSON object');
    }
    const listingId =
      typeof body.listing_id === 'string' && body.listing_id.trim()
        ? body.listing_id.trim()
        : 'unknown';

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);

    try {
      const response = await fetch(`${API_BASE_URL}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(toPredictionRequest(body)),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        console.error('[PREDICT] API error:', { status: response.status, errorData });
        const status = SAFE_UPSTREAM_STATUSES.has(response.status) ? response.status : 502;
        return NextResponse.json(
          { error: upstreamErrorMessage(response.status, errorData) },
          { status },
        );
      }

      const prediction = (await response.json()) as PredictionResponse;
      const predictedPrice = Math.round(prediction.predicted_price);
      const factors =
        estimateRangeFactorsFromArtifact(prediction.estimate_range_factors) ?? undefined;

      return NextResponse.json({
        listing_id: listingId,
        predicted_price: predictedPrice,
        ...predictionRange(predictedPrice, factors),
        estimate_range_factors: factors ?? null,
        model_used: prediction.model_used,
        model_id: prediction.model_id,
        model_type: prediction.model_type,
        requires_listing_price: prediction.requires_listing_price,
        status: prediction.status,
        input_data: prediction.input,
        confidence: 'medium',
        timestamp: new Date().toISOString()
      });

    } catch (fetchError) {
      clearTimeout(timeoutId);

      if (fetchError instanceof Error) {
        if (fetchError.name === 'AbortError') {
          return NextResponse.json({ error: 'Prediction request timed out' }, { status: 504 });
        }
        throw fetchError;
      }
      throw new Error('Failed to fetch prediction');
    }

  } catch (error) {
    console.error('Prediction error:', error);

    const errorMessage = error instanceof Error ? error.message : 'Failed to generate prediction';

    if (errorMessage.includes('ECONNREFUSED') || errorMessage.includes('fetch failed')) {
      return NextResponse.json(
        { error: 'Prediction service unavailable. Please ensure the FastAPI server is running.' },
        { status: 503 }
      );
    }
    
    console.error('Prediction error:', errorMessage);
    return NextResponse.json({ error: 'Failed to generate prediction' }, { status: 500 });
  }
}

export async function GET() {
  return NextResponse.json({
    message: 'Property Price Prediction API',
    usage: 'POST to this endpoint with property details to get price predictions',
    required_fields: ['living_area'],
    optional_fields: ['listing_price', 'rooms', 'monthly_fee', 'days_on_market', 'construction_year', 'property_type', 'municipality', 'area', 'model', 'floor', 'elevator', 'balcony', 'latitude', 'longitude'],
    allowed_models: ['auto', 'no_list_price', 'with_list_price'],
    note: 'Feature engineering is handled by the prediction service; send raw property fields.',
    backend: 'FastAPI',
    api_url: API_BASE_URL
  });
}
