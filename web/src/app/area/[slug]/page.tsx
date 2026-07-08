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
import { parseRoomFilter } from "@/lib/room-filter";
import { AREA_SECTIONS } from "@/components/area/section-registry";
import { RoomFilterProvider } from "@/components/area/room-filter-provider";
import { RoomFilterComponent } from "@/components/area/room-filter";
import { RailNav } from "@/components/area/rail-nav";
import { AreaHero } from "@/components/area/area-hero";
import { MarketSection } from "@/components/area/sections/market-section";
import { ValueSection } from "@/components/area/sections/value-section";
import { SizeSection } from "@/components/area/sections/size-section";
import { BuildingStockSection } from "@/components/area/sections/building-stock-section";
import { RecentSalesTable } from "@/components/area/recent-sales-table";
import { SimilarAreas } from "@/components/area/similar-areas";
import { ButtonLink } from "@/components/ui/button";

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
      <div className="mx-auto mt-4 max-w-xl rounded-sm border border-ledger-border bg-ledger-surface px-6 py-12 text-center shadow-elev-1">
        <p className="eyebrow text-val-over">Data unavailable</p>
        <h1 className="mt-3 font-display text-title text-ledger-text">
          Area statistics are not available yet
        </h1>
        <p className="mt-3 text-body-sm text-ledger-muted">
          Run the enrichment pipeline or enable GCS downloads, then reload this page.
        </p>
        <ButtonLink href="/areas" variant="secondary" size="sm" className="mt-6">
          Back to all areas
        </ButtonLink>
      </div>
    </div>
  );
}

/** Static contents anchors shown under the hero on mobile (the rail is hidden). */
function MobileContents() {
  return (
    <nav aria-label="Report contents" className="mt-8 lg:hidden">
      <p className="eyebrow text-ledger-dimmed">In this report</p>
      <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1.5 text-body-sm">
        {AREA_SECTIONS.map((section) => (
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

function KeyFacts({
  area,
  updatedAt,
  stale,
}: {
  area: AreaStatistics;
  updatedAt: string;
  stale: boolean;
}) {
  return (
    <div className="border-t border-ledger-border pt-4">
      <p className="eyebrow text-ledger-dimmed">Key facts</p>
      <dl className="mt-3 space-y-2 text-body-sm">
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-ledger-muted">Price tier</dt>
          <dd className="font-medium text-ledger-text">
            {PRICE_TIER_LABEL[area.price_tier] ?? area.price_tier}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-ledger-muted">Sample size</dt>
          <dd className="num font-medium text-ledger-text">{formatNumber(area.sample_size)}</dd>
        </div>
        <div className="flex items-baseline justify-between gap-3">
          <dt className="text-ledger-muted">Updated</dt>
          <dd className={`num font-medium ${stale ? "text-val-over" : "text-ledger-text"}`}>
            {formatDateSv(updatedAt)}
          </dd>
        </div>
      </dl>
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

  const updatedAt = metadata.generated_at;
  const stale = getStaleInfo(updatedAt)?.isStale ?? false;

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 lg:py-12">
      <nav className="mb-6 text-caption text-ledger-muted">
        <Link href="/areas" className="focus-ring transition-colors hover:text-ledger-text">
          Areas
        </Link>
        {" / "}
        <span className="text-ledger-text">{area.display_name}</span>
      </nav>

      <AreaHero area={area} updatedAt={updatedAt} stale={stale} />
      <MobileContents />

      <RoomFilterProvider initialFilter={initialFilter} roomData={area.by_room_count}>
        <div className="mt-10 grid grid-cols-1 gap-x-10 lg:grid-cols-12">
          <aside className="hidden lg:col-span-3 lg:block">
            <div className="sticky top-20 space-y-6">
              <RailNav />
              <KeyFacts area={area} updatedAt={updatedAt} stale={stale} />
              <p className="border-t border-ledger-border pt-4 text-caption text-ledger-dimmed">
                Figures are model estimates from Booli sold listings, not appraisals.
              </p>
            </div>
          </aside>

          <div className="min-w-0 lg:col-span-9">
            <div className="sticky top-14 z-30 -mx-4 mb-8 border-b border-ledger-border bg-ledger-bg/90 px-4 py-3 backdrop-blur-md sm:-mx-6 sm:px-6 lg:static lg:mx-0 lg:border-0 lg:bg-transparent lg:p-0 lg:backdrop-blur-none">
              <RoomFilterComponent />
            </div>

            <div className="space-y-12">
              <MarketSection
                overview={area.overview}
                marketDynamics={area.market_dynamics}
                avgLivingArea={area.size_analysis.size_distribution.living_area.mean}
                updatedAt={updatedAt}
                stale={stale}
              />
              <ValueSection
                valueInsights={area.value_insights}
                updatedAt={updatedAt}
                stale={stale}
              />
              <SizeSection sizeAnalysis={area.size_analysis} updatedAt={updatedAt} stale={stale} />
              <BuildingStockSection
                characteristics={area.property_characteristics}
                constructionEra={area.construction_era}
                updatedAt={updatedAt}
                stale={stale}
              />
              {similarAreas.length > 0 && <SimilarAreas areas={similarAreas} />}
              <RecentSalesTable
                recentProperties={area.recent_properties}
                areaName={area.area_name}
                updatedAt={updatedAt}
                stale={stale}
              />

              <aside className="border-t border-ledger-border pt-6">
                <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                  <div className="max-w-md">
                    <p className="eyebrow text-ledger-accent">Explore</p>
                    <h2 className="mt-1 font-display text-title text-ledger-text">
                      Find properties in {area.display_name}
                    </h2>
                    <p className="mt-2 text-body-sm text-ledger-muted">
                      Browse all{" "}
                      <span className="num">{formatNumber(area.overview.listing_count)}</span>{" "}
                      properties and surface undervalued opportunities.
                    </p>
                  </div>
                  <ButtonLink
                    href={`/value-finder?area=${area.area_name}`}
                    variant="primary"
                    size="md"
                    className="shrink-0"
                  >
                    Open in Value Finder
                  </ButtonLink>
                </div>
              </aside>
            </div>
          </div>
        </div>
      </RoomFilterProvider>
    </div>
  );
}
