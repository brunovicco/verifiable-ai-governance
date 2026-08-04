"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";

import { PortalAuthStatus } from "@/components/auth/PortalAuth";
import { DemoReadOnlyBanner } from "@/components/layout/DemoReadOnlyBanner";
import { Icon, type IconName } from "@/components/ui/Icon";
import { getDeploymentLabel, getGitSha, isDemoReadOnly } from "@/lib/demo";

interface AppShellProps { children: ReactNode; }
interface NavItem { href: string; label: string; icon: IconName; exact?: boolean; }

const navigation: NavItem[] = [
  { href: "/", label: "Portfólio", icon: "portfolio", exact: true },
  { href: "/dashboard", label: "Monitoramento", icon: "monitoring" },
  { href: "/controles", label: "Controles", icon: "layers" },
  { href: "/documentacao", label: "Documentação", icon: "documentation" },
];

function isCurrent(pathname: string, item: NavItem): boolean {
  return item.exact ? pathname === item.href : pathname.startsWith(item.href);
}

export function AppShell({ children }: AppShellProps) {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    function closeOnEscape(event: KeyboardEvent) { if (event.key === "Escape") setMenuOpen(false); }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, []);

  return (
    <div className="vg-app-shell">
      <button aria-label="Fechar navegação" className={`vg-sidebar-overlay ${menuOpen ? "is-open" : ""}`} onClick={() => setMenuOpen(false)} type="button" />
      <aside className={`vg-sidebar ${menuOpen ? "is-open" : ""}`}>
        <div className="vg-sidebar__brand">
          <span className="vg-brand-mark"><Icon name="shield" size={22} /></span>
          <span><strong>Verifiable AI</strong><small>Governance Platform</small></span>
          <button aria-label="Fechar menu" className="vg-icon-button vg-sidebar__close" onClick={() => setMenuOpen(false)} type="button"><Icon name="close" /></button>
        </div>
        {isDemoReadOnly() ? (
          <span aria-disabled="true" className="vg-sidebar__cta vg-sidebar__cta--disabled" title="Disponível apenas em uma instalação autenticada"><Icon name="plus" size={18} />Nova iniciativa</span>
        ) : (
          <Link className="vg-sidebar__cta" href="/initiatives/new" onClick={() => setMenuOpen(false)}><Icon name="plus" size={18} />Nova iniciativa</Link>
        )}
        <nav aria-label="Navegação principal" className="vg-sidebar__nav">
          <p className="vg-sidebar__section-label">Workspace</p>
          {navigation.map((item) => {
            const current = isCurrent(pathname, item);
            return <Link aria-current={current ? "page" : undefined} className={`vg-nav-item ${current ? "is-current" : ""}`} href={item.href} onClick={() => setMenuOpen(false)} key={item.href}><Icon name={item.icon} size={19} /><span>{item.label}</span></Link>;
          })}
        </nav>
        <div className="vg-sidebar__footer">
          <div className="vg-environment"><span className="vg-environment__dot" />{getDeploymentLabel()}</div>
          <span>v0.1 · Reference platform{getGitSha() ? ` · ${getGitSha()}` : ""}</span>
        </div>
      </aside>
      <div className="vg-workspace">
        <DemoReadOnlyBanner />
        <header className="vg-topbar">
          <div className="vg-topbar__left">
            <button aria-expanded={menuOpen} aria-label="Abrir navegação" className="vg-icon-button vg-menu-button" onClick={() => setMenuOpen(true)} type="button"><Icon name="menu" /></button>
            <div className="vg-topbar__context"><span>AI Governance</span><strong>{navigation.find((item) => isCurrent(pathname, item))?.label ?? "Workspace"}</strong></div>
          </div>
          <div className="vg-topbar__right"><span className="vg-topbar__assurance"><Icon name="shield" size={16} />Fail-closed controls</span><PortalAuthStatus /></div>
        </header>
        <main className="vg-main">{children}</main>
        <footer className="vg-footer"><span>Políticas verificáveis · Evidências · Decisões auditáveis</span><span>Verifiable AI Governance</span></footer>
      </div>
    </div>
  );
}
