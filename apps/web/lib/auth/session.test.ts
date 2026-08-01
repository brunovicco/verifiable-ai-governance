import {
  InteractionRequiredAuthError,
  type AccountInfo,
  type AuthenticationResult,
  type RedirectRequest,
  type SilentRequest,
} from "@azure/msal-browser";
import { describe, expect, it, vi } from "vitest";

import type { EntraPortalAuthConfig } from "@/lib/auth/config";
import {
  acquireApiAccessToken,
  loginRequest,
  PortalAuthenticationRequired,
  type MsalTokenClient,
} from "@/lib/auth/session";

const config: EntraPortalAuthConfig = {
  mode: "entra",
  clientId: "11111111-1111-4111-8111-111111111111",
  tenantId: "22222222-2222-4222-8222-222222222222",
  apiScope: "api://11111111-1111-4111-8111-111111111111/access_as_user",
  authority: "https://login.microsoftonline.com/22222222-2222-4222-8222-222222222222",
};

const account: AccountInfo = {
  homeAccountId: "home",
  environment: "login.microsoftonline.com",
  tenantId: config.tenantId,
  username: "reviewer@example.com",
  localAccountId: "local",
};

class FakeTokenClient implements MsalTokenClient {
  activeAccount: AccountInfo | null = null;
  accounts: AccountInfo[] = [account];
  result: Promise<AuthenticationResult> = Promise.resolve({
    accessToken: "api-access-token",
  } as AuthenticationResult);
  redirect = vi.fn(async (_request: RedirectRequest) => undefined);

  getActiveAccount(): AccountInfo | null {
    return this.activeAccount;
  }

  getAllAccounts(): AccountInfo[] {
    return this.accounts;
  }

  setActiveAccount(value: AccountInfo | null): void {
    this.activeAccount = value;
  }

  acquireTokenSilent(_request: SilentRequest): Promise<AuthenticationResult> {
    return this.result;
  }

  acquireTokenRedirect(request: RedirectRequest): Promise<void> {
    return this.redirect(request);
  }
}

describe("acquireApiAccessToken", () => {
  it("selects the only cached account and acquires the API token silently", async () => {
    const client = new FakeTokenClient();

    await expect(acquireApiAccessToken(client, config)).resolves.toBe("api-access-token");
    expect(client.activeAccount).toBe(account);
    expect(client.redirect).not.toHaveBeenCalled();
  });

  it("fails closed when no corporate account is available", async () => {
    const client = new FakeTokenClient();
    client.accounts = [];

    await expect(acquireApiAccessToken(client, config)).rejects.toBeInstanceOf(
      PortalAuthenticationRequired,
    );
  });

  it("starts an interactive redirect when Conditional Access requires it", async () => {
    const client = new FakeTokenClient();
    client.activeAccount = account;
    client.result = Promise.reject(
      new InteractionRequiredAuthError("interaction_required", "correlation-id"),
    );

    await expect(acquireApiAccessToken(client, config)).rejects.toThrow(
      "Reautenticação iniciada",
    );
    expect(client.redirect).toHaveBeenCalledWith(
      expect.objectContaining({ account, scopes: [config.apiScope] }),
    );
  });
});

describe("loginRequest", () => {
  it("requests only the identity claims and delegated API scope needed by the portal", () => {
    expect(loginRequest(config)).toEqual({
      scopes: ["openid", "profile", config.apiScope],
      prompt: "select_account",
    });
  });
});
