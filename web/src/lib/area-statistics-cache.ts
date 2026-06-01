import type { AreaStatisticsData } from "@/lib/area-types";
import { createJsonFileCache } from "@/lib/json-file-cache";

export const AREA_STATS_CACHE_TTL_MS = 5 * 60 * 1000;

const cache = createJsonFileCache<AreaStatisticsData>({
  relativePath: "enrichment/area_statistics.json",
  ttlMs: AREA_STATS_CACHE_TTL_MS,
});

/** One parse + in-memory cache for all consumers (area list, detail, health freshness). */
export const getAreaStatisticsData = cache.get;
