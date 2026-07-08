import type { ReactNode } from "react";

interface PageHeroProps {
  /** Chapter index, e.g. "01". Rendered in the mono eyebrow. */
  chapter: string;
  /** Chapter name, e.g. "Predictor". Joined with the chapter as `01 · Predictor`. */
  eyebrow: string;
  title: string;
  lead?: ReactNode;
  children?: ReactNode;
}

export function PageHero({ chapter, eyebrow, title, lead, children }: PageHeroProps) {
  return (
    <header className="border-t-2 border-ledger-text pt-5">
      <p className="eyebrow flex items-center gap-2 text-ledger-muted">
        <span className="num text-ledger-text">{chapter}</span>
        <span aria-hidden className="text-ledger-border-emphasis">
          ·
        </span>
        <span>{eyebrow}</span>
      </p>
      <h1 className="mt-3 font-display text-display text-ledger-text text-balance">
        {title}
      </h1>
      {lead && (
        <p className="mt-4 max-w-2xl text-body text-ledger-muted text-balance">{lead}</p>
      )}
      {children && <div className="mt-6">{children}</div>}
    </header>
  );
}
