"use client";

import { InteractionStatus } from "@azure/msal-browser";
import { MsalProvider, useMsal } from "@azure/msal-react";
import { useEffect, useState, type ReactNode } from "react";

import { getPortalAuthConfig } from "@/lib/auth/config";
import { getMsalApplication } from "@/lib/auth/msal";
import { loginRequest } from "@/lib/auth/session";

/** Provide MSAL context only when the portal build explicitly enables Entra authentication. */
export function PortalAuthProvider({ children }: { children: ReactNode }) {
  const config = getPortalAuthConfig();
  const [instance, setInstance] = useState<ReturnType<typeof getMsalApplication> | null>(null);

  useEffect(() => {
    let active = true;
    if (config.mode !== "entra") {
      return () => {
        active = false;
      };
    }
    void Promise.resolve().then(() => {
      if (active) {
        setInstance(getMsalApplication());
      }
    });
    return () => {
      active = false;
    };
  }, [config.mode]);

  if (config.mode === "local") {
    return children;
  }
  if (!instance) {
    return <AuthMessage title="Preparando login…" detail="Aguarde o Microsoft Entra ID." />;
  }
  return <MsalProvider instance={instance}>{children}</MsalProvider>;
}

/** Block protected portal content until an Entra account is selected. */
export function PortalAuthBoundary({ children }: { children: ReactNode }) {
  const config = getPortalAuthConfig();
  if (config.mode === "local") {
    return children;
  }
  return <EntraAuthBoundary>{children}</EntraAuthBoundary>;
}

/** Display local-mode provenance or the active Entra account and logout action. */
export function PortalAuthStatus() {
  const config = getPortalAuthConfig();
  if (config.mode === "local") {
    return <span className="auth-local">Ambiente local</span>;
  }
  return <EntraAuthStatus />;
}

function EntraAuthBoundary({ children }: { children: ReactNode }) {
  const config = getPortalAuthConfig();
  const { accounts, inProgress, instance } = useMsal();
  const [error, setError] = useState("");
  const activeAccount = instance.getActiveAccount();
  const selectedAccount = activeAccount ?? (accounts.length === 1 ? accounts[0] : null);

  useEffect(() => {
    if (!activeAccount && accounts.length === 1) {
      instance.setActiveAccount(accounts[0]);
    }
  }, [accounts, activeAccount, instance]);

  if (inProgress !== InteractionStatus.None) {
    return <AuthMessage title="Validando sua sessão…" detail="Aguarde o Microsoft Entra ID." />;
  }
  if (selectedAccount) {
    return children;
  }

  async function signIn() {
    if (config.mode !== "entra") return;
    setError("");
    try {
      await instance.loginRedirect(loginRequest(config));
    } catch {
      setError("Não foi possível iniciar o login. Tente novamente ou contate o suporte.");
    }
  }

  return (
    <AuthMessage
      title={accounts.length > 1 ? "Selecione sua conta corporativa" : "Entre para continuar"}
      detail="Sua identidade será validada pelo Microsoft Entra ID antes do acesso ao portfólio."
    >
      {error && <div className="notice notice-error">{error}</div>}
      <button className="button button-primary" onClick={signIn}>
        Entrar com Microsoft
      </button>
    </AuthMessage>
  );
}

function EntraAuthStatus() {
  const config = getPortalAuthConfig();
  const { accounts, inProgress, instance } = useMsal();
  const activeAccount = instance.getActiveAccount();
  const account = activeAccount ?? (accounts.length === 1 ? accounts[0] : null);

  async function signIn() {
    if (config.mode === "entra") {
      await instance.loginRedirect(loginRequest(config));
    }
  }

  async function signOut() {
    await instance.logoutRedirect({
      account: account ?? undefined,
      postLogoutRedirectUri: window.location.origin,
    });
  }

  if (inProgress !== InteractionStatus.None) {
    return <span className="auth-local">Autenticando…</span>;
  }
  if (!account) {
    return (
      <button className="link-button auth-action" onClick={signIn}>
        Entrar
      </button>
    );
  }
  return (
    <div className="auth-account">
      <span title={account.username}>{account.name ?? account.username}</span>
      <button className="link-button auth-action" onClick={signOut}>
        Sair
      </button>
    </div>
  );
}

function AuthMessage({
  title,
  detail,
  children,
}: {
  title: string;
  detail: string;
  children?: ReactNode;
}) {
  return (
    <div className="auth-page page-shell">
      <section className="panel auth-panel">
        <p className="eyebrow">IDENTIDADE CORPORATIVA</p>
        <h1>{title}</h1>
        <p>{detail}</p>
        {children}
      </section>
    </div>
  );
}
