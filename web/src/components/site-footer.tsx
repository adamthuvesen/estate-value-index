import Link from "next/link";

import { siteConfig } from "@/config/site";

export function SiteFooter() {
  return (
    <footer className="mt-8 border-t-2 border-ledger-text">
      <div className="mx-auto flex max-w-7xl flex-col gap-6 px-4 py-8 sm:px-6">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-2.5">
            <span
              className="flex h-5 w-5 items-center justify-center rounded-[6px] bg-ledger-text text-white"
              aria-hidden
            >
              <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                <path d="M2 7.2 8 2.5l6 4.7V14H10v-3.6H6V14H2V7.2Z" fill="currentColor" />
              </svg>
            </span>
            <p className="text-body-sm text-ledger-muted">
              {siteConfig.name} · Stockholm valuations from machine learning
            </p>
          </div>
          <nav className="flex flex-wrap items-center gap-5 text-body-sm">
            {siteConfig.navItems.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="focus-ring font-medium text-ledger-muted transition-colors hover:text-ledger-text"
              >
                {item.label}
              </Link>
            ))}
            <Link
              href={siteConfig.social.github}
              target="_blank"
              rel="noopener noreferrer"
              className="focus-ring font-medium text-ledger-muted transition-colors hover:text-ledger-text"
            >
              GitHub
            </Link>
            <span className="text-ledger-dimmed">© {new Date().getFullYear()}</span>
          </nav>
        </div>
        <p className="text-caption text-ledger-dimmed">
          Data: Booli sold listings · Model estimates, not appraisals
        </p>
      </div>
    </footer>
  );
}
