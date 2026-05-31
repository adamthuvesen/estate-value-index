import { NextResponse } from "next/server";

export const AREA_DATA_MISSING_CODE = "AREA_DATA_MISSING";
export const AREA_DATA_ERROR_CODE = "AREA_DATA_ERROR";

/**
 * Returns true when an error from the area-statistics or value-analysis loader
 * indicates the source file simply isn't available yet (vs. a real failure).
 * Shared by every API route that reads enrichment JSON.
 */
export function isMissingDataError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const message = error.message.toLowerCase();
  return (
    message.includes("enoent") ||
    message.includes("not found") ||
    message.includes("gcs is not enabled") ||
    message.includes("failed to load data")
  );
}

export interface ErrorResponseInit {
  errorCode: string;
  errorMessage: string;
  remediation: string;
  status: number;
  /** Extra fields to merge into the JSON body. */
  extra?: Record<string, unknown>;
}

export function errorResponse({
  errorCode,
  errorMessage,
  remediation,
  status,
  extra,
}: ErrorResponseInit) {
  return NextResponse.json(
    {
      error_code: errorCode,
      error_message: errorMessage,
      remediation,
      ...extra,
    },
    { status }
  );
}

/** Standard 404 for "the enrichment job hasn't produced data yet". */
export function areaDataMissingResponse() {
  return errorResponse({
    errorCode: AREA_DATA_MISSING_CODE,
    errorMessage: "Area statistics are not available yet.",
    remediation:
      "Run the enrichment pipeline or enable GCS downloads for enrichment data.",
    status: 404,
  });
}

/** Standard 500 for an unexpected loader failure. */
export function areaDataErrorResponse(
  message = "Failed to load area statistics."
) {
  return errorResponse({
    errorCode: AREA_DATA_ERROR_CODE,
    errorMessage: message,
    remediation: "Check the data pipeline and server logs.",
    status: 500,
  });
}
