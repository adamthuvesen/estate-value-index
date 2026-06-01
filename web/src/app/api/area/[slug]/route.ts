import { NextRequest, NextResponse } from "next/server";
import type { AreaDetails } from "@/lib/area-types";
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

const AREA_NOT_FOUND_CODE = "AREA_NOT_FOUND";

/** GET /api/area/[slug] — detailed analytics for a specific area */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ slug: string }> }
) {
  try {
    const data = await getAreaStatisticsData();
    const { slug: areaSlug } = await params;

    const areaData = data.areas[areaSlug];

    if (!areaData) {
      return NextResponse.json(
        {
          error_code: AREA_NOT_FOUND_CODE,
          error_message: "Area not found.",
          remediation: "Select a different area from the list.",
          available_areas: Object.keys(data.areas),
        },
        { status: 404 }
      );
    }

    const response: AreaDetails = {
      ...areaData,
      metadata: data.metadata,
    };

    return NextResponse.json(response, {
      headers: {
        "Cache-Control": "public, s-maxage=300, stale-while-revalidate=600",
      },
    });
  } catch (error) {
    console.error("Error in area detail API:", error);
    return isMissingDataError(error)
      ? areaDataMissingResponse()
      : areaDataErrorResponse("Failed to load area details.");
  }
}
