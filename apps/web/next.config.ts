import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  /* Dev: use `npm run dev` (next dev --webpack). Plain `next dev` uses Turbopack and can panic with "Next.js package not found" on /tasks. */
};

export default nextConfig;
