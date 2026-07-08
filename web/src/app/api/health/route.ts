import { NextResponse } from 'next/server';
import { getAreaStatisticsData } from "@/lib/area-statistics-cache";

// Lock to the Node runtime so localhost `fetch` to the FastAPI sidecar works.
export const runtime = 'nodejs';

const FASTAPI_URL = process.env.PREDICTION_API_URL || 'http://localhost:8000';
const HEALTH_CHECK_TIMEOUT = 5000; // 5 seconds
const AREA_DATA_STALE_DAYS = 8;

type FastAPIHealth = {
  status: string;
  models_loaded: string[];
  models_count: number;
};

type CheckResult = { status: string; details?: unknown };

async function checkFastApi(): Promise<CheckResult> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), HEALTH_CHECK_TIMEOUT);

  try {
    const response = await fetch(`${FASTAPI_URL}/health`, {
      method: 'GET',
      signal: controller.signal,
    });

    if (response.ok) {
      const data = (await response.json()) as FastAPIHealth;
      return {
        status: 'healthy',
        details: {
          models_loaded: data.models_loaded,
          models_count: data.models_count,
        },
      };
    }
    console.error('[HEALTH] FastAPI unhealthy, status:', response.status);
    return {
      status: 'unhealthy',
      details: { http_status: response.status },
    };
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Unknown error';
    console.error('[HEALTH] FastAPI check failed:', errorMessage);
    return {
      status: 'unhealthy',
      details: { error: errorMessage },
    };
  } finally {
    clearTimeout(timeoutId);
  }
}

async function checkAreaData(): Promise<CheckResult> {
  try {
    const data = await getAreaStatisticsData();
    const generatedAt = data?.metadata?.generated_at;

    if (!generatedAt) {
      return {
        status: "unhealthy",
        details: { error: "Missing generated_at in area statistics metadata." },
      };
    }

    const generatedAtDate = new Date(generatedAt);
    const ageDays = Number.isNaN(generatedAtDate.getTime())
      ? null
      : (Date.now() - generatedAtDate.getTime()) / (1000 * 60 * 60 * 24);
    const isStale = ageDays !== null && ageDays > AREA_DATA_STALE_DAYS;

    return {
      status: isStale ? "degraded" : "healthy",
      details: {
        generated_at: generatedAt,
        age_days: ageDays !== null ? Math.floor(ageDays) : null,
        stale_threshold_days: AREA_DATA_STALE_DAYS,
      },
    };
  } catch (error) {
    console.error("[HEALTH] Area data check failed:", error);
    return {
      status: "unhealthy",
      details: { error_code: "AREA_DATA_UNAVAILABLE" },
    };
  }
}

export async function GET() {
  // Probe both checks concurrently — the FastAPI fetch can take up to 5s and
  // shouldn't serialize behind a (potentially cold) GCS area-data load.
  const [fastapi, areaData] = await Promise.all([checkFastApi(), checkAreaData()]);

  const checks: Record<string, CheckResult> = {
    nextjs: { status: 'healthy' },
    fastapi,
    area_data: areaData,
  };

  const allHealthy = Object.values(checks).every((check) => check.status === 'healthy');
  const httpStatus = allHealthy ? 200 : 503;

  return NextResponse.json(
    {
      status: allHealthy ? 'healthy' : 'degraded',
      checks,
      timestamp: new Date().toISOString(),
    },
    { status: httpStatus }
  );
}
