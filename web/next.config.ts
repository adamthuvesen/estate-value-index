import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Performance optimizations
  reactStrictMode: true,
  poweredByHeader: false,

  // The build type-checks app code only. Tests import fixtures shared with the Python
  // tests from outside web/, which the Docker build context does not include.
  // `npm run typecheck` still type-checks the tests through tsconfig.json.
  typescript: {
    tsconfigPath: "tsconfig.build.json",
  },

  compiler: {
    removeConsole: process.env.NODE_ENV === "production",
  },
};

export default nextConfig;
