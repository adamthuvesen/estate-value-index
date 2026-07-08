import Link from "next/link";
import type { ScoredArea } from "@/lib/similar-areas";
import { TierChip } from "@/components/ui/badge";
import { formatNumber, formatNumberOrDash, formatSek } from "@/lib/format";
import { getSection } from "@/components/area/section-registry";

interface SimilarAreasProps {
  /** Pre-scored on the server via `selectSimilarAreas` — render-only here. */
  areas: ScoredArea[];
}

/** Chapter 5 — navigation, not a numbered figure. */
export function SimilarAreas({ areas }: SimilarAreasProps) {
  if (areas.length === 0) {
    return null;
  }

  const section = getSection("similar");

  return (
    <section id="similar" className="scroll-mt-24 border-t border-ledger-border pt-4">
      <span className="eyebrow block text-ledger-accent">Chapter {section.chapter}</span>
      <h2 className="mt-1 font-display text-title text-ledger-text">Similar areas</h2>
      <p className="mt-1 text-caption text-ledger-dimmed">
        Comparable neighbourhoods by price tier and market profile
      </p>

      <div className="mt-4 grid gap-3 md:grid-cols-3">
        {areas.map((area) => (
          <Link
            key={area.area_name}
            href={`/area/${area.area_name}`}
            className="focus-ring group block rounded-sm border border-ledger-border bg-ledger-surface p-5 transition-colors hover:border-ledger-border-emphasis hover:bg-ledger-elevated/50"
          >
            <div className="flex items-start justify-between gap-2">
              <h3 className="font-display text-heading text-ledger-text transition-colors group-hover:text-ledger-accent">
                {area.display_name}
              </h3>
              <TierChip tier={area.price_tier} />
            </div>

            <dl className="mt-4 space-y-2 text-body-sm">
              <div className="flex items-baseline justify-between border-t border-ledger-border pt-2">
                <dt className="text-ledger-muted">Avg price</dt>
                <dd className="num font-medium text-ledger-text">{formatSek(area.avg_sold_price)}</dd>
              </div>
              <div className="flex items-baseline justify-between border-t border-ledger-border pt-2">
                <dt className="text-ledger-muted">Properties</dt>
                <dd className="num font-medium text-ledger-text">
                  {formatNumber(area.listing_count)}
                </dd>
              </div>
              <div className="flex items-baseline justify-between border-t border-ledger-border pt-2">
                <dt className="text-ledger-muted">Undervalued</dt>
                <dd className="num font-medium text-val-exc">
                  {formatNumberOrDash(area.undervalued_pct, 1)}%
                </dd>
              </div>
            </dl>
          </Link>
        ))}
      </div>
    </section>
  );
}
