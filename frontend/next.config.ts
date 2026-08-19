import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Standalone output: bundles only the production deps a request actually
  // needs into .next/standalone, so the K8s image doesn't ship the full
  // node_modules tree.
  output: "standalone",
};

export default nextConfig;
