import { PageHero } from "@/components/ui/page-hero";
import { Stat, StatBar } from "@/components/ui/stat-bar";
import { BarcodeStrip } from "@/components/stats/barcode-strip";
import type {
  OverallHero,
  OverallStatisticsMetadata,
} from "@/lib/overall-statistics-types";
import { formatNumber, formatShortSek } from "@/lib/format";

function monthYear(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { month: "short", year: "numeric" });
}

export function StatsHero({
  hero,
  metadata,
}: {
  hero: OverallHero;
  metadata: OverallStatisticsMetadata;
}) {
  const range = `${monthYear(metadata.date_range.start)} – ${monthYear(
    metadata.date_range.end,
  )}`;

  return (
    <header>
      <PageHero
        chapter="04"
        eyebrow="Statistics"
        title="Stockholm in Numbers"
        lead={
          <>
            Every recorded apartment sale in the register, read as one document:{" "}
            <span className="num">{formatNumber(hero.total_sales)}</span> sales across{" "}
            <span className="num">{hero.total_areas}</span> Stockholm areas, at a median of{" "}
            <span className="num">{formatNumber(hero.median_price_per_sqm)}</span> kr/m². What
            follows is the whole market in seven chapters.
          </>
        }
      >
        <StatBar>
          <Stat value={formatNumber(hero.total_sales)} label="Sales" />
          <Stat value={formatNumber(hero.total_areas)} label="Areas" />
          <Stat value={formatShortSek(hero.median_sold_price)} label="Median price" small />
          <Stat value={formatNumber(hero.median_price_per_sqm)} label="Median kr/m²" small />
          <Stat value={range} label="Period" small />
        </StatBar>
      </PageHero>

      <BarcodeStrip strip={hero.price_per_sqm_strip} medianPerSqm={hero.median_price_per_sqm} />
    </header>
  );
}
