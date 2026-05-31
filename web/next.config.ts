import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Performance optimizations
  reactStrictMode: true,
  poweredByHeader: false,

  compiler: {
    removeConsole: process.env.NODE_ENV === "production",
  },

  experimental: {
    turbo: {
      // Leave Turbopack enabled without custom aliases that reference removed dependencies
    },
  },
};

export default nextConfig;
