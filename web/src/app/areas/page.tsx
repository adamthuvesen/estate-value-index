import type { Metadata } from "next";
import { PageHero } from "@/components/ui/page-hero";
import { StatBar, Stat } from "@/components/ui/stat-bar";
import { FigureFrame } from "@/components/ui/figure-frame";
import { AreasTable } from "@/components/areas/areas-table";
import { getAreaStatisticsData } from "@/lib/area-statistics-cache";
import { getAreaOverviewList } from "@/lib/area-overview";
import { isMissingDataError } from "@/lib/api-errors";
import type { AreaOverview, AreaStatisticsMetadata } from "@/lib/area-types";
import { formatDateSv, formatNumber, getStaleInfo } from "@/lib/format";

export const metadata: Metadata = {
  title: "Areas",
  description:
    "Stockholm neighbourhood market statistics — prices, momentum, and the model's most undervalued areas.",
};

type LoadResult =
  | { ok: true; areas: AreaOverview[]; meta: AreaStatisticsMetadata }
  | { ok: false; kind: "missing" | "error" };

async function loadAreas(): Promise<LoadResult> {
  try {
    const [data, areas] = await Promise.all([
      getAreaStatisticsData(),
      getAreaOverviewList(),
    ]);
    return { ok: true, areas, meta: data.metadata };
  } catch (error) {
    console.error("Error loading areas:", error);
    return { ok: false, kind: isMissingDataError(error) ? "missing" : "error" };
  }
}

const ERROR_COPY: Record<"missing" | "error", string> = {
  missing:
    "Area statistics aren’t available yet. Run the enrichment pipeline or enable GCS downloads.",
  error: "Couldn’t load area data. Please try again later.",
};

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">{children}</div>
  );
}

/** Swatch key for the per-m² color grade — the coding is otherwise undocumented. */
function PerSqmLegend() {
  return (
    <div className="flex items-center gap-2 text-caption text-ledger-dimmed">
      <span>lower</span>
      <span className="flex items-center gap-1" aria-hidden>
        <span className="h-2 w-2 rounded-full bg-val-exc" />
        <span className="h-2 w-2 rounded-full bg-val-great" />
        <span className="h-2 w-2 rounded-full bg-val-fair" />
        <span className="h-2 w-2 rounded-full bg-val-over" />
        <span className="h-2 w-2 rounded-full bg-val-high" />
      </span>
      <span>higher price/m²</span>
    </div>
  );
}

export default async function AreasPage() {
  const result = await loadAreas();

  if (!result.ok) {
    return (
      <Shell>
        <PageHero
          chapter="03"
          eyebrow="Areas"
          title="Stockholm areas"
          lead="Market statistics across Stockholm’s areas — prices, momentum, and where the model finds the most undervalued homes."
        />
        <div className="mt-10 rounded-sm border border-val-over-line bg-val-over-tint px-6 py-10 text-center">
          <p className="text-body-sm text-val-over">{ERROR_COPY[result.kind]}</p>
        </div>
      </Shell>
    );
  }

  const { areas, meta } = result;
  const staleInfo = getStaleInfo(meta.generated_at);
  const isStale = staleInfo?.isStale ?? false;
  const hasLimited = areas.some((area) => area.has_limited_data);

  const metaLine = isStale && staleInfo
    ? `Source: Booli · Updated ${formatDateSv(meta.generated_at)} · ${Math.floor(staleInfo.ageDays)} days old`
    : `Source: Booli · Updated ${formatDateSv(meta.generated_at)}`;

  return (
    <Shell>
      <PageHero
        chapter="03"
        eyebrow="Areas"
        title="Stockholm areas"
        lead={
          <>
            Market statistics across {meta.total_areas} areas. Table 1 ranks prices, momentum,
            and where the model finds the most undervalued homes.
          </>
        }
      >
        <StatBar>
          <Stat value={formatNumber(meta.total_areas)} label="Areas" />
          <Stat value={formatNumber(meta.total_properties)} label="Properties" />
          <Stat value={formatDateSv(meta.generated_at)} label="Updated" small />
        </StatBar>
      </PageHero>

      <div className="mt-12">
        <FigureFrame
          kind="table"
          index={1}
          title="Area register"
          meta={metaLine}
          stale={isStale}
          actions={<PerSqmLegend />}
          footnote={
            hasLimited ? "† Limited sample — interpret with care." : undefined
          }
        >
          <AreasTable areas={areas} />
        </FigureFrame>
      </div>
    </Shell>
  );
}
