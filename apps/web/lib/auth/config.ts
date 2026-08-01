export type PortalAuthMode = "local" | "entra";

export interface PortalAuthEnvironment {
  mode?: string;
  clientId?: string;
  tenantId?: string;
  apiScope?: string;
}

export interface LocalPortalAuthConfig {
  mode: "local";
}

export interface EntraPortalAuthConfig {
  mode: "entra";
  clientId: string;
  tenantId: string;
  apiScope: string;
  authority: string;
}

export type PortalAuthConfig = LocalPortalAuthConfig | EntraPortalAuthConfig;

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const API_SCOPE_PATTERN = /^(api:\/\/|https:\/\/)[^\s]{1,500}$/;

/** Parse public build-time authentication settings and fail closed for invalid Entra values. */
export function parsePortalAuthConfig(environment: PortalAuthEnvironment): PortalAuthConfig {
  const mode = environment.mode?.trim() || "local";
  if (mode === "local") {
    return { mode };
  }
  if (mode !== "entra") {
    throw new Error("NEXT_PUBLIC_AUTH_MODE deve ser local ou entra.");
  }

  const clientId = requiredUuid(environment.clientId, "NEXT_PUBLIC_ENTRA_CLIENT_ID");
  const tenantId = requiredUuid(environment.tenantId, "NEXT_PUBLIC_ENTRA_TENANT_ID");
  const apiScope = environment.apiScope?.trim() ?? "";
  if (!API_SCOPE_PATTERN.test(apiScope)) {
    throw new Error(
      "NEXT_PUBLIC_ENTRA_API_SCOPE deve ser um scope delegado api:// ou https:// válido.",
    );
  }

  return {
    mode,
    clientId,
    tenantId,
    apiScope,
    authority: `https://login.microsoftonline.com/${tenantId}`,
  };
}

/** Return the authentication configuration embedded in the current portal build. */
export function getPortalAuthConfig(): PortalAuthConfig {
  return parsePortalAuthConfig({
    mode: process.env.NEXT_PUBLIC_AUTH_MODE,
    clientId: process.env.NEXT_PUBLIC_ENTRA_CLIENT_ID,
    tenantId: process.env.NEXT_PUBLIC_ENTRA_TENANT_ID,
    apiScope: process.env.NEXT_PUBLIC_ENTRA_API_SCOPE,
  });
}

function requiredUuid(value: string | undefined, name: string): string {
  const normalized = value?.trim() ?? "";
  if (!UUID_PATTERN.test(normalized)) {
    throw new Error(`${name} deve ser um UUID explícito do Microsoft Entra ID.`);
  }
  return normalized.toLowerCase();
}
