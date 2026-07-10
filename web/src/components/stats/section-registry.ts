/**
 * Chapter and figure numbering for the city-wide statistics report (`/stats`).
 * Same contract as the area report's registry — numbering is real and
 * referenceable, consumed by the contents rail and every FigureFrame.
 */
export type FigureKind = "figure" | "table";

export interface StatsSection {
  /** Anchor id — also the scrollspy target. */
  id: string;
  /** Chapter number within the report (1-based). */
  chapter: number;
  title: string;
}

export const STATS_SECTIONS: readonly StatsSection[] = [
  { id: "prices", chapter: 1, title: "Prices" },
  { id: "over-time", chapter: 2, title: "Over time" },
  { id: "bidding", chapter: 3, title: "Bidding" },
  { id: "geography", chapter: 4, title: "Geography" },
  { id: "size-rooms", chapter: 5, title: "Size & rooms" },
  { id: "building", chapter: 6, title: "Building & amenities" },
  { id: "records", chapter: 7, title: "The record book" },
] as const;
