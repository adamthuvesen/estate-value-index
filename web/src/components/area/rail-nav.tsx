"use client";

import { useEffect, useState } from "react";
import { AREA_SECTIONS } from "@/components/area/section-registry";
import { cn } from "@/lib/cn";

const FIGURE_REF: Record<string, string> = Object.fromEntries(
  AREA_SECTIONS.filter((s) => s.figure).map((s) => [
    s.id,
    s.figure!.kind === "table" ? `Table ${s.figure!.index}` : `Fig. ${s.figure!.index}`,
  ]),
);

/** Sticky contents rail with IntersectionObserver scrollspy. Reduced-motion
 *  aware: smooth scroll is skipped when the user asks for less motion. */
export function RailNav() {
  const [active, setActive] = useState<string>(AREA_SECTIONS[0]?.id ?? "");

  useEffect(() => {
    const ids = AREA_SECTIONS.map((s) => s.id);
    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => el !== null);

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible[0]) {
          setActive(visible[0].target.id);
        }
      },
      { rootMargin: "-96px 0px -60% 0px", threshold: 0 },
    );

    elements.forEach((el) => observer.observe(el));
    return () => observer.disconnect();
  }, []);

  const handleClick = (event: React.MouseEvent<HTMLAnchorElement>, id: string) => {
    const target = document.getElementById(id);
    if (!target) return;
    event.preventDefault();
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    window.history.replaceState(null, "", `#${id}`);
    setActive(id);
  };

  return (
    <nav aria-label="Report contents">
      <p className="eyebrow text-ledger-dimmed">Contents</p>
      <ol className="mt-3 space-y-0.5">
        {AREA_SECTIONS.map((section) => {
          const isActive = active === section.id;
          return (
            <li key={section.id}>
              <a
                href={`#${section.id}`}
                onClick={(e) => handleClick(e, section.id)}
                aria-current={isActive ? "true" : undefined}
                className={cn(
                  "group flex items-baseline gap-2.5 rounded-sm px-2.5 py-1.5 text-body-sm transition-colors focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ledger-accent/35 focus-visible:ring-offset-2 focus-visible:ring-offset-ledger-bg",
                  isActive
                    ? "bg-ledger-accent-tint font-medium text-ledger-text"
                    : "text-ledger-muted hover:bg-ledger-elevated/70 hover:text-ledger-text",
                )}
              >
                <span className={cn("num text-caption", isActive ? "text-ledger-accent" : "text-ledger-dimmed")}>
                  {section.chapter}
                </span>
                {isActive && <span className="h-1.5 w-1.5 rounded-full bg-ledger-accent" aria-hidden />}
                <span className="flex-1">{section.title}</span>
                {FIGURE_REF[section.id] && (
                  <span className="eyebrow shrink-0 text-ledger-dimmed">
                    {FIGURE_REF[section.id]}
                  </span>
                )}
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
