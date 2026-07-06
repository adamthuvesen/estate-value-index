import { NextRequest, NextResponse } from 'next/server';
import { coerceBool } from '@/lib/booli-listing-parser';

type PredictionRequestBody = {
  listing_id?: string;
  listing_price?: number | string;
  living_area?: number | string;
  rooms?: number | string;
  monthly_fee?: number | string;
  days_on_market?: number | string;
  construction_year?: number | string;
  property_type?: string;
  municipality?: string;
  area?: string;
  model?: string;
  floor?: number | string;
  elevator?: boolean | string;
  balcony?: boolean | string;
  latitude?: number | string;
  longitude?: number | string;
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
};

const API_BASE_URL = process.env.PREDICTION_API_URL || 'http://localhost:8000';
const API_TIMEOUT = 30000; // 30 seconds
const PRICE_RANGE_STEP = 100_000;

function parseOptionalBoolean(value: unknown): boolean | null {
  if (value === '' || value === null || value === undefined) return null;
  return coerceBool(value);
}

function predictionRange(predictedPrice: number, modelId: string) {
  const roundToStep = modelId === 'no_list' ? Math.ceil : Math.round;
  const roundedPrediction = roundToStep(predictedPrice / PRICE_RANGE_STEP) * PRICE_RANGE_STEP;
  return {
    rounded_predicted_price: roundedPrediction,
    price_range_min: Math.max(0, roundedPrediction - PRICE_RANGE_STEP),
    price_range_max: roundedPrediction + PRICE_RANGE_STEP,
    price_range_step: PRICE_RANGE_STEP,
  };
}

// Lock to the Node runtime so localhost `fetch` to the FastAPI sidecar works.
export const runtime = 'nodejs';

export async function POST(request: NextRequest) {
  try {
    const body = (await request.json()) as PredictionRequestBody;
    const {
      listing_id,
      listing_price,
      living_area,
      rooms,
      monthly_fee,
      days_on_market,
      construction_year,
      property_type,
      municipality,
      area,
      model,
      floor,
      elevator,
      balcony,
      latitude,
      longitude,
    } = body;

    // Validate required fields
    if (!living_area) {
      return NextResponse.json(
        { error: 'Missing required field: living_area is required' },
        { status: 400 }
      );
    }

    // Send raw features only; SimplePredictionPipeline does feature engineering server-side.
    const inputData: PredictionPayload = {
      listing_price: listing_price != null && listing_price !== '' ? Number(listing_price) : null,
      living_area: Number(living_area),
      rooms: Number(rooms ?? 2),
      monthly_fee: Number(monthly_fee ?? 3000),
      days_on_market: Number(days_on_market ?? 30),
      construction_year: Number(construction_year ?? 1970),
      municipality: municipality ?? 'Stockholm',
      property_type: property_type ?? 'Lägenhet',
      area: area ?? 'Södermalm',
      model: model ?? 'auto',
      floor: floor != null && floor !== '' ? Number(floor) : null,
      elevator: parseOptionalBoolean(elevator),
      balcony: parseOptionalBoolean(balcony),
      latitude: latitude != null && latitude !== '' ? Number(latitude) : null,
      longitude: longitude != null && longitude !== '' ? Number(longitude) : null,
    };

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
        console.error('[PREDICT] API error:', errorData);
        throw new Error(errorData.detail || `API returned ${response.status}`);
      }

      const prediction = (await response.json()) as FastAPIResponse;
      const predictedPrice = Math.round(prediction.predicted_price);

      return NextResponse.json({
        listing_id: listing_id || 'unknown',
        predicted_price: predictedPrice,
        ...predictionRange(predictedPrice, prediction.model_id),
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
          throw new Error('Prediction request timed out');
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
    
    return NextResponse.json(
      { error: errorMessage },
      { status: 500 }
    );
  }
}

export async function GET() {
  return NextResponse.json({
    message: 'Property Price Prediction API',
    usage: 'POST to this endpoint with property details to get price predictions',
    required_fields: ['living_area'],
    optional_fields: ['listing_price', 'rooms', 'monthly_fee', 'days_on_market', 'construction_year', 'property_type', 'municipality', 'area', 'model', 'floor', 'elevator', 'balcony', 'latitude', 'longitude'],
    allowed_models: ['auto', 'no_list', 'listing'],
    note: 'Feature engineering is handled internally by SimplePredictionPipeline - send only raw features',
    backend: 'FastAPI',
    api_url: API_BASE_URL
  });
}
