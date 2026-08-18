import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output keeps the production Docker image small (only the traced
  // dependency subset is copied in) — see frontend/Dockerfile.
  output: "standalone",
};

export default nextConfig;
