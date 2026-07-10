import type { ReactNode } from "react";

interface SectionIntroProps {
  /** Two-digit chapter, e.g. "01". */
  chapter: string;
  title: string;
  lead: ReactNode;
}

/** Chapter header shown above a section's figures — mirrors the hero's eyebrow
 *  rhythm so each section reads as a chapter of the same report. */
export function SectionIntro({ chapter, title, lead }: SectionIntroProps) {
  return (
    <div className="max-w-2xl">
      <p className="eyebrow flex items-center gap-2 text-ledger-muted">
        <span className="num text-ledger-accent">{chapter}</span>
        <span aria-hidden className="text-ledger-border-emphasis">
          ·
        </span>
        <span>{title}</span>
      </p>
      <p className="mt-3 text-body text-ledger-muted text-balance">{lead}</p>
    </div>
  );
}
