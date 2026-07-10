import type { Metadata } from "next";
import { getOverallStatisticsData } from "@/lib/overall-statistics-cache";
import { isMissingDataError } from "@/lib/api-errors";
import { figureMeta } from "@/lib/area-report";
import type { OverallStatisticsData } from "@/lib/overall-statistics-types";
import { PageHero } from "@/components/ui/page-hero";
import { StatsHero } from "@/components/stats/stats-hero";
import { StatsRailNav } from "@/components/stats/stats-rail-nav";
import { STATS_SECTIONS } from "@/components/stats/section-registry";
import { PricesSection } from "@/components/stats/sections/prices-section";
import { OverTimeSection } from "@/components/stats/sections/over-time-section";
import { BiddingSection } from "@/components/stats/sections/bidding-section";
import { GeographySection } from "@/components/stats/sections/geography-section";
import { SizeRoomsSection } from "@/components/stats/sections/size-rooms-section";
import { BuildingSection } from "@/components/stats/sections/building-section";
import { RecordsSection } from "@/components/stats/sections/records-section";

// Statistics load from a request-time cache (GCS-synced file); a static build
// would bake in whatever existed at build time — often the missing-data panel.
export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Statistics — Stockholm in Numbers",
  description:
    "A city-wide statistical report over every recorded Stockholm apartment sale — prices, bidding, geography, building stock, and the record book.",
};

type LoadResult =
  | { ok: true; data: OverallStatisticsData }
  | { ok: false; kind: "missing" | "error" };

async function loadStats(): Promise<LoadResult> {
  try {
    const data = await getOverallStatisticsData();
    return { ok: true, data };
  } catch (error) {
    console.error("Error loading overall statistics:", error);
    return { ok: false, kind: isMissingDataError(error) ? "missing" : "error" };
  }
}

const ERROR_COPY: Record<"missing" | "error", string> = {
  missing:
    "City-wide statistics aren’t available yet. Run the enrichment pipeline or enable GCS downloads.",
  error: "Couldn’t load the statistics. Please try again later.",
};

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-12">{children}</div>
  );
}

/** Static contents anchors shown under the hero on mobile (the rail is hidden). */
function MobileContents() {
  return (
    <nav aria-label="Report contents" className="mt-8 lg:hidden">
      <p className="eyebrow text-ledger-dimmed">In this report</p>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 text-body-sm">
        {STATS_SECTIONS.map((section) => (
          <li key={section.id}>
            <a
              href={`#${section.id}`}
              className="focus-ring text-ledger-muted underline-offset-4 hover:text-ledger-text hover:underline"
            >
              {section.title}
            </a>
          </li>
        ))}
      </ul>
    </nav>
  );
}

export default async function StatsPage() {
  const result = await loadStats();

  if (!result.ok) {
    return (
      <Shell>
        <PageHero
          chapter="04"
          eyebrow="Statistics"
          title="Stockholm in Numbers"
          lead="A city-wide statistical report over every recorded Stockholm apartment sale."
        />
        <div className="mt-10 rounded-sm border border-val-over-line bg-val-over-tint px-6 py-10 text-center">
          <p className="text-body-sm text-val-over">{ERROR_COPY[result.kind]}</p>
        </div>
      </Shell>
    );
  }

  const { data } = result;
  const updatedMeta = figureMeta(data.metadata.generated_at);

  return (
    <Shell>
      <StatsHero hero={data.hero} metadata={data.metadata} />
      <MobileContents />

      <div className="mt-12 grid grid-cols-1 gap-x-10 lg:grid-cols-12">
        <aside className="hidden lg:col-span-3 lg:block">
          <div className="sticky top-20 space-y-6">
            <StatsRailNav />
            <p className="border-t border-ledger-border pt-4 text-caption text-ledger-dimmed">
              Figures are computed from Booli sold listings, not appraisals. Shares are model
              estimates.
            </p>
          </div>
        </aside>

        <div className="min-w-0 space-y-16 lg:col-span-9">
          <PricesSection prices={data.prices} updatedMeta={updatedMeta} />
          <OverTimeSection overTime={data.over_time} updatedMeta={updatedMeta} />
          <BiddingSection bidding={data.bidding} updatedMeta={updatedMeta} />
          <GeographySection geography={data.geography} updatedMeta={updatedMeta} />
          <SizeRoomsSection sizeRooms={data.size_rooms} updatedMeta={updatedMeta} />
          <BuildingSection
            building={data.building}
            totalProperties={data.metadata.total_properties}
            updatedMeta={updatedMeta}
          />
          <RecordsSection records={data.records} updatedMeta={updatedMeta} />
        </div>
      </div>
    </Shell>
  );
}
