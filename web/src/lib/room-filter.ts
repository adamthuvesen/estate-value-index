import type { RoomFilter } from "@/lib/area-types";

export const ROOM_FILTERS: readonly RoomFilter[] = ["all", "1", "2", "3", "4+"];

/** Validate a raw `?rooms=` query value; anything unknown falls back to "all".
 *  Plain module (no "use client") so the server page can call it too. */
export function parseRoomFilter(raw: string | string[] | undefined): RoomFilter {
  return typeof raw === "string" && (ROOM_FILTERS as readonly string[]).includes(raw)
    ? (raw as RoomFilter)
    : "all";
}
