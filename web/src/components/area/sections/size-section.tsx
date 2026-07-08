"use client";

import { useState } from "react";
import type { AreaSizeAnalysis } from "@/lib/area-types";
import { formatNumber } from "@/lib/format";
import { FigureFrame } from "@/components/ui/figure-frame";
import { SizePriceChart } from "@/components/area/charts/size-price-chart";
import { Segmented } from "@/components/area/charts/segmented";
import { figureMeta } from "@/lib/area-report";

interface SizeSectionProps {
  sizeAnalysis: AreaSizeAnalysis;
  updatedAt: string;
  stale: boolean;
}

/** Size analysis has no per-room variant — figures are all-rooms. */
export function SizeSection({ sizeAnalysis, updatedAt, stale }: SizeSectionProps) {
  const { size_distribution, price_by_size } = sizeAnalysis;
  const [view, setView] = useState<"chart" | "table">("chart");

  const hasThinBuckets = price_by_size.some((b) => b.count < 3);
  const rooms = Object.entries(size_distribution.room_distribution).sort(([a], [b]) => {
    if (a === "4+") return 1;
    if (b === "4+") return -1;
    return parseInt(a) - parseInt(b);
  });
  const roomMax = Math.max(1, ...rooms.map(([, count]) => count));

  return (
    <FigureFrame
      kind="figure"
      index={3}
      id="size"
      title="Size & price"
      meta={figureMeta(updatedAt)}
      stale={stale}
      actions={
        <Segmented
          ariaLabel="Size view"
          value={view}
          onChange={setView}
          options={[
            { value: "chart", label: "Chart" },
            { value: "table", label: "Table" },
          ]}
        />
      }
      footnote={
        view === "chart" && hasThinBuckets
          ? "Muted bars cover size bands with fewer than 3 recorded sales — read them with care."
          : undefined
      }
    >
      <p className="mb-3 eyebrow text-ledger-dimmed">
        Median sold price across living-area bands (m²)
      </p>
      <SizePriceChart price_by_size={price_by_size} view={view} />

      <div className="mt-6 border-t border-ledger-border pt-5">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <p className="eyebrow text-ledger-dimmed">Room distribution</p>
          <p className="text-caption text-ledger-muted">
            Median living area{" "}
            <span className="num text-ledger-text">
              {formatNumber(size_distribution.living_area.median)}
            </span>{" "}
            m²
          </p>
        </div>
        <ul className="mt-3 space-y-2">
          {rooms.map(([room, count]) => (
            <li key={room} className="flex items-center gap-3 text-body-sm">
              <span className="w-16 shrink-0 text-ledger-muted">
                {room} room{room !== "1" ? "s" : ""}
              </span>
              <span className="relative h-1.5 flex-1 rounded-pill bg-ledger-elevated">
                <span
                  className="absolute inset-y-0 left-0 rounded-pill bg-ledger-accent-soft"
                  style={{ width: `${(count / roomMax) * 100}%` }}
                  aria-hidden
                />
              </span>
              <span className="num w-12 shrink-0 text-right font-medium text-ledger-text">
                {formatNumber(count)}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </FigureFrame>
  );
}
