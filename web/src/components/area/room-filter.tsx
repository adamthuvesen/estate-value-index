"use client";

import type { RoomFilter, RoomFilteredStatistics } from "@/lib/area-types";

interface RoomFilterProps {
  selectedFilter: RoomFilter;
  onFilterChange: (filter: RoomFilter) => void;
  roomData: Record<RoomFilter, RoomFilteredStatistics> | undefined;
}

export function RoomFilterComponent({
  selectedFilter,
  onFilterChange,
  roomData,
}: RoomFilterProps) {
  if (!roomData) {
    return null;
  }

  const filters: { key: RoomFilter; label: string }[] = [
    { key: "all", label: "All" },
    { key: "2", label: "2 rooms" },
    { key: "3", label: "3 rooms" },
    { key: "4+", label: "4+ rooms" },
  ];

  return (
    <div className="mx-auto mb-6 max-w-3xl">
      <div className="flex items-center gap-4 rounded-xl border border-ledger-border bg-ledger-elevated px-4 py-3">
        <div>
          <span className="text-[11px] font-semibold uppercase tracking-eyebrow text-ledger-dimmed">Rooms</span>
        </div>
        <div className="flex flex-1 flex-wrap gap-1.5">
          {filters.map(({ key, label }) => {
          const stats = roomData[key];
          const isActive = selectedFilter === key;
          const isDisabled = !stats;

          return (
            <button
              key={key}
              onClick={() => !isDisabled && onFilterChange(key)}
              disabled={isDisabled}
              className={`
                flex items-center gap-1.5 rounded-pill border px-3 py-1.5 text-[13px] font-medium transition-colors
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
