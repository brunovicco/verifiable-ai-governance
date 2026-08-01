import {
  InteractionRequiredAuthError,
  type AccountInfo,
  type AuthenticationResult,
  type PublicClientApplication,
  type RedirectRequest,
  type SilentRequest,
} from "@azure/msal-browser";

import { getPortalAuthConfig, type EntraPortalAuthConfig } from "@/lib/auth/config";
import { getMsalApplication } from "@/lib/auth/msal";

export interface MsalTokenClient {
  getActiveAccount(): AccountInfo | null;
  getAllAccounts(): AccountInfo[];
  setActiveAccount(account: AccountInfo | null): void;
  acquireTokenSilent(request: SilentRequest): Promise<AuthenticationResult>;
  acquireTokenRedirect(request: RedirectRequest): Promise<void>;
}

let interaction: Promise<void> | null = null;

export class PortalAuthenticationRequired extends Error {
  /** Create a stable user-facing authentication boundary error. */
  constructor(message: string) {
    super(message);
    this.name = "PortalAuthenticationRequired";
  }
}

/** Build the initial login request including the delegated API scope. */
export function loginRequest(config: EntraPortalAuthConfig): RedirectRequest {
  return {
    scopes: ["openid", "profile", config.apiScope],
    prompt: "select_account",
  };
}

/** Acquire an API access token silently and redirect only when interaction is required. */
export async function acquireApiAccessToken(
  client: MsalTokenClient,
  config: EntraPortalAuthConfig,
): Promise<string> {
  const account = selectAccount(client);
  const request: SilentRequest = {
    account,
    scopes: [config.apiScope],
  };

  try {
    const result = await client.acquireTokenSilent(request);
    if (!result.accessToken) {
      throw new PortalAuthenticationRequired("O Entra ID não retornou token para a API.");
    }
    return result.accessToken;
  } catch (error) {
    if (!(error instanceof InteractionRequiredAuthError)) {
      throw error;
    }
    interaction ??= client.acquireTokenRedirect(request).finally(() => {
      interaction = null;
    });
    await interaction;
    throw new PortalAuthenticationRequired("Reautenticação iniciada pelo Microsoft Entra ID.");
  }
}

/** Acquire an API token from the configured singleton MSAL client. */
export async function getApiAccessToken(): Promise<string> {
  const config = getPortalAuthConfig();
  if (config.mode !== "entra") {
    throw new Error("Access token não é usado no modo local.");
  }
  return acquireApiAccessToken(
    getMsalApplication() as PublicClientApplication,
    config,
  );
}

function selectAccount(client: MsalTokenClient): AccountInfo {
  const active = client.getActiveAccount();
  if (active) {
    return active;
  }
  const accounts = client.getAllAccounts();
  if (accounts.length === 1) {
    client.setActiveAccount(accounts[0]);
    return accounts[0];
  }
  if (accounts.length > 1) {
    throw new PortalAuthenticationRequired("Selecione uma única conta corporativa.");
  }
  throw new PortalAuthenticationRequired("Entre com sua conta corporativa para continuar.");
}
