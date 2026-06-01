import Link from "next/link";

import { siteConfig } from "@/config/site";

export function SiteHeader() {
  return (
    <header className="border-b border-tactical-border bg-tactical-surface/95 sticky top-0 z-40 backdrop-blur-sm">
      <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6">
        <div className="flex items-center gap-6">
          <Link href="/" className="flex items-center gap-3 font-bold">
            <div className="w-2 h-2 bg-tactical-accent animate-glow-pulse" aria-hidden />
            <span className="text-tactical-text text-sm tracking-tactical-wide uppercase">{siteConfig.name}</span>
          </Link>
          {siteConfig.navItems.length > 0 && (
            <nav className="hidden md:flex items-center gap-1">
              {siteConfig.navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="tactical-label px-3 py-2 transition-all duration-tactical hover:text-tactical-accent hover:bg-tactical-elevated"
                >
                  {item.label.toUpperCase()}
                </Link>
              ))}
            </nav>
          )}
        </div>
        <span className="tactical-label hidden sm:inline">STOCKHOLM INTEL</span>
      </div>
    </header>
  );
}
