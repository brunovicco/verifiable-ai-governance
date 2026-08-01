import { BrowserCacheLocation } from "@azure/msal-browser";
import { describe, expect, it } from "vitest";

import type { EntraPortalAuthConfig } from "@/lib/auth/config";
import { buildMsalConfiguration } from "@/lib/auth/msal";

const config: EntraPortalAuthConfig = {
  mode: "entra",
  clientId: "11111111-1111-4111-8111-111111111111",
  tenantId: "22222222-2222-4222-8222-222222222222",
  apiScope: "api://11111111-1111-4111-8111-111111111111/access_as_user",
  authority: "https://login.microsoftonline.com/22222222-2222-4222-8222-222222222222",
};

describe("buildMsalConfiguration", () => {
  it("uses tenant-specific PKCE SPA settings and session-only cache", () => {
    const result = buildMsalConfiguration(config, "https://governance.example.com");

    expect(result.auth.clientId).toBe(config.clientId);
    expect(result.auth.authority).toBe(config.authority);
    expect(result.auth.redirectUri).toBe("https://governance.example.com");
    expect(result.auth.postLogoutRedirectUri).toBe("https://governance.example.com");
    expect(result.cache?.cacheLocation).toBe(BrowserCacheLocation.SessionStorage);
    expect(result.system?.allowPlatformBroker).toBe(false);
    expect(result.system?.loggerOptions?.piiLoggingEnabled).toBe(false);
  });
});
