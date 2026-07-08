import Link from "next/link";
import { getAreaOverviewList } from "@/lib/area-overview";
import type { AreaOverview } from "@/lib/area-types";

/** 404 for unknown area slugs, with a few real areas to jump to instead. */
export default async function AreaNotFound() {
  let suggestions: AreaOverview[] = [];
  try {
    const areas = await getAreaOverviewList();
    suggestions = areas.slice(0, 4); // already sorted by listing_count desc
  } catch {
    // No data available — the plain 404 still stands on its own.
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8 lg:py-14">
      <div className="mx-auto mt-4 max-w-xl rounded-2xl border border-ledger-border bg-ledger-surface px-6 py-12 text-center shadow-elev-1">
        <p className="eyebrow text-ledger-dimmed">Area report</p>
        <h1 className="mt-3 font-display text-title text-ledger-text">Area not found</h1>
        <p className="mt-3 text-[14px] text-ledger-muted">
          No statistics are recorded under this name. It may be spelled differently in the
          register, or the area has too few sales to report on.
        </p>

        {suggestions.length > 0 && (
          <div className="mt-6">
            <p className="eyebrow">Largest areas</p>
            <ul className="mt-2 flex flex-wrap justify-center gap-2">
              {suggestions.map((area) => (
                <li key={area.area_name}>
                  <Link
                    href={`/area/${area.area_name}`}
                    className="focus-ring inline-flex rounded-pill border border-ledger-border bg-ledger-elevated px-3 py-1 text-[13px] font-medium text-ledger-muted transition-colors hover:border-ledger-border-emphasis hover:text-ledger-text"
                  >
                    {area.display_name}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        )}

        <Link href="/areas" className="ledger-btn focus-ring mt-8 inline-flex text-[13px]">
          Browse the area register
        </Link>
      </div>
    </div>
  );
}
