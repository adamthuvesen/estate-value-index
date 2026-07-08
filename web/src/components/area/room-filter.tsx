"use client";

import type { RoomFilter } from "@/lib/area-types";
import { useRoomFilter } from "@/components/area/room-filter-provider";

const FILTERS: { key: RoomFilter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "2", label: "2 rooms" },
  { key: "3", label: "3 rooms" },
  { key: "4+", label: "4+ rooms" },
];

export function RoomFilterComponent() {
  const { filter, setFilter, roomData } = useRoomFilter();

  if (!roomData) {
    return null;
  }

  return (
    <div className="mx-auto mb-6 max-w-3xl">
      <div className="flex items-center gap-4 rounded-xl border border-ledger-border bg-ledger-elevated px-4 py-3">
        <span className="eyebrow">Rooms</span>
        <div className="flex flex-1 flex-wrap gap-1.5">
          {FILTERS.map(({ key, label }) => {
            const stats = roomData[key];
            const isActive = filter === key;
            const isDisabled = !stats;

            return (
              <button
                key={key}
                onClick={() => !isDisabled && setFilter(key)}
                disabled={isDisabled}
                aria-pressed={isActive}
                className={`
                  focus-ring flex items-center gap-1.5 rounded-pill border px-3 py-1.5 text-[13px] font-medium transition-colors
                  ${
                    isActive
                      ? "border-ledger-text bg-ledger-text text-white"
                      : isDisabled
                        ? "cursor-not-allowed border-ledger-border bg-ledger-surface text-ledger-dimmed opacity-40"
                        : "border-ledger-border bg-ledger-surface text-ledger-muted hover:border-ledger-border-emphasis hover:text-ledger-text"
                  }
                `}
              >
                <span>{label}</span>
                {stats && (
                  <span
                    className={`num text-[12px] font-normal ${
                      isActive ? "text-white/70" : "text-ledger-dimmed"
                    }`}
                  >
                    ({stats.property_count})
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}
