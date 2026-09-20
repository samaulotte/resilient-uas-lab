import path from "node:path";

import type { NextConfig } from "next";

// In development the API usually runs on another port; NEXT_PUBLIC_API_BASE points the
// browser at it directly (CORS is enabled for localhost origins). In the Compose
// deployment the gateway serves UI and API on one origin and the variable stays empty.
const apiBase = process.env.NEXT_PUBLIC_API_BASE ?? "";

const securityHeaders = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "Referrer-Policy", value: "no-referrer" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
];

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.join(__dirname, "../../"),
  reactStrictMode: true,
  poweredByHeader: false,
  transpilePackages: ["@reslab/api-client"],
  typescript: { ignoreBuildErrors: false },
  async headers() {
    return [{ source: "/:path*", headers: securityHeaders }];
  },
  async redirects() {
    return [{ source: "/", destination: "/mission-control", permanent: false }];
  },
  env: {
    NEXT_PUBLIC_API_BASE: apiBase,
  },
};

export default nextConfig;
