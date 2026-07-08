"use client";

import type {
  AreaPropertyCharacteristics,
  ConstructionEraDistribution,
} from "@/lib/area-types";
import { formatPercent } from "@/lib/format";
import { ConstructionEraChart } from "@/components/area/construction-era-chart";
import { useRoomFilter } from "@/components/area/room-filter-provider";

interface BuildingStockSectionProps {
  characteristics: AreaPropertyCharacteristics;
  constructionEra: ConstructionEraDistribution;
}

export function BuildingStockSection({
  characteristics,
  constructionEra,
}: BuildingStockSectionProps) {
  const { stats } = useRoomFilter();
  const chars = stats?.property_characteristics ?? characteristics;
  const era = stats?.construction_era ?? constructionEra;

  return (
    <div id="building-stock" className="ledger-card mb-6 p-5 sm:p-6">
      <h2 className="mb-4 text-lg font-semibold tracking-tight text-ledger-text">
        Building stock
      </h2>

      <div className="mb-5 grid gap-3 sm:grid-cols-2">
        <div className="rounded-xl border border-ledger-border bg-ledger-elevated p-4">
          <div className="flex items-center justify-between">
            <p className="eyebrow">Elevator</p>
            <span className="num text-2xl font-semibold text-ledger-text">
              {formatPercent(chars.elevator_pct)}
            </span>
          </div>
          <p className="mt-2 text-[12px] text-ledger-muted">of properties have elevator access</p>
        </div>
        <div className="rounded-xl border border-ledger-border bg-ledger-elevated p-4">
          <div className="flex items-center justify-between">
            <p className="eyebrow">Balcony</p>
            <span className="num text-2xl font-semibold text-ledger-text">
              {formatPercent(chars.balcony_pct)}
            </span>
          </div>
          <p className="mt-2 text-[12px] text-ledger-muted">of properties have a balcony</p>
        </div>
      </div>

      <ConstructionEraChart construction_era={era} />
    </div>
  );
}
