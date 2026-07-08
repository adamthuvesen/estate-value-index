/**
 * Single source of truth for the area report's chapter and figure numbering.
 * Consumed by the contents rail and every FigureFrame on the page — numbering
 * is real and referenceable ("see Fig. 1"), never decorative.
 */
export type FigureKind = "figure" | "table";

export interface AreaSection {
  /** Anchor id — also the scrollspy target. */
  id: string;
  /** Chapter number within the report (1-based). */
  chapter: number;
  title: string;
  /** The numbered figure/table this chapter carries, if any. */
  figure?: { kind: FigureKind; index: number; title: string };
}

export const AREA_SECTIONS: readonly AreaSection[] = [
  {
    id: "market",
    chapter: 1,
    title: "Market dynamics",
    figure: { kind: "figure", index: 1, title: "Price trend" },
  },
  {
    id: "value",
    chapter: 2,
    title: "Value",
    figure: { kind: "figure", index: 2, title: "Value-tier distribution" },
  },
  {
    id: "size",
    chapter: 3,
    title: "Size & price",
    figure: { kind: "figure", index: 3, title: "Price by size" },
  },
  {
    id: "building-stock",
    chapter: 4,
    title: "Building stock",
    figure: { kind: "figure", index: 4, title: "Construction era" },
  },
  { id: "similar", chapter: 5, title: "Similar areas" },
  {
    id: "recent",
    chapter: 6,
    title: "Recent sales",
    figure: { kind: "table", index: 1, title: "Latest recorded sales" },
  },
] as const;

export function getSection(id: string): AreaSection {
  const section = AREA_SECTIONS.find((s) => s.id === id);
  if (!section) {
    throw new Error(`Unknown area section: ${id}`);
  }
  return section;
}
