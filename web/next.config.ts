import type { NextConfig } from "next";

import { readSiteUrl } from "./src/lib/siteUrl";

// Stops the build and the start in production when the public address is missing or not https.
readSiteUrl(process.env.NEXT_PUBLIC_SITE_URL);

const apiUrl = process.env.API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  // Hides the round "N" badge Next.js shows in development.
  devIndicators: false,
  // Django expects the trailing slash in /api/health/.
  skipTrailingSlashRedirect: true,
  // The browser only talks to this app; /api requests are forwarded to the server.
  async rewrites() {
    return [
      { source: "/api/:path*/", destination: `${apiUrl}/api/:path*/` },
      { source: "/api/:path*", destination: `${apiUrl}/api/:path*` },
    ];
  },
};

export default nextConfig;
