import { describe, expect, it } from "vitest";

import { parsePortalAuthConfig } from "@/lib/auth/config";

const CLIENT_ID = "11111111-1111-4111-8111-111111111111";
const TENANT_ID = "22222222-2222-4222-8222-222222222222";

describe("parsePortalAuthConfig", () => {
  it("defaults to an explicit local development boundary", () => {
    expect(parsePortalAuthConfig({})).toEqual({ mode: "local" });
  });

  it("builds a tenant-specific Entra authority", () => {
    expect(
      parsePortalAuthConfig({
        mode: "entra",
        clientId: CLIENT_ID,
        tenantId: TENANT_ID,
        apiScope: `api://${CLIENT_ID}/access_as_user`,
      }),
    ).toEqual({
      mode: "entra",
      clientId: CLIENT_ID,
      tenantId: TENANT_ID,
      apiScope: `api://${CLIENT_ID}/access_as_user`,
      authority: `https://login.microsoftonline.com/${TENANT_ID}`,
    });
  });

  it.each([
    [{ mode: "unknown" }, "local ou entra"],
    [{ mode: "entra", tenantId: TENANT_ID, apiScope: "api://scope" }, "CLIENT_ID"],
    [{ mode: "entra", clientId: CLIENT_ID, apiScope: "api://scope" }, "TENANT_ID"],
    [
      { mode: "entra", clientId: CLIENT_ID, tenantId: TENANT_ID, apiScope: "User.Read" },
      "scope delegado",
    ],
  ])("fails closed for invalid configuration", (environment, expected) => {
    expect(() => parsePortalAuthConfig(environment)).toThrow(expected);
  });
});
