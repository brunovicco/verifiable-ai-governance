import { describe, expect, it, vi } from "vitest";

import { applyRequestAuthentication } from "@/lib/auth/request";

const entraConfig = {
  mode: "entra" as const,
  clientId: "11111111-1111-4111-8111-111111111111",
  tenantId: "22222222-2222-4222-8222-222222222222",
  apiScope: "api://11111111-1111-4111-8111-111111111111/access_as_user",
  authority: "https://login.microsoftonline.com/22222222-2222-4222-8222-222222222222",
};

describe("applyRequestAuthentication", () => {
  it("uses explicit development headers only in local mode", async () => {
    const headers = new Headers({ Authorization: "Bearer stale" });

    await applyRequestAuthentication(
      headers,
      { userId: "local.reviewer", areas: ["security"] },
      { mode: "local" },
    );

    expect(headers.get("Authorization")).toBeNull();
    expect(headers.get("X-User-Id")).toBe("local.reviewer");
    expect(headers.get("X-User-Areas")).toBe("security");
  });

  it("removes caller-controlled identity and sends only the API bearer token", async () => {
    const headers = new Headers({
      "X-User-Id": "impersonated.user",
      "X-User-Areas": "security",
    });
    const tokenProvider = vi.fn().mockResolvedValue("api-access-token");

    await applyRequestAuthentication(
      headers,
      { userId: "ignored", areas: ["security"] },
      entraConfig,
      tokenProvider,
    );

    expect(headers.get("Authorization")).toBe("Bearer api-access-token");
    expect(headers.get("X-User-Id")).toBeNull();
    expect(headers.get("X-User-Areas")).toBeNull();
    expect(tokenProvider).toHaveBeenCalledOnce();
  });
});
