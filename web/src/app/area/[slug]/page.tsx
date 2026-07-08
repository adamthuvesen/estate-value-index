import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { AreaStatistics, AreaStatisticsMetadata } from "@/lib/area-types";
import { getAreaStatisticsData } from "@/lib/area-statistics-cache";
import { getAreaOverviewList } from "@/lib/area-overview";
import { selectSimilarAreas, type ScoredArea } from "@/lib/similar-areas";
import { isMissingDataError } from "@/lib/api-errors";
import { PRICE_TIER_LABEL } from "@/lib/tiers";
import { formatDateSv, formatNumber, getStaleInfo } from "@/lib/format";
import { SectionNavigation } from "@/components/area/section-navigation";
import { RoomFilterProvider } from "@/components/area/room-filter-provider";
import { parseRoomFilter } from "@/lib/room-filter";
import { RoomFilterComponent } from "@/components/area/room-filter";
import { OverviewSection } from "@/components/area/sections/overview-section";
import { MarketSection } from "@/components/area/sections/market-section";
import { ValueSection } from "@/components/area/sections/value-section";
import { SizeSection } from "@/components/area/sections/size-section";
import { BuildingStockSection } from "@/components/area/sections/building-stock-section";
import { RecentSalesSection } from "@/components/area/recent-sales-section";
import { SimilarAreas } from "@/components/area/similar-areas";

// Area statistics load from a request-time cache (GCS-synced file); a static
// build would bake in whatever existed at build time.
export const dynamic = "force-dynamic";

interface AreaPageProps {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ rooms?: string }>;
}

export async function generateMetadata({ params }: AreaPageProps): Promise<Metadata> {
  const { slug } = await params;

  let area: AreaStatistics | undefined;
  try {
    const data = await getAreaStatisticsData();
    area = data.areas[slug];
  } catch {
    return { title: "Area statistics" };
  }

  if (!area) {
    return { title: "Area not found" };
  }

  const perSqm = area.overview.avg_price_per_sqm;
  const description = [
    perSqm ? `Average price ${formatNumber(perSqm)} kr/m²` : null,
    `${formatNumber(area.overview.listing_count)} sold listings`,
    `${formatNumber(area.market_dynamics.days_on_market_median)} days on market in ${area.display_name}`,
  ]
    .filter(Boolean)
    .join(", ")
    .concat(". Price trends, value analysis and building stock.");

  const title = `${area.display_name} — Area statistics`;
  return {
    title,
    description,
    alternates: { canonical: `/area/${slug}` },
    openGraph: { title, description },
    twitter: { card: "summary", title, description },
  };
}

/** Rendered inline for the known "statistics not generated yet" state. */
function MissingDataPanel() {
  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
      <div className="mx-auto mt-4 max-w-xl rounded-2xl border border-ledger-border bg-ledger-surface px-6 py-12 text-center shadow-elev-1">
        <p className="eyebrow text-val-over">Data unavailable</p>
        <h1 className="mt-3 font-display text-title text-ledger-text">
          Area statistics are not available yet
        </h1>
        <p className="mt-3 text-[14px] text-ledger-muted">
          Run the enrichment pipeline or enable GCS downloads, then reload this page.
        </p>
        <Link href="/areas" className="ledger-btn focus-ring mt-6 inline-flex text-[13px]">
          Back to all areas
        </Link>
      </div>
    </div>
  );
}

export default async function AreaDetailPage({ params, searchParams }: AreaPageProps) {
  const [{ slug }, { rooms }] = await Promise.all([params, searchParams]);
  const initialFilter = parseRoomFilter(rooms);

  let area: AreaStatistics | undefined;
  let metadata: AreaStatisticsMetadata;
  let similarAreas: ScoredArea[] = [];

  try {
    const data = await getAreaStatisticsData();
    metadata = data.metadata;
    area = data.areas[slug];

    if (area) {
      const allAreas = await getAreaOverviewList();
      similarAreas = selectSimilarAreas(
        {
          area_name: area.area_name,
          price_tier: area.price_tier,
          avg_sold_price: area.overview.avg_sold_price,
        },
        allAreas,
      );
    }
  } catch (error) {
    if (isMissingDataError(error)) {
      return <MissingDataPanel />;
    }
    throw error;
  }

  if (!area) {
    notFound();
  }

  const staleInfo = getStaleInfo(metadata.generated_at);

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
      <div className="relative">
        <nav className="mb-8 text-[13px] text-ledger-muted">
          <Link href="/" className="focus-ring transition-colors hover:text-ledger-text">
            Home
          </Link>
          {" / "}
          <Link href="/areas" className="focus-ring transition-colors hover:text-ledger-text">
            Areas
          </Link>
          {" / "}
          <span className="font-medium text-ledger-text">{area.display_name}</span>
        </nav>

        <div className="mb-8 text-center animate-fade-in-up">
          <p className="eyebrow text-ledger-accent">Area report</p>
          <div className="mt-2 mb-3 flex flex-wrap items-center justify-center gap-3">
            <h1 className="font-display text-headline text-ledger-text">{area.display_name}</h1>
            <span className="inline-flex rounded-pill border border-ledger-border bg-ledger-elevated px-3 py-1 text-[13px] font-medium text-ledger-muted">
              {PRICE_TIER_LABEL[area.price_tier] ?? area.price_tier}
            </span>
          </div>
          {area.has_limited_data && (
            <p className="text-[13px] text-val-over">
              Limited data available ({area.sample_size} properties) — estimates may vary.
            </p>
          )}
        </div>

        {staleInfo?.isStale && (
          <div className="mx-auto mb-8 max-w-2xl rounded-xl border border-val-over-line bg-val-over-tint px-4 py-3 text-center">
            <p className="text-[13px] text-val-over">
              Data is {Math.floor(staleInfo.ageDays)} days old — last updated{" "}
              {formatDateSv(staleInfo.generatedAt)}.
            </p>
          </div>
        )}

        <SectionNavigation areaName={area.display_name} />

        <RoomFilterProvider initialFilter={initialFilter} roomData={area.by_room_count}>
          <RoomFilterComponent />

          <OverviewSection overview={area.overview} marketDynamics={area.market_dynamics} />

          <MarketSection
            overview={area.overview}
            marketDynamics={area.market_dynamics}
            avgLivingArea={area.size_analysis.size_distribution.living_area.mean}
          />

          <ValueSection valueInsights={area.value_insights} />

          <SizeSection sizeAnalysis={area.size_analysis} />

          <BuildingStockSection
            characteristics={area.property_characteristics}
            constructionEra={area.construction_era}
          />

          {similarAreas.length > 0 && (
            <div id="similar" className="ledger-card mb-6 p-5 sm:p-6">
              <SimilarAreas areas={similarAreas} />
            </div>
          )}

          <RecentSalesSection
            recentProperties={area.recent_properties}
            areaName={area.area_name}
          />
        </RoomFilterProvider>

        <div className="ledger-card p-6 text-center">
          <h3 className="text-lg font-semibold tracking-tight text-ledger-text">
            Find properties in {area.display_name}
          </h3>
          <p className="mt-2 text-[14px] text-ledger-muted">
            Browse all <span className="num">{formatNumber(area.overview.listing_count)}</span>{" "}
            properties and discover undervalued opportunities.
          </p>
          <Link
            href={`/value-finder?area=${area.area_name}`}
            className="ledger-btn-primary focus-ring mt-4 inline-flex text-[13px]"
          >
            Explore {area.display_name} properties
          </Link>
        </div>
      </div>
    </div>
  );
}
