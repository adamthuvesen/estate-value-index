import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Performance optimizations
  reactStrictMode: true,
  poweredByHeader: false,
  // Next 16 type-checks at build time through typescript/lib/typescript.js, which TypeScript 7
  // does not ship. `just check` runs tsc, and `just slow` runs it again after the build.
  typescript: { ignoreBuildErrors: true },

  compiler: {
    removeConsole: process.env.NODE_ENV === "production",
  },
};

export default nextConfig;
