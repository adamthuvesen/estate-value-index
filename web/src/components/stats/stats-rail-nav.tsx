"use client";

import { useEffect, useState } from "react";
import { STATS_SECTIONS } from "@/components/stats/section-registry";
import { cn } from "@/lib/cn";

/** Sticky contents rail with IntersectionObserver scrollspy. Reduced-motion
 *  aware: smooth scroll is skipped when the user asks for less motion. */
export function StatsRailNav() {
  const [active, setActive] = useState<string>(STATS_SECTIONS[0]?.id ?? "");

  useEffect(() => {
    const ids = STATS_SECTIONS.map((s) => s.id);
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
        {STATS_SECTIONS.map((section) => {
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
                <span
                  className={cn(
                    "num text-caption",
                    isActive ? "text-ledger-accent" : "text-ledger-dimmed",
                  )}
                >
                  {String(section.chapter).padStart(2, "0")}
                </span>
                {isActive && (
                  <span className="h-1.5 w-1.5 rounded-full bg-ledger-accent" aria-hidden />
                )}
                <span className="flex-1">{section.title}</span>
              </a>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
