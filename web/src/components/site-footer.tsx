import Link from "next/link";

import { siteConfig } from "@/config/site";

export function SiteFooter() {
  return (
    <footer className="border-t border-tactical-border bg-tactical-surface/95">
      <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-8 text-xs font-mono sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className="text-tactical-muted tracking-tactical">
          © {new Date().getFullYear()} {siteConfig.name.toUpperCase()} CLASSIFIED INTEL SYSTEM
        </p>
        <div className="flex items-center gap-6">
          <Link href={siteConfig.social.github} className="tactical-label hover:text-tactical-accent transition-colors duration-tactical">
            GITHUB
          </Link>
        </div>
      </div>
    </footer>
  );
}
