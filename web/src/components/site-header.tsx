"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { siteConfig } from "@/config/site";

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function SiteHeader() {
  const pathname = usePathname() ?? "/";

  return (
    <header className="sticky top-0 z-40 border-b border-ledger-border bg-ledger-bg/80 backdrop-blur-md">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-8">
          <Link href="/" className="group flex items-center gap-2.5">
            <span
              className="flex h-6 w-6 items-center justify-center rounded-[7px] bg-ledger-text text-white"
              aria-hidden
            >
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                <path d="M2 7.2 8 2.5l6 4.7V14H10v-3.6H6V14H2V7.2Z" fill="currentColor" />
              </svg>
            </span>
            <span className="text-[15px] font-semibold tracking-tight text-ledger-text">
              {siteConfig.name}
            </span>
          </Link>
          {siteConfig.navItems.length > 0 && (
            <nav className="hidden items-center gap-1 md:flex">
              {siteConfig.navItems.map((item) => {
                const active = isActive(pathname, item.href);
                return (
                  <Link
                    key={item.href}
                    href={item.href}
                    aria-current={active ? "page" : undefined}
                    className={`rounded-md px-3 py-1.5 text-sm font-medium transition-colors duration-ledger ${
                      active
                        ? "bg-ledger-elevated text-ledger-text"
                        : "text-ledger-muted hover:text-ledger-text hover:bg-ledger-elevated/60"
                    }`}
                  >
                    {item.label}
                  </Link>
                );
              })}
            </nav>
          )}
        </div>
        <div className="flex items-center gap-2 text-ledger-dimmed">
          <span className="hidden h-1.5 w-1.5 rounded-full bg-val-exc sm:inline-block" aria-hidden />
          <span className="hidden text-xs font-medium tracking-tight text-ledger-muted sm:inline">
            Stockholm
          </span>
        </div>
      </div>
    </header>
  );
}
