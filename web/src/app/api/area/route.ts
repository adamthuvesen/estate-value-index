import { NextResponse } from "next/server";
import type { AreaOverview } from "@/lib/area-types";
import { getAreaStatisticsData } from "@/lib/area-statistics-cache";
import {
  areaDataErrorResponse,
  areaDataMissingResponse,
  isMissingDataError,
} from "@/lib/api-errors";

// Lock to the Node runtime: this route imports `@google-cloud/storage` and
// `fs/promises` (transitively via `loadDataFile`), neither of which are
// available on the Edge runtime.
export const runtime = "nodejs";

/** GET /api/area — overview list of all areas for the comparison table */
export async function GET() {
  try {
    const data = await getAreaStatisticsData();

    const areas: AreaOverview[] = Object.values(data.areas).map((area) => {
      // Weighted average price/m² across room buckets
      let avg_price_per_sqm: number | null = null;
      if (area.size_analysis.price_per_sqm_by_rooms) {
        let totalWeightedPrice = 0;
        let totalCount = 0;

        Object.values(area.size_analysis.price_per_sqm_by_rooms).forEach((roomData) => {
          totalWeightedPrice += roomData.mean * roomData.count;
          totalCount += roomData.count;
        });

        if (totalCount > 0) {
          avg_price_per_sqm = Math.round(totalWeightedPrice / totalCount);
        }
      }

      return {
        area_name: area.area_name,
        display_name: area.display_name,
        price_tier: area.price_tier,
        avg_sold_price: area.overview.avg_sold_price,
        avg_price_per_sqm,
        listing_count: area.overview.listing_count,
        inventory: area.overview.inventory,
        median_price_3m: area.overview.median_price_3m,
        days_on_market_median: area.market_dynamics.days_on_market_median,
        price_change_mean: area.market_dynamics.price_change_mean,
        volatility: area.market_dynamics.volatility,
        undervalued_pct: area.value_insights.undervalued_pct,
        has_limited_data: area.has_limited_data,
        sample_size: area.sample_size,
      };
    });

    areas.sort((a, b) => b.listing_count - a.listing_count);

    return NextResponse.json(
      {
        metadata: data.metadata,
        areas,
      },
      {
        headers: {
          "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600",
        },
      }
    );
  } catch (error) {
    console.error("Error in area API:", error);
    return isMissingDataError(error)
      ? areaDataMissingResponse()
      : areaDataErrorResponse();
  }
}
