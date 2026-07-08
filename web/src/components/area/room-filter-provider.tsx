"use client";

import { createContext, useContext, useState, type ReactNode } from "react";
import type { RoomFilter, RoomFilteredStatistics } from "@/lib/area-types";

interface RoomFilterContextValue {
  filter: RoomFilter;
  setFilter: (filter: RoomFilter) => void;
  /** Stats for the active filter, or null when the bucket doesn't exist. */
  stats: RoomFilteredStatistics | null;
  roomData: Record<RoomFilter, RoomFilteredStatistics> | undefined;
}

const RoomFilterContext = createContext<RoomFilterContextValue | null>(null);

/**
 * Client island holding the room-filter state over the already-shipped
 * `by_room_count` payload. Toggling is instant (no server round trip); the
 * URL stays shareable via shallow `history.replaceState` — deep links like
 * `?rooms=3` are validated and server-rendered by the page.
 */
export function RoomFilterProvider({
  initialFilter,
  roomData,
  children,
}: {
  initialFilter: RoomFilter;
  roomData: Record<RoomFilter, RoomFilteredStatistics> | undefined;
  children: ReactNode;
}) {
  const [filter, setFilterState] = useState<RoomFilter>(initialFilter);

  const setFilter = (next: RoomFilter) => {
    setFilterState(next);
    const url = new URL(window.location.href);
    if (next === "all") {
      url.searchParams.delete("rooms");
    } else {
      url.searchParams.set("rooms", next);
    }
    // Shallow: keep the URL shareable without a server re-render.
    window.history.replaceState(null, "", url);
  };

  const stats = roomData?.[filter] ?? null;

  return (
    <RoomFilterContext.Provider value={{ filter, setFilter, stats, roomData }}>
      {children}
    </RoomFilterContext.Provider>
  );
}

export function useRoomFilter(): RoomFilterContextValue {
  const ctx = useContext(RoomFilterContext);
  if (!ctx) {
    throw new Error("useRoomFilter must be used inside <RoomFilterProvider>");
  }
  return ctx;
}
