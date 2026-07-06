import { NextResponse } from "next/server";
import {
  VALUE_TIERS,
  type ValueAnalysisData,
  type ValueFinderFacetsResponse,
} from "@/lib/value-finder-types";
import { getValueAnalysisData } from "@/lib/value-analysis-cache";
import {
  isValueAnalysisDataMissingError,
  valueAnalysisDataErrorResponse,
  valueAnalysisDataMissingResponse,
} from "@/lib/api-errors";

// Lock to the Node runtime: this route imports `@google-cloud/storage` and
// `fs/promises` (transitively via `loadDataFile`), neither of which are
// available on the Edge runtime.
export const runtime = "nodejs";

interface NumericRange {
  min: number;
  max: number;
}

const seedRange = (): NumericRange => ({
  min: Number.POSITIVE_INFINITY,
  max: Number.NEGATIVE_INFINITY,
});

const updateRange = (range: NumericRange, value: number | null) => {
  if (value === null) return;
  if (value < range.min) range.min = value;
  if (value > range.max) range.max = value;
};

const finalizeRange = (range: NumericRange): NumericRange =>
  Number.isFinite(range.min) ? range : { min: 0, max: 0 };

function buildMetadataResponse(data: ValueAnalysisData): ValueFinderFacetsResponse {
  const areas = new Set<string>();
  const municipalities = new Set<string>();
  const propertyTypes = new Set<string>();
  const priceRange = seedRange();
  const livingAreaRange = seedRange();
  const roomsRange = seedRange();
  const valueScoreRange = seedRange();

  // Single pass: builds all four ranges + three uniqueness sets in one walk.
  // Replaces eight `Math.min(...arr)` spreads (which can hit V8's call-stack
  // limit on large datasets) plus four `data.properties.map(...)` allocations.
  for (const property of data.properties) {
    areas.add(property.area);
    municipalities.add(property.municipality);
    propertyTypes.add(property.property_type);
    updateRange(priceRange, property.sold_price);
    updateRange(livingAreaRange, property.living_area);
    updateRange(roomsRange, property.rooms);
    updateRange(valueScoreRange, property.value_score);
  }

  return {
    available_areas: [...areas].sort(),
    available_municipalities: [...municipalities].sort(),
    property_types: [...propertyTypes].sort(),
    value_tiers: [...VALUE_TIERS],
    price_range: finalizeRange(priceRange),
    living_area_range: finalizeRange(livingAreaRange),
    rooms_range: finalizeRange(roomsRange),
    value_score_range: finalizeRange(valueScoreRange),
    statistics: data.statistics,
    last_updated: data.metadata.generated_at,
  };
}

export async function GET() {
  try {
    const data = await getValueAnalysisData();
    const metadata = buildMetadataResponse(data);

    return NextResponse.json(metadata, {
      headers: {
        "Cache-Control": "public, s-maxage=600, stale-while-revalidate=1200",
      },
    });
  } catch (error) {
    console.error("Error in value-finder/metadata API:", error);

    return isValueAnalysisDataMissingError(error)
      ? valueAnalysisDataMissingResponse()
      : valueAnalysisDataErrorResponse();
  }
}
