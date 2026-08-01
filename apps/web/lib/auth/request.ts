import { getPortalAuthConfig, type PortalAuthConfig } from "@/lib/auth/config";
import { getApiAccessToken } from "@/lib/auth/session";
import type { Identity } from "@/lib/types";

export type AccessTokenProvider = () => Promise<string>;

/** Apply either explicit local identity or Entra bearer authentication, never both. */
export async function applyRequestAuthentication(
  headers: Headers,
  identity: Identity,
  config: PortalAuthConfig = getPortalAuthConfig(),
  tokenProvider: AccessTokenProvider = getApiAccessToken,
): Promise<void> {
  headers.delete("Authorization");
  headers.delete("X-User-Id");
  headers.delete("X-User-Areas");

  if (config.mode === "local") {
    headers.set("X-User-Id", identity.userId);
    headers.set("X-User-Areas", identity.areas?.join(",") ?? "");
    return;
  }

  const accessToken = await tokenProvider();
  headers.set("Authorization", `Bearer ${accessToken}`);
}
