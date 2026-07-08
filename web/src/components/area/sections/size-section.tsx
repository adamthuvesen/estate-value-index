import type { AreaSizeAnalysis } from "@/lib/area-types";
import { formatNumber } from "@/lib/format";
import { SizePriceChart } from "@/components/area/size-price-chart";

interface SizeSectionProps {
  sizeAnalysis: AreaSizeAnalysis;
}

/** Size analysis has no per-room variant — stays a server component. */
export function SizeSection({ sizeAnalysis }: SizeSectionProps) {
  const { size_distribution, price_by_size } = sizeAnalysis;

  return (
    <div id="size" className="ledger-card mb-6 p-5 sm:p-6">
      <h2 className="mb-4 text-lg font-semibold tracking-tight text-ledger-text">
        Size analysis
      </h2>

      <div className="mb-5">
        <SizePriceChart price_by_size={price_by_size} />
      </div>

      <div>
        <h3 className="mb-3 text-[14px] font-semibold tracking-tight text-ledger-text">
          Property size distribution
        </h3>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-xl border border-ledger-border bg-ledger-elevated p-4">
            <p className="eyebrow">Living area (m²)</p>
            <p className="num mt-1.5 text-xl font-semibold text-ledger-text">
              {formatNumber(size_distribution.living_area.median)} m²
            </p>
            <div className="mt-2 space-y-1 text-[12px] text-ledger-muted">
              <p>
                Mean: <span className="num">{formatNumber(size_distribution.living_area.mean)}</span> m²
              </p>
              <p>
                Range: <span className="num">{formatNumber(size_distribution.living_area.min)}</span> –{" "}
                <span className="num">{formatNumber(size_distribution.living_area.max)}</span> m²
              </p>
            </div>
          </div>
          <div className="rounded-xl border border-ledger-border bg-ledger-elevated p-4">
            <p className="eyebrow mb-3">Room distribution</p>
            <div className="space-y-2">
              {Object.entries(size_distribution.room_distribution)
                .sort(([a], [b]) => {
                  if (a === "4+") return 1;
                  if (b === "4+") return -1;
                  return parseInt(a) - parseInt(b);
                })
                .map(([rooms, count]) => (
                  <div key={rooms} className="flex items-center justify-between text-[13px]">
                    <span className="text-ledger-muted">
                      {rooms} room{rooms !== "1" ? "s" : ""}
                    </span>
                    <span className="num font-medium text-ledger-text">{formatNumber(count)}</span>
                  </div>
                ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
