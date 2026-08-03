import type { Metadata } from "next";
import Link from "next/link";

import {
  PortalAuthBoundary,
  PortalAuthProvider,
  PortalAuthStatus,
} from "@/components/auth/PortalAuth";

import "./globals.css";

export const metadata: Metadata = {
  title: "Verifiable AI Governance",
  description: "Governança de IA do cadastro ao monitoramento",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="pt-BR">
      <body>
        <PortalAuthProvider>
          <header className="topbar">
            <Link className="brand" href="/">
              <span className="brand-mark">V</span>
              <span>
                <strong>Verifiable AI</strong>
                <small>Governance workspace</small>
              </span>
            </Link>
            <nav aria-label="Navegação principal">
              <Link href="/">Portfólio</Link>
              <Link href="/dashboard">Monitoramento</Link>
              <Link href="/controles">Controles</Link>
              <Link href="/documentacao">Documentação</Link>
              <Link className="button button-small" href="/initiatives/new">
                Nova iniciativa
              </Link>
              <PortalAuthStatus />
            </nav>
          </header>
          <PortalAuthBoundary>
            <main>{children}</main>
          </PortalAuthBoundary>
          <footer>
            <span>Políticas verificáveis · Evidências · Decisões auditáveis</span>
            <span>v0.1</span>
          </footer>
        </PortalAuthProvider>
      </body>
    </html>
  );
}
