"use client";

import type {
  AreaPropertyCharacteristics,
  ConstructionEraDistribution,
} from "@/lib/area-types";
import { formatPercent } from "@/lib/format";
import { FigureFrame } from "@/components/ui/figure-frame";
import { ConstructionEraChart } from "@/components/area/charts/construction-era-chart";
import { useRoomFilter } from "@/components/area/room-filter-provider";
import { figureMeta, roomScopeNote } from "@/lib/area-report";

interface BuildingStockSectionProps {
  characteristics: AreaPropertyCharacteristics;
  constructionEra: ConstructionEraDistribution;
  updatedAt: string;
  stale: boolean;
}

function eraNote(era: ConstructionEraDistribution): string | undefined {
  if (!era.median_year) return undefined;
  const parts = [`Median build year ${era.median_year}`];
  if (era.avg_age) parts.push(`Avg age ${era.avg_age} yrs`);
  if (era.oldest && era.newest) parts.push(`Range ${era.oldest}–${era.newest}`);
  return parts.join(" · ");
}

export function BuildingStockSection({
  characteristics,
  constructionEra,
  updatedAt,
  stale,
}: BuildingStockSectionProps) {
  const { filter, stats } = useRoomFilter();
  const chars = stats?.property_characteristics ?? characteristics;
  const era = stats?.construction_era ?? constructionEra;
  const note = roomScopeNote(filter, stats?.property_count);

  return (
    <FigureFrame
      kind="figure"
      index={4}
      id="building-stock"
      title="Building stock"
      meta={figureMeta(updatedAt, note)}
      stale={stale}
      footnote={eraNote(era)}
    >
      <dl className="mb-6 grid gap-5 sm:grid-cols-2">
        <div>
          <dt className="eyebrow">Elevator</dt>
          <dd className="num mt-1.5 text-title font-semibold text-ledger-text">
            {formatPercent(chars.elevator_pct)}
          </dd>
          <p className="mt-1 text-caption text-ledger-muted">of properties have elevator access</p>
        </div>
        <div>
          <dt className="eyebrow">Balcony</dt>
          <dd className="num mt-1.5 text-title font-semibold text-ledger-text">
            {formatPercent(chars.balcony_pct)}
          </dd>
          <p className="mt-1 text-caption text-ledger-muted">of properties have a balcony</p>
        </div>
      </dl>

      <p className="mb-3 eyebrow text-ledger-dimmed">Properties by construction era</p>
      <ConstructionEraChart construction_era={era} />
    </FigureFrame>
  );
}
