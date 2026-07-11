import { NextResponse } from "next/server";
import { DataFileMissingError } from "@/lib/data-file-errors";

export const VALUE_ANALYSIS_DATA_MISSING_CODE = "VALUE_ANALYSIS_DATA_MISSING";
export const VALUE_ANALYSIS_DATA_ERROR_CODE = "VALUE_ANALYSIS_DATA_ERROR";

export function isMissingDataError(error: unknown): boolean {
  return error instanceof DataFileMissingError;
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

/** Standard 404 for "the value-analysis job hasn't produced data yet". */
export function valueAnalysisDataMissingResponse() {
  return errorResponse({
    errorCode: VALUE_ANALYSIS_DATA_MISSING_CODE,
    errorMessage: "Value analysis data is not available yet.",
    remediation:
      "Run the value-analysis generation job or enable GCS downloads for enrichment data.",
    status: 404,
  });
}

/** Standard 500 for an unexpected value-analysis loader failure. */
export function valueAnalysisDataErrorResponse() {
  return errorResponse({
    errorCode: VALUE_ANALYSIS_DATA_ERROR_CODE,
    errorMessage: "Failed to load value analysis data.",
    remediation: "Check the data pipeline and server logs.",
    status: 500,
  });
}
