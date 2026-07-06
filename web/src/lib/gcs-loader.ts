// Loads enrichment data from local disk, falling back to GCS when enabled.

import { readFile, writeFile, mkdir } from "fs/promises";
import { dirname } from "path";
import { Storage } from "@google-cloud/storage";
import { DataFileLoadError, DataFileMissingError } from "@/lib/data-file-errors";

// Default to true in production, false in development/test
const isProduction = process.env.NODE_ENV === "production";
const GCS_ENABLED = process.env.GCS_ENABLED
  ? process.env.GCS_ENABLED === "true"
  : isProduction;

let storageClient: Storage | null = null;

function getStorageClient(): Storage {
  if (!storageClient) {
    storageClient = new Storage();
  }
  return storageClient;
}

function getGcsBucket(): string {
  const bucket = process.env.GCS_BUCKET;
  if (!bucket) {
    throw new Error("GCS_BUCKET is required when GCS fallback is enabled");
  }
  return bucket;
}

function isNotFoundError(error: unknown): boolean {
  if (!(error instanceof Error)) return false;
  const code = "code" in error ? String(error.code) : "";
  return code === "404" || error.message.toLowerCase().includes("no such object");
}

export async function loadDataFile(
  localPath: string,
  gcsPath: string
): Promise<string> {
  try {
    const content = await readFile(localPath, "utf-8");
    console.debug(JSON.stringify({ level: "debug", message: "Loaded data file from local", localPath }));
    return content;
  } catch (error) {
    if (error instanceof Error && "code" in error && error.code !== "ENOENT") {
      throw new DataFileLoadError(
        "Failed to read data file.",
        localPath,
        gcsPath,
        error.message,
      );
    }

    if (!GCS_ENABLED) {
      console.error(JSON.stringify({
        level: "error",
        message: "Data file not found and GCS fallback disabled",
        localPath,
        gcsPath,
        gcsEnabled: GCS_ENABLED,
        nodeEnv: process.env.NODE_ENV,
        remediation: "Set GCS_ENABLED=true or ensure local file exists"
      }));
      throw new DataFileMissingError(
        "Data file is not available and GCS fallback is disabled.",
        localPath,
        gcsPath,
      );
    }

    console.debug(JSON.stringify({ level: "debug", message: "Local file not found, downloading from GCS", localPath, gcsPath }));

    try {
      const storage = getStorageClient();
      const bucket = storage.bucket(getGcsBucket());
      const file = bucket.file(gcsPath);

      const [content] = await file.download();
      const contentStr = content.toString("utf-8");

      // Cache to local path; failure here is non-fatal — we already have the content
      try {
        await mkdir(dirname(localPath), { recursive: true });
        await writeFile(localPath, contentStr, "utf-8");
        console.debug(JSON.stringify({ level: "debug", message: "Downloaded and cached data file locally", localPath, gcsPath }));
      } catch (writeError) {
        console.warn(`[GCS] Failed to cache file locally: ${writeError}`);
      }

      return contentStr;
    } catch (gcsError) {
      const message = gcsError instanceof Error ? gcsError.message : "Unknown error";
      if (isNotFoundError(gcsError)) {
        throw new DataFileMissingError("Data file is not available in GCS.", localPath, gcsPath);
      }
      throw new DataFileLoadError(
        "Failed to load data file.",
        localPath,
        gcsPath,
        message,
      );
    }
  }
}
