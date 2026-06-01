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
    { key: "all", label: "ALL" },
    { key: "2", label: "2R" },
    { key: "3", label: "3R" },
    { key: "4+", label: "4+R" },
  ];

  return (
    <div className="mx-auto mb-6 max-w-3xl">
      <div className="flex items-center gap-4 rounded-tactical border border-tactical-border bg-tactical-elevated px-4 py-3">
        <div>
          <label className="tactical-label text-[10px]">ROOMS</label>
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
                flex items-center gap-1.5 rounded-tactical border px-3 py-1.5 font-mono text-[10px] font-semibold uppercase tracking-tactical transition-all duration-tactical
                ${
                  isActive
                    ? "border-tactical-accent bg-tactical-accent text-tactical-bg shadow-[0_0_15px_rgba(255,51,51,0.2)]"
                    : isDisabled
                    ? "cursor-not-allowed border-tactical-border bg-tactical-surface text-tactical-dimmed opacity-30"
                    : "border-tactical-border bg-tactical-surface text-tactical-text hover:border-tactical-accent-hover hover:text-tactical-accent-hover"
                }
              `}
            >
              <span>{label}</span>
              {stats && (
                <span
                  className={`text-[9px] font-normal ${
                    isActive ? "text-tactical-bg/70" : "text-tactical-muted"
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
