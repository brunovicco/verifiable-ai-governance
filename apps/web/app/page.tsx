"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { StatusPill } from "@/components/StatusPill";
import { Icon } from "@/components/ui/Icon";
import { KpiCard } from "@/components/ui/KpiCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { listInitiatives } from "@/lib/api";
import { isDemoReadOnly } from "@/lib/demo";
import type { Initiative } from "@/lib/types";

const ALL = "all";

export default function PortfolioPage() {
  const [initiatives, setInitiatives] = useState<Initiative[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState(ALL);
  const [riskFilter, setRiskFilter] = useState(ALL);

  useEffect(() => {
    listInitiatives().then(setInitiatives).catch((reason: Error) => setError(reason.message)).finally(() => setLoading(false));
  }, []);

  const summary = useMemo(() => ({
    total: initiatives.length,
    review: initiatives.filter((item) => item.status === "under_review").length,
    high: initiatives.filter((item) => ["high", "critical"].includes(item.risk_tier)).length,
    approved: initiatives.filter((item) => item.status === "approved").length,
  }), [initiatives]);

  const filteredInitiatives = useMemo(() => {
    const normalizedSearch = search.trim().toLocaleLowerCase("pt-BR");
    return initiatives.filter((initiative) => {
      const matchesSearch = !normalizedSearch || initiative.name.toLocaleLowerCase("pt-BR").includes(normalizedSearch) || initiative.business_area.toLocaleLowerCase("pt-BR").includes(normalizedSearch) || initiative.business_owner_id.toLocaleLowerCase("pt-BR").includes(normalizedSearch);
      return matchesSearch && (statusFilter === ALL || initiative.status === statusFilter) && (riskFilter === ALL || initiative.risk_tier === riskFilter);
    });
  }, [initiatives, riskFilter, search, statusFilter]);

  return (
    <div className="vg-page">
      <PageHeader eyebrow="Portfólio de IA" title="Visão consolidada das iniciativas" description={<p>Gerencie propostas, acompanhe risco, aprovações e operação em um inventário verificável.</p>} actions={isDemoReadOnly() ? undefined : <Link className="vg-button vg-button--primary" href="/initiatives/new"><Icon name="plus" size={17} />Nova iniciativa</Link>} />

      <section aria-label="Resumo do portfólio" className="vg-kpi-grid">
        <KpiCard helper="Todas as iniciativas registradas" icon="portfolio" label="Total" value={summary.total} />
        <KpiCard helper="Aguardando decisões obrigatórias" icon="clock" label="Em revisão" tone="info" value={summary.review} />
        <KpiCard helper="Tiers alto ou crítico" icon="alert" label="Risco elevado" tone="warning" value={summary.high} />
        <KpiCard helper="Gates obrigatórios concluídos" icon="check" label="Aprovadas" tone="success" value={summary.approved} />
      </section>

      <section aria-label="Filtros do portfólio" className="vg-portfolio-toolbar">
        <label className="vg-search-field"><span className="sr-only">Buscar iniciativas</span><Icon name="search" size={17} /><input onChange={(event) => setSearch(event.target.value)} placeholder="Buscar por iniciativa, área ou owner" type="search" value={search} /></label>
        <label><span className="sr-only">Filtrar por status</span><select className="vg-filter-select" onChange={(event) => setStatusFilter(event.target.value)} value={statusFilter}><option value={ALL}>Todos os status</option><option value="draft">Rascunho</option><option value="under_review">Em revisão</option><option value="changes_requested">Ajustes solicitados</option><option value="approved">Aprovada</option><option value="rejected">Rejeitada</option><option value="active">Ativa</option><option value="retired">Aposentada</option></select></label>
        <label><span className="sr-only">Filtrar por risco</span><select className="vg-filter-select" onChange={(event) => setRiskFilter(event.target.value)} value={riskFilter}><option value={ALL}>Todos os riscos</option><option value="low">Baixo</option><option value="medium">Médio</option><option value="high">Alto</option><option value="critical">Crítico</option></select></label>
      </section>

      <section className="vg-card vg-portfolio-table">
        <div className="vg-card__header"><div><h2>Inventário de iniciativas</h2><p>{filteredInitiatives.length} de {initiatives.length} registros exibidos</p></div></div>
        {error && <div className="vg-notice vg-notice--error">Não foi possível acessar a API: {error}</div>}
        {loading ? <div className="vg-empty-state">Carregando portfólio…</div> : filteredInitiatives.length === 0 ? <div className="vg-empty-state"><div><strong>Nenhuma iniciativa encontrada.</strong><span>Ajuste os filtros ou cadastre uma nova proposta.</span></div></div> : (
          <div className="vg-table-wrap"><table className="vg-table"><thead><tr><th>Iniciativa</th><th>Área</th><th>Risco</th><th>Status</th><th>Ação</th></tr></thead><tbody>{filteredInitiatives.map((initiative) => <tr key={initiative.id}><td><Link className="vg-table__primary" href={`/initiatives/${initiative.id}`}>{initiative.name}</Link><span className="vg-table__secondary">Owner: {initiative.business_owner_id}</span></td><td>{initiative.business_area}</td><td><StatusPill value={initiative.risk_tier} /></td><td><StatusPill value={initiative.status} /></td><td><Link className="vg-table-link" href={`/initiatives/${initiative.id}`}>Abrir <Icon name="arrow-right" size={14} /></Link></td></tr>)}</tbody></table></div>
        )}
      </section>
      <p className="vg-portfolio-context">Classificação preliminar baseada em impacto, dados, autonomia, exposição e contexto regulatório.</p>
    </div>
  );
}
