import Link from "next/link";

import { siteConfig } from "@/config/site";

export function SiteFooter() {
  return (
    <footer className="mt-8 border-t border-ledger-border">
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-8 sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <div className="flex items-center gap-2.5">
          <span className="flex h-5 w-5 items-center justify-center rounded-[6px] bg-ledger-text text-white" aria-hidden>
            <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
              <path d="M2 7.2 8 2.5l6 4.7V14H10v-3.6H6V14H2V7.2Z" fill="currentColor" />
            </svg>
          </span>
          <p className="text-[13px] text-ledger-muted">
            {siteConfig.name} · Stockholm valuations from machine learning
          </p>
        </div>
        <div className="flex items-center gap-5 text-[13px]">
          <span className="text-ledger-dimmed">© {new Date().getFullYear()}</span>
          <Link
            href={siteConfig.social.github}
            target="_blank"
            rel="noopener noreferrer"
            className="font-medium text-ledger-muted transition-colors hover:text-ledger-text"
          >
            GitHub
          </Link>
        </div>
      </div>
    </footer>
  );
}
