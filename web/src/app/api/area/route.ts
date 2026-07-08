import { NextResponse } from "next/server";
import { getAreaStatisticsData } from "@/lib/area-statistics-cache";
import { getAreaOverviewList } from "@/lib/area-overview";
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
    const areas = await getAreaOverviewList();

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
