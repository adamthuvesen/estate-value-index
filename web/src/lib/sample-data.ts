import type { SampleListing } from "./prediction-types";

// Synthetic demo listings only. Do not replace with real scraped rows.
export const SAMPLE_LISTINGS: SampleListing[] = [
  {
    name: "Demo Compact",
    data: {
      listing_id: "synthetic-demo-001",
      listing_price: "3495000",
      living_area: "41",
      rooms: "2",
      monthly_fee: "2592",
      days_on_market: "13",
      construction_year: "1949",
      property_type: "Lägenhet",
      area: "Södermalm",
      model: "lgbm",
      floor: "2",
      elevator: "",
      balcony: "",
    }
  },
  {
    name: "Demo Premium",
    data: {
      listing_id: "synthetic-demo-002",
      listing_price: "7950000",
      living_area: "58",
      rooms: "2",
      monthly_fee: "3984",
      days_on_market: "23",
      construction_year: "1924",
      property_type: "Lägenhet",
      area: "Östermalm",
      model: "lgbm",
      floor: "1",
      elevator: "true",
      balcony: "",
    }
  },
  {
    name: "Demo Family",
    data: {
      listing_id: "synthetic-demo-003",
      listing_price: "4895000",
      living_area: "60",
      rooms: "4",
      monthly_fee: "4980",
      days_on_market: "10",
      construction_year: "1931",
      property_type: "Lägenhet",
      area: "Kungsholmen",
      model: "lgbm",
      floor: "",
      elevator: "",
      balcony: "",
    }
  },
  {
    name: "Demo Cozy",
    data: {
      listing_id: "synthetic-demo-004",
      listing_price: "5195000",
      living_area: "49",
      rooms: "2",
      monthly_fee: "2745",
      days_on_market: "18",
      construction_year: "1973",
      property_type: "Lägenhet",
      area: "Vasastan",
      model: "lgbm",
      floor: "5",
      elevator: "true",
      balcony: "true",
    }
  },
  {
    name: "Demo Central",
    data: {
      listing_id: "synthetic-demo-005",
      listing_price: "6795000",
      living_area: "56",
      rooms: "2",
      monthly_fee: "2656",
      days_on_market: "11",
      construction_year: "1915",
      property_type: "Lägenhet",
      area: "Norrmalm",
      model: "lgbm",
      floor: "1",
      elevator: "true",
      balcony: "",
    }
  },
  {
    name: "Demo Modern",
    data: {
      listing_id: "synthetic-demo-006",
      listing_price: "6890000",
      living_area: "67",
      rooms: "3",
      monthly_fee: "4229",
      days_on_market: "12",
      construction_year: "1962",
      property_type: "Lägenhet",
      area: "Gärdet",
      model: "lgbm",
      floor: "3",
      elevator: "true",
      balcony: "true",
    }
  }
];

export const DEFAULT_AREAS = [
  "Södermalm",
  "Östermalm",
  "Kungsholmen",
  "Vasastan",
  "Norrmalm",
  "Gamla Stan",
  "Fredhäll",
  "Gärdet",
  "Årsta",
  "Gröndal",
  "Hammarby Sjöstad",
];

export const MODEL_LABELS: Record<string, string> = {
  lgbm: "LightGBM",
  xgb: "XGBoost",
  linear: "Linear Regression",
};
