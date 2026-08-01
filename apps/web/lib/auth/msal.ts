import {
  BrowserCacheLocation,
  EventType,
  PublicClientApplication,
  type AuthenticationResult,
  type Configuration,
} from "@azure/msal-browser";

import { getPortalAuthConfig, type EntraPortalAuthConfig } from "@/lib/auth/config";

let application: PublicClientApplication | null = null;

/** Build the tenant-specific MSAL configuration without accepting secrets or arbitrary authorities. */
export function buildMsalConfiguration(
  config: EntraPortalAuthConfig,
  origin: string,
): Configuration {
  return {
    auth: {
      clientId: config.clientId,
      authority: config.authority,
      redirectUri: origin,
      postLogoutRedirectUri: origin,
    },
    cache: {
      cacheLocation: BrowserCacheLocation.SessionStorage,
    },
    system: {
      allowPlatformBroker: false,
      loggerOptions: {
        piiLoggingEnabled: false,
        loggerCallback: () => undefined,
      },
    },
  };
}

/** Return the process-wide browser MSAL public-client instance. */
export function getMsalApplication(): PublicClientApplication {
  if (typeof window === "undefined") {
    throw new Error("MSAL só pode ser inicializado no navegador.");
  }
  const config = getPortalAuthConfig();
  if (config.mode !== "entra") {
    throw new Error("MSAL não está disponível no modo de autenticação local.");
  }
  if (application) {
    return application;
  }

  application = new PublicClientApplication(buildMsalConfiguration(config, window.location.origin));
  application.addEventCallback((message) => {
    if (message.eventType !== EventType.LOGIN_SUCCESS || !message.payload) {
      return;
    }
    const result = message.payload as AuthenticationResult;
    if (result.account) {
      application?.setActiveAccount(result.account);
    }
  });
  return application;
}
