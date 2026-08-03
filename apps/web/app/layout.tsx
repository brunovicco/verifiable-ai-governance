import type { Metadata } from "next";
import { PortalAuthBoundary, PortalAuthProvider } from "@/components/auth/PortalAuth";
import { AppShell } from "@/components/layout/AppShell";
import "./globals.css";
import "./design-system.css";
import "./app-shell.css";
import "./portfolio-v2.css";
import "./dashboard-v2.css";

export const metadata: Metadata = {
  title: { default: "Verifiable AI Governance", template: "%s · Verifiable AI Governance" },
  description: "Plataforma de governança verificável para iniciativas, modelos e agentes de IA.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="pt-BR"><body><PortalAuthProvider><AppShell><PortalAuthBoundary>{children}</PortalAuthBoundary></AppShell></PortalAuthProvider></body></html>;
}
