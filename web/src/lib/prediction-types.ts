export interface PredictionInput {
  listing_id: string;
  listing_price: string;
  living_area: string;
  rooms: string;
  monthly_fee: string;
  days_on_market: string;
  construction_year: string;
  property_type: string;
  area: string;
  model: string;
  floor: string;
  elevator: string;
  balcony: string;
  latitude: string;
  longitude: string;
}

export interface PredictionPayload {
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
  floor: number | null;
  elevator: boolean | null;
  balcony: boolean | null;
  latitude: number | null;
  longitude: number | null;
}

export interface PredictionResult {
  listing_id: string;
  predicted_price: number;
  rounded_predicted_price: number;
  price_range_min: number;
  price_range_max: number;
  price_range_step: number;
  input_data: PredictionPayload;
  confidence: string;
  timestamp: string;
  model_used?: string;
  model_id?: string;
  model_type?: string;
  requires_listing_price?: boolean;
  status?: string;
}

export interface ListingPrefillResponse {
  listing_id?: string;
  listing_price?: number | null;
  living_area?: number | null;
  rooms?: number | null;
  monthly_fee?: number | null;
  days_on_market?: number | null;
  construction_year?: number | null;
  property_type?: string | null;
  area?: string | null;
  floor?: number | null;
  elevator?: boolean | null;
  balcony?: boolean | null;
  latitude?: number | null;
  longitude?: number | null;
  source_url?: string;
  error?: string;
}

export interface SampleListing {
  name: string;
  data: PredictionInput;
}
