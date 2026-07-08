import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type FigureKind = "table" | "figure" | "panel";

interface FigureFrameProps {
  kind: FigureKind;
  /** Figure/table number. Omitted for panels (instruments, not figures). */
  index?: number;
  title: string;
  /** Source / updated line under the title. Amber when `stale`. */
  meta?: ReactNode;
  stale?: boolean;
  /** Right-aligned controls in the caption bar (toggles, links). */
  actions?: ReactNode;
  footnote?: ReactNode;
  /** Anchor id for in-page figure references and scrollspy. */
  id?: string;
  className?: string;
  children: ReactNode;
}

const KIND_LABEL: Record<Exclude<FigureKind, "panel">, string> = {
  figure: "FIG.",
  table: "TABLE",
};

export function FigureFrame({
  kind,
  index,
  title,
  meta,
  stale = false,
  actions,
  footnote,
  id,
  className,
  children,
}: FigureFrameProps) {
  const label =
    kind !== "panel" && index !== undefined ? `${KIND_LABEL[kind]} ${index}` : null;

  return (
    <section id={id} className={cn("scroll-mt-24 border-t-2 border-ledger-text pt-4", className)}>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3">
        <div className="min-w-0">
          {label && (
            <span className="eyebrow block text-ledger-accent">{label}</span>
          )}
          <h2 className="mt-1 font-display text-title text-ledger-text">{title}</h2>
          {meta && (
            <p
              className={cn(
                "mt-1 text-caption",
                stale ? "text-val-over" : "text-ledger-dimmed",
              )}
            >
              {meta}
            </p>
          )}
        </div>
        {actions && (
          <div className="flex shrink-0 items-center gap-2">{actions}</div>
        )}
      </div>

      <div className="ledger-card mt-4 rounded-t-none border-t-0 p-4 shadow-none sm:p-5">
        {children}
      </div>

      {footnote && (
        <p className="mt-2.5 text-caption text-ledger-dimmed">{footnote}</p>
      )}
    </section>
  );
}
