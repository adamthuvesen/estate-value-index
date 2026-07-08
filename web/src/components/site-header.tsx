"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { siteConfig } from "@/config/site";

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

function chapterIndex(order: number): string {
  return String(order + 1).padStart(2, "0");
}

export function SiteHeader() {
  const pathname = usePathname() ?? "/";
  const [menuOpen, setMenuOpen] = useState(false);
  const [menuPath, setMenuPath] = useState(pathname);
  const currentYear = new Date().getFullYear();

  // Close the mobile disclosure on route change (adjust state during render;
  // avoids a cascading-render effect).
  if (pathname !== menuPath) {
    setMenuPath(pathname);
    setMenuOpen(false);
  }

  const hasNav = siteConfig.navItems.length > 0;

  return (
    <header className="sticky top-0 z-40 border-b border-ledger-border bg-ledger-bg/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <div className="flex h-full items-center gap-8">
          <Link href="/" className="focus-ring flex items-center gap-2.5">
            <span
              className="flex h-6 w-6 items-center justify-center rounded-[7px] bg-ledger-text text-white"
              aria-hidden
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <path d="M2 7.2 8 2.5l6 4.7V14H10v-3.6H6V14H2V7.2Z" fill="currentColor" />
              </svg>
            </span>
            <span className="font-display text-heading tracking-tight text-ledger-text">
              {siteConfig.name}
            </span>
          </Link>
          {hasNav && (
            <nav className="hidden h-full items-center gap-2 md:flex">
              {siteConfig.navItems.map((item, order) => {
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`inline-flex h-9 items-center gap-1.5 rounded-sm px-2.5 text-body-sm font-medium transition-colors duration-ledger focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ledger-accent/35 focus-visible:ring-offset-2 focus-visible:ring-offset-ledger-bg ${
                      active
                        ? "bg-ledger-accent-tint text-ledger-text"
                        : "text-ledger-muted hover:bg-ledger-elevated/70 hover:text-ledger-text"
                    }`}
                  >
                    <span
                      className={`font-mono text-caption ${active ? "text-ledger-accent" : "text-ledger-dimmed"}`}
                      aria-hidden
                    >
                      {chapterIndex(order)}
                    </span>
                    {active && <span className="h-1.5 w-1.5 rounded-full bg-ledger-accent" aria-hidden />}
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          )}
        </div>
        <div className="flex items-center gap-3">
          <span className="hidden font-mono text-eyebrow uppercase tracking-eyebrow text-ledger-dimmed sm:inline">
            Stockholm · {currentYear}
          </span>
          {hasNav && (
            <button
              type="button"
              aria-label="Toggle navigation"
              aria-expanded={menuOpen}
              aria-controls="mobile-nav"
              onClick={() => setMenuOpen((open) => !open)}
              className="focus-ring -mr-1 inline-flex h-9 w-9 items-center justify-center rounded-sm text-ledger-muted hover:text-ledger-text md:hidden"
            >
              <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden>
                {menuOpen ? (
                  <path
                    d="M4 4l10 10M14 4L4 14"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                ) : (
                  <path
                    d="M2.5 5h13M2.5 9h13M2.5 13h13"
                    stroke="currentColor"
                    strokeWidth="1.6"
                    strokeLinecap="round"
                  />
                )}
              </svg>
            </button>
          )}
        </div>
      </div>
      {hasNav && menuOpen && (
        <nav
          id="mobile-nav"
          className="border-t border-ledger-border bg-ledger-bg md:hidden"
        >
          <ul className="mx-auto flex max-w-7xl flex-col px-4 py-2 sm:px-6">
            {siteConfig.navItems.map((item, order) => {
              const active = isActive(pathname, item.href);
              return (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`flex items-center gap-2.5 rounded-sm px-2 py-3 text-body font-medium transition-colors duration-ledger focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-ledger-accent/35 focus-visible:ring-offset-2 focus-visible:ring-offset-ledger-bg ${
                      active
                        ? "bg-ledger-accent-tint text-ledger-text"
                        : "text-ledger-muted hover:bg-ledger-elevated/70 hover:text-ledger-text"
                    }`}
                  >
                    <span
                      className={`font-mono text-caption ${active ? "text-ledger-accent" : "text-ledger-dimmed"}`}
                      aria-hidden
                    >
                      {chapterIndex(order)}
                    </span>
                    {active && <span className="h-1.5 w-1.5 rounded-full bg-ledger-accent" aria-hidden />}
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
      )}
    </header>
  );
}
