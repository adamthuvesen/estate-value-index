import type { ValueAnalysisData } from "@/lib/value-finder-types";
import { createJsonFileCache } from "@/lib/json-file-cache";

export const VALUE_ANALYSIS_CACHE_TTL_MS = 5 * 60 * 1000;

const cache = createJsonFileCache<ValueAnalysisData>({
  relativePath: "enrichment/value_analysis.json",
  ttlMs: VALUE_ANALYSIS_CACHE_TTL_MS,
});

/** Single load path for value finder list + metadata routes. */
export const getValueAnalysisData = cache.get;
