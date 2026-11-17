import type { NextConfig } from "next";
const config: NextConfig = {
  output: "standalone",
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${process.env.API_INTERNAL_URL || "http://127.0.0.1:8001"}/api/:path*/`,
      },
    ];
  },
};
export default config;
