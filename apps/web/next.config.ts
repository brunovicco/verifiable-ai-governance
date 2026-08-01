import type { NextConfig } from "next";
import path from "node:path";

import { parsePortalAuthConfig } from "./lib/auth/config";

parsePortalAuthConfig({
  mode: process.env.NEXT_PUBLIC_AUTH_MODE,
  clientId: process.env.NEXT_PUBLIC_ENTRA_CLIENT_ID,
  tenantId: process.env.NEXT_PUBLIC_ENTRA_TENANT_ID,
  apiScope: process.env.NEXT_PUBLIC_ENTRA_API_SCOPE,
});

const nextConfig: NextConfig = {
  output: "standalone",
  outputFileTracingRoot: path.resolve(process.cwd(), "../.."),
  turbopack: {
    root: path.resolve(process.cwd(), "../.."),
  },
};

export default nextConfig;
