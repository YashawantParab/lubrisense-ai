import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output keeps the production Docker image small (only the traced
  // dependency subset is copied in) — see frontend/Dockerfile. Disabled on Vercel:
  // Next.js 16.3's standalone output trips a Vercel adapter incompatibility
  // (onBuildComplete fails with ENOENT on .next/next-server.js.nft.json) — Vercel's
  // own build output API supersedes standalone there anyway, so this only affects
  // local/Docker builds.
  output: process.env.VERCEL ? undefined : "standalone",
};

export default nextConfig;
