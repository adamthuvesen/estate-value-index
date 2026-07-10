import { NextRequest, NextResponse } from 'next/server';
import { coerceBool } from '@/lib/booli-listing-parser';
import {
  estimateRange,
  estimateRangeFactorsFromArtifact,
  type EstimateRangeFactors,
} from '@/lib/estimate-range';

type PredictionRequestBody = {
  listing_id?: unknown;
  listing_price?: unknown;
  living_area?: unknown;
  rooms?: unknown;
  monthly_fee?: unknown;
  days_on_market?: unknown;
  construction_year?: unknown;
  property_type?: unknown;
  municipality?: unknown;
  area?: unknown;
  model?: unknown;
  floor?: unknown;
  elevator?: unknown;
  balcony?: unknown;
  latitude?: unknown;
  longitude?: unknown;
};

type PredictionPayload = {
  listing_price: number | null;
  living_area: number;
  rooms: number;
  monthly_fee: number;
  days_on_market: number;
  construction_year: number;
  municipality: string;
  property_type: string;
  area: string;
  model: string;
  floor?: number | null;
  elevator?: boolean | null;
  balcony?: boolean | null;
  latitude?: number | null;
  longitude?: number | null;
};

type FastAPIResponse = {
  predicted_price: number;
  model_used: string;
  model_type: string;
  model_id: string;
  requires_listing_price: boolean;
  status: string;
  estimate_range_factors?: unknown;
};

const API_BASE_URL = process.env.PREDICTION_API_URL || 'http://localhost:8000';
const API_TIMEOUT = 30000; // 30 seconds
const PRICE_RANGE_STEP = 100_000;
const ALLOWED_MODELS = ['auto', 'no_list_price', 'with_list_price'] as const;
const SAFE_UPSTREAM_STATUSES = new Set([400, 422, 429, 503]);

class ValidationError extends Error {}

function isRecord(value: unknown): value is PredictionRequestBody {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function badRequest(message: string) {
  return NextResponse.json({ error: message }, { status: 400 });
}

function parseJsonBody(value: unknown): PredictionRequestBody {
  if (!isRecord(value)) {
    throw new ValidationError('Request body must be a JSON object');
  }
  return value;
}

function isEmptyInput(value: unknown): boolean {
  return value === undefined || value === null || (typeof value === 'string' && value.trim() === '');
}

function parseFiniteNumber(
  body: PredictionRequestBody,
  field: keyof PredictionRequestBody,
  options: {
    required?: boolean;
    defaultValue?: number;
    gt?: number;
    ge?: number;
    min?: number;
    max?: number;
    integer?: boolean;
  } = {},
): number | null {
  const rawValue = body[field];
  if (isEmptyInput(rawValue)) {
    if (options.required) {
      throw new ValidationError(`Missing required field: ${field}`);
    }
    return options.defaultValue ?? null;
  }

  if (typeof rawValue !== 'number' && typeof rawValue !== 'string') {
    throw new ValidationError(`${field} must be a number`);
  }

  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed)) {
    throw new ValidationError(`${field} must be a finite number`);
  }
  if (options.integer && !Number.isInteger(parsed)) {
    throw new ValidationError(`${field} must be an integer`);
  }
  if (options.gt !== undefined && parsed <= options.gt) {
    throw new ValidationError(`${field} must be greater than ${options.gt}`);
  }
  if (options.ge !== undefined && parsed < options.ge) {
    throw new ValidationError(`${field} must be at least ${options.ge}`);
  }
  if (options.min !== undefined && parsed < options.min) {
    throw new ValidationError(`${field} must be at least ${options.min}`);
  }
  if (options.max !== undefined && parsed > options.max) {
    throw new ValidationError(`${field} must be at most ${options.max}`);
  }

  return parsed;
}

function parseStringField(
  body: PredictionRequestBody,
  field: keyof PredictionRequestBody,
  defaultValue: string,
  maxLength = 160,
): string {
  const rawValue = body[field];
  if (isEmptyInput(rawValue)) return defaultValue;
  if (typeof rawValue !== 'string') {
    throw new ValidationError(`${field} must be a string`);
  }
  const trimmed = rawValue.trim();
  if (!trimmed) return defaultValue;
  if (trimmed.length > maxLength) {
    throw new ValidationError(`${field} must be at most ${maxLength} characters`);
  }
  return trimmed;
}

function parseOptionalBoolean(value: unknown): boolean | null {
  if (value === '' || value === null || value === undefined) return null;
  const parsed = coerceBool(value);
  if (parsed === null) {
    throw new ValidationError('elevator and balcony must be true, false, or empty');
  }
  return parsed;
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

function parsePredictionPayload(body: PredictionRequestBody): {
  listingId: string;
  payload: PredictionPayload;
} {
  const modelRaw = parseStringField(body, 'model', 'auto', 40).toLowerCase();
  if (!ALLOWED_MODELS.includes(modelRaw as (typeof ALLOWED_MODELS)[number])) {
    throw new ValidationError(`model must be one of: ${ALLOWED_MODELS.join(', ')}`);
  }

  const listingIdRaw = body.listing_id;
  const listingId =
    typeof listingIdRaw === 'string' && listingIdRaw.trim() ? listingIdRaw.trim() : 'unknown';

  return {
    listingId,
    payload: {
      listing_price: parseFiniteNumber(body, 'listing_price', { gt: 0 }),
      living_area: parseFiniteNumber(body, 'living_area', { required: true, gt: 0 }) ?? 0,
      rooms: parseFiniteNumber(body, 'rooms', { defaultValue: 2, gt: 0 }) ?? 2,
      monthly_fee: parseFiniteNumber(body, 'monthly_fee', { defaultValue: 3000, ge: 0 }) ?? 3000,
      days_on_market:
        parseFiniteNumber(body, 'days_on_market', { defaultValue: 30, ge: 0 }) ?? 30,
      construction_year:
        parseFiniteNumber(body, 'construction_year', {
          defaultValue: 1970,
          integer: true,
          min: 1800,
          max: 2100,
        }) ?? 1970,
      municipality: parseStringField(body, 'municipality', 'Stockholm', 120),
      property_type: parseStringField(body, 'property_type', 'Lägenhet', 80),
      area: parseStringField(body, 'area', 'Södermalm', 160),
      model: modelRaw,
      floor: parseFiniteNumber(body, 'floor', { min: -20, max: 200 }),
      elevator: parseOptionalBoolean(body.elevator),
      balcony: parseOptionalBoolean(body.balcony),
      latitude: parseFiniteNumber(body, 'latitude', { min: -90, max: 90 }),
      longitude: parseFiniteNumber(body, 'longitude', { min: -180, max: 180 }),
    },
  };
}

function upstreamErrorMessage(status: number): string {
  if (status === 429) return 'Prediction service rate limit exceeded.';
  if (status === 503) return 'Prediction service unavailable.';
  if (status === 400 || status === 422) return 'Prediction request was rejected.';
  return 'Prediction service returned an unexpected error.';
}

// Lock to the Node runtime so localhost `fetch` to the FastAPI sidecar works.
export const runtime = 'nodejs';

export async function POST(request: NextRequest) {
  try {
    let parsedBody: PredictionRequestBody;
    try {
      parsedBody = parseJsonBody(await request.json());
    } catch (error) {
      if (error instanceof ValidationError) {
        return badRequest(error.message);
      }
      return badRequest('Request body must be valid JSON');
    }

    let parsedPayload: { listingId: string; payload: PredictionPayload };
    try {
      parsedPayload = parsePredictionPayload(parsedBody);
    } catch (error) {
      if (error instanceof ValidationError) {
        return badRequest(error.message);
      }
      throw error;
    }

    const inputData = parsedPayload.payload;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), API_TIMEOUT);

    try {
      const response = await fetch(`${API_BASE_URL}/predict`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(inputData),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
        console.error('[PREDICT] API error:', { status: response.status, errorData });
        const status = SAFE_UPSTREAM_STATUSES.has(response.status) ? response.status : 502;
        return NextResponse.json({ error: upstreamErrorMessage(response.status) }, { status });
      }

      const prediction = (await response.json()) as FastAPIResponse;
      const predictedPrice = Math.round(prediction.predicted_price);
      const factors =
        estimateRangeFactorsFromArtifact(prediction.estimate_range_factors) ?? undefined;

      return NextResponse.json({
        listing_id: parsedPayload.listingId,
        predicted_price: predictedPrice,
        ...predictionRange(predictedPrice, factors),
        estimate_range_factors: factors ?? null,
        model_used: prediction.model_used,
        model_id: prediction.model_id,
        model_type: prediction.model_type,
        requires_listing_price: prediction.requires_listing_price,
        status: prediction.status,
        input_data: inputData,
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
