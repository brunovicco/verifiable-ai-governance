"use client";

import { useEffect, useMemo, useState } from "react";
import { Icon } from "@/components/ui/Icon";
import { KpiCard } from "@/components/ui/KpiCard";
import { PageHeader } from "@/components/ui/PageHeader";
import { getDashboard } from "@/lib/api";
import { label } from "@/lib/labels";
import type { Dashboard } from "@/lib/types";

const RISK_TIERS = ["low", "medium", "high", "critical"] as const;
const REVIEW_STATES = ["current", "expired", "not_reviewed"] as const;

function formatDateTime(value: string): string { return new Intl.DateTimeFormat("pt-BR", { dateStyle: "short", timeStyle: "short" }).format(new Date(value)); }
function formatHours(value: number | null): string { if (value === null) return "Sem dados"; if (value >= 24) return `${(value / 24).toFixed(1)} dias`; return `${value.toFixed(1)} horas`; }
function percentage(numerator: number, denominator: number): number { if (denominator <= 0) return 0; return Math.min(100, Math.max(0, (numerator / denominator) * 100)); }

export default function OperationalMonitoringPage() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getDashboard().then(setDashboard).catch((reason: Error) => setError(reason.message)); }, []);

  const activeIncidents = useMemo(() => dashboard ? dashboard.incidents.open + dashboard.incidents.contained + dashboard.incidents.remediating : 0, [dashboard]);
  const expiredReviews = useMemo(() => dashboard ? RISK_TIERS.reduce((total, tier) => total + (dashboard.review_status_by_risk_tier[tier]?.expired ?? 0), 0) : 0, [dashboard]);

  if (error && !dashboard) return <div className="vg-page"><div className="vg-notice vg-notice--error">{error}</div></div>;
  if (!dashboard) return <div className="vg-page"><div className="vg-empty-state">Carregando monitoramento…</div></div>;

  const riskMax = Math.max(1, ...RISK_TIERS.map((tier) => dashboard.residual_risk_by_tier[tier] ?? 0));
  const coverage = percentage(dashboard.assessment_coverage.submitted, dashboard.assessment_coverage.required);

  return (
    <div className="vg-page">
      <PageHeader eyebrow="Monitoramento operacional" title="Risco, bloqueios e assurance do portfólio" description={<p>Atualizado em {formatDateTime(dashboard.generated_at)}. Indicadores refletem fatos registrados pela plataforma, sem inferir metas não declaradas.</p>} />

      <section aria-label="Indicadores principais" className="vg-kpi-grid">
        <KpiCard helper="Abertos, contidos ou em remediação" icon="alert" label="Incidentes ativos" tone={activeIncidents > 0 ? "danger" : "success"} value={activeIncidents} />
        <KpiCard helper="Planos com prazo ultrapassado" icon="clock" label="Remediações vencidas" tone={dashboard.incidents.overdue_remediation > 0 ? "danger" : "neutral"} value={dashboard.incidents.overdue_remediation} />
        <KpiCard helper={`${dashboard.routing_outcomes.cost_limit_exceeded} por limite de custo`} icon="shield" label="Ações bloqueadas" tone="warning" value={dashboard.routing_outcomes.blocked} />
        <KpiCard helper="Revisões fora da validade" icon="clock" label="Revisões vencidas" tone={expiredReviews > 0 ? "warning" : "success"} value={expiredReviews} />
        <KpiCard helper={`${coverage.toFixed(0)}% dos assessments requeridos`} icon="check" label="Cobertura" tone="info" value={`${dashboard.assessment_coverage.submitted}/${dashboard.assessment_coverage.required}`} />
      </section>

      <section className="vg-dashboard-grid">
        <article className="vg-card vg-dashboard-span-8"><div className="vg-card__header"><div><h2>Risco residual</h2><p>Distribuição dos assessments submetidos por tier.</p></div></div><div className="vg-dashboard-card__body"><div className="vg-risk-bars">{RISK_TIERS.map((tier) => { const count = dashboard.residual_risk_by_tier[tier] ?? 0; return <div className="vg-risk-bar" key={tier}><div className="vg-risk-bar__header"><span>{label(tier)}</span><strong>{count}</strong></div><div className="vg-risk-bar__track"><span className="vg-risk-bar__fill" data-tier={tier} style={{ width: `${percentage(count, riskMax)}%` }} /></div></div>; })}</div></div></article>

        <article className="vg-card vg-dashboard-span-4"><div className="vg-card__header"><div><h2>Ações necessárias</h2><p>Sinais que exigem acompanhamento operacional.</p></div></div><div className="vg-dashboard-card__body"><div className="vg-attention-list"><div className="vg-attention-item"><div><span>Incidentes ativos</span><strong>Resposta e contenção</strong></div><span className="vg-attention-item__value">{activeIncidents}</span></div><div className="vg-attention-item"><div><span>Revisões vencidas</span><strong>Renovar assurance</strong></div><span className="vg-attention-item__value">{expiredReviews}</span></div><div className="vg-attention-item"><div><span>Remediações vencidas</span><strong>Escalar owner</strong></div><span className="vg-attention-item__value">{dashboard.incidents.overdue_remediation}</span></div></div></div></article>

        <article className="vg-card vg-dashboard-span-6"><div className="vg-card__header"><div><h2>Cobertura de assessments</h2><p>Documentos estruturados submetidos versus requeridos.</p></div></div><div className="vg-dashboard-card__body"><div className="vg-progress-block"><div className="vg-progress-block__summary"><strong>{coverage.toFixed(0)}%</strong><span>{dashboard.assessment_coverage.submitted} de {dashboard.assessment_coverage.required}</span></div><div className="vg-progress-track"><span style={{ width: `${coverage}%` }} /></div></div></div></article>

        <article className="vg-card vg-dashboard-span-6"><div className="vg-card__header"><div><h2>Tempo médio de ciclo</h2><p>Tempo observado, sem meta ou SLA inferido.</p></div></div><div className="vg-dashboard-card__body"><div className="vg-cycle-grid"><div className="vg-cycle-item"><span>Rodada de revisão</span><strong>{formatHours(dashboard.cycle_times.review_round_avg_hours)}</strong><small>{dashboard.cycle_times.review_round_samples} amostras</small></div><div className="vg-cycle-item"><span>Remediação de incidente</span><strong>{formatHours(dashboard.cycle_times.incident_remediation_avg_hours)}</strong><small>{dashboard.cycle_times.incident_remediation_samples} amostras</small></div></div></div></article>

        <article className="vg-card vg-dashboard-span-7"><div className="vg-card__header"><div><h2>Vigência de revisões</h2><p>Modelos e agentes por tier de risco e estado de revisão.</p></div></div><div className="vg-table-wrap"><table className="vg-table"><thead><tr><th>Risco</th>{REVIEW_STATES.map((state) => <th key={state}>{label(state)}</th>)}</tr></thead><tbody>{RISK_TIERS.map((tier) => <tr key={tier}><td><strong>{label(tier)}</strong></td>{REVIEW_STATES.map((state) => <td key={state}>{dashboard.review_status_by_risk_tier[tier]?.[state] ?? 0}</td>)}</tr>)}</tbody></table></div></article>

        <article className="vg-card vg-dashboard-span-5"><div className="vg-card__header"><div><h2>Decisões de roteamento</h2><p>Resultados produzidos pelo enforcement em runtime.</p></div></div><div className="vg-table-wrap"><table className="vg-table"><tbody><tr><td>{label("allowed")}</td><td>{dashboard.routing_outcomes.allowed}</td></tr><tr><td>{label("blocked")}</td><td>{dashboard.routing_outcomes.blocked}</td></tr><tr><td>{label("dependency_unavailable")}</td><td>{dashboard.routing_outcomes.dependency_unavailable}</td></tr><tr><td>Limite de custo</td><td>{dashboard.routing_outcomes.cost_limit_exceeded}</td></tr></tbody></table></div></article>

        <article className="vg-card vg-dashboard-span-6"><div className="vg-card__header"><div><h2>Incidentes por status</h2><p>Posição atual dos registros de resposta.</p></div></div><div className="vg-table-wrap"><table className="vg-table"><tbody><tr><td>{label("open")}</td><td>{dashboard.incidents.open}</td></tr><tr><td>{label("contained")}</td><td>{dashboard.incidents.contained}</td></tr><tr><td>{label("remediating")}</td><td>{dashboard.incidents.remediating}</td></tr><tr><td>{label("closed")}</td><td>{dashboard.incidents.closed}</td></tr></tbody></table></div></article>

        <article className="vg-card vg-dashboard-span-6"><div className="vg-card__header"><div><h2>Exceções temporárias</h2><p>Distribuição por estado de vigência.</p></div></div><div className="vg-table-wrap"><table className="vg-table"><tbody>{Object.entries(dashboard.exceptions_by_state).map(([state, count]) => <tr key={state}><td>{label(state)}</td><td>{count}</td></tr>)}</tbody></table></div></article>

        <article className="vg-card vg-dashboard-span-6"><div className="vg-card__header"><div><h2>Drift de modelos e agentes</h2><p>Model evaluation</p></div></div><div className="vg-dashboard-card__body vg-unavailable"><Icon name="alert" size={20} /><div><strong>Métrica ainda indisponível</strong><p>Depende da integração futura com avaliações e regressões do ragforge.</p></div></div></article>
        <article className="vg-card vg-dashboard-span-6"><div className="vg-card__header"><div><h2>Efetividade de controles</h2><p>Control assurance</p></div></div><div className="vg-dashboard-card__body vg-unavailable"><Icon name="alert" size={20} /><div><strong>Métrica ainda indisponível</strong><p>O catálogo registra aplicabilidade, mas ainda não comprova efetividade operacional.</p></div></div></article>
      </section>
    </div>
  );
}
