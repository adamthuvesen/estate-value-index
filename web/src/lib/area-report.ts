import type { RoomFilter } from "@/lib/area-types";
import { formatDateSv } from "@/lib/format";

/** Human room-scope note for a figure meta line, e.g. `3-room properties (n=48)`. */
export function roomScopeNote(filter: RoomFilter, n: number | null | undefined): string | null {
  if (filter === "all") return null;
  const label = filter === "4+" ? "4+-room" : `${filter}-room`;
  return typeof n === "number" ? `${label} properties (n=${n})` : `${label} properties`;
}

/** `Source: Booli sold listings · Updated {date}` with an optional room-scope suffix. */
export function figureMeta(updatedAt: string, roomNote?: string | null): string {
  const base = `Source: Booli sold listings · Updated ${formatDateSv(updatedAt)}`;
  return roomNote ? `${base} · ${roomNote}` : base;
}
