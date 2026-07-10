import type { OverallStatisticsData } from "@/lib/overall-statistics-types";
import { createJsonFileCache } from "@/lib/json-file-cache";

export const OVERALL_STATS_CACHE_TTL_MS = 5 * 60 * 1000;

const cache = createJsonFileCache<OverallStatisticsData>({
  relativePath: "derived/overall_statistics.json",
  ttlMs: OVERALL_STATS_CACHE_TTL_MS,
});

/** One parse + in-memory cache for the city-wide statistics report (`/stats`). */
export const getOverallStatisticsData = cache.get;
