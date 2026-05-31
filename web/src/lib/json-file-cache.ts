import { join } from "path";
import { loadDataFile } from "@/lib/gcs-loader";

export interface JsonFileCacheOptions {
  /** Filename under `data/` (e.g. `enrichment/value_analysis.json`). */
  relativePath: string;
  /** TTL in milliseconds before the in-memory copy is refetched. */
  ttlMs: number;
}

/**
 * Build an in-memory TTL cache around a single JSON data file. Resolves the
 * production (`/app/data/...`) vs dev (`<cwd>/../data/...`) paths and shares the
 * same loader for both, so adding new cached datasets is a one-liner.
 */
export function createJsonFileCache<T>({ relativePath, ttlMs }: JsonFileCacheOptions): {
  get: () => Promise<T>;
} {
  const localPath =
    process.env.NODE_ENV === "production"
      ? `/app/data/${relativePath}`
      : join(process.cwd(), "..", "data", relativePath);

  let cached: T | null = null;
  let cachedAt: number | null = null;
  let inFlight: Promise<T> | null = null;

  return {
    async get(): Promise<T> {
      const now = Date.now();
      if (cached && cachedAt && now - cachedAt < ttlMs) {
        return cached;
      }

      if (inFlight) {
        return inFlight;
      }

      inFlight = loadDataFile(localPath, relativePath)
        .then((fileContent) => {
          const data = JSON.parse(fileContent) as T;
          cached = data;
          cachedAt = Date.now();
          return data;
        })
        .finally(() => {
          inFlight = null;
        });

      return inFlight;
    },
  };
}
