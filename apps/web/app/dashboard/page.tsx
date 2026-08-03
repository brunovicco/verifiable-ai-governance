"use client";

import { useEffect, useMemo, useState } from "react";

import { getDashboard } from "@/lib/api";
import { label } from "@/lib/labels";
import type { Dashboard } from "@/lib/types";

const RISK_TIERS = ["low", "medium", "high", "critical"];
const REVIEW_STATES = ["current", "expired", "not_reviewed"];

function formatDateTime(value: string): string {
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

export default function OperationalMonitoringPage() {
  const [dashboard, setDashboard] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getDashboard().then(setDashboard).catch((reason: Error) => setError(reason.message));
  }, []);

  const activeIncidents = useMemo(() => {
    if (!dashboard) return 0;
    const { open, contained, remediating } = dashboard.incidents;
    return open + contained + remediating;
  }, [dashboard]);

  const expiredReviews = useMemo(() => {
    if (!dashboard) return 0;
    return RISK_TIERS.reduce(
      (total, tier) => total + (dashboard.review_status_by_risk_tier[tier]?.expired ?? 0),
      0,
    );
  }, [dashboard]);

  if (error && !dashboard) {
    return <div className="page-shell"><div className="notice notice-error">{error}</div></div>;
  }
  if (!dashboard) {
    return <div className="page-shell"><div className="empty">Carregando monitoramento…</div></div>;
  }

  return (
    <div className="page-shell detail-page">
      <section className="detail-header">
        <div>
          <p className="eyebrow">MONITORAMENTO OPERACIONAL</p>
          <h1>Violações, bloqueios e vigência em todo o portfólio</h1>
          <p>Atualizado em {formatDateTime(dashboard.generated_at)}.</p>
        </div>
      </section>

      <section className="asset-summary">
        <article className="panel"><span>Incidentes ativos</span><strong>{activeIncidents}</strong></article>
        <article className="panel"><span>Remediações vencidas</span><strong>{dashboard.incidents.overdue_remediation}</strong></article>
        <article className="panel"><span>Ações bloqueadas</span><strong>{dashboard.routing_outcomes.blocked}</strong></article>
        <article className="panel"><span>Revisões vencidas</span><strong>{expiredReviews}</strong></article>
      </section>

      <section className="asset-columns">
        <article className="panel asset-panel">
          <div className="panel-heading"><div><p className="eyebrow">MODEL ROUTING</p><h2>Decisões de roteamento</h2></div></div>
          <table>
            <tbody>
              <tr><td>{label("allowed")}</td><td>{dashboard.routing_outcomes.allowed}</td></tr>
              <tr><td>{label("blocked")}</td><td>{dashboard.routing_outcomes.blocked}</td></tr>
              <tr><td>{label("dependency_unavailable")}</td><td>{dashboard.routing_outcomes.dependency_unavailable}</td></tr>
              <tr><td>Bloqueios por limite de custo</td><td>{dashboard.routing_outcomes.cost_limit_exceeded}</td></tr>
            </tbody>
          </table>
          {dashboard.routing_outcomes.top_blocked_reason_codes.length > 0 && (
            <>
              <p className="field-label">Principais motivos de bloqueio</p>
              <table>
                <tbody>
                  {dashboard.routing_outcomes.top_blocked_reason_codes.map(([reason, count]) => (
                    <tr key={reason}><td>{label(reason)}</td><td>{count}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </article>

        <article className="panel asset-panel">
          <div className="panel-heading"><div><p className="eyebrow">ASSET REGISTRY</p><h2>Vigência de revisões</h2></div></div>
          <table>
            <thead>
              <tr><th>Risco</th>{REVIEW_STATES.map((state) => <th key={state}>{label(state)}</th>)}</tr>
            </thead>
            <tbody>
              {RISK_TIERS.map((tier) => (
                <tr key={tier}>
                  <td>{label(tier)}</td>
                  {REVIEW_STATES.map((state) => (
                    <td key={state}>{dashboard.review_status_by_risk_tier[tier]?.[state] ?? 0}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </article>
      </section>

      <section className="asset-columns">
        <article className="panel asset-panel">
          <div className="panel-heading"><div><p className="eyebrow">INCIDENT RESPONSE</p><h2>Incidentes por status</h2></div></div>
          <table>
            <tbody>
              <tr><td>{label("open")}</td><td>{dashboard.incidents.open}</td></tr>
              <tr><td>{label("contained")}</td><td>{dashboard.incidents.contained}</td></tr>
              <tr><td>{label("remediating")}</td><td>{dashboard.incidents.remediating}</td></tr>
              <tr><td>{label("closed")}</td><td>{dashboard.incidents.closed}</td></tr>
            </tbody>
          </table>
        </article>

        <article className="panel asset-panel">
          <div className="panel-heading"><div><p className="eyebrow">TEMPORARY EXCEPTIONS</p><h2>Exceções por vigência</h2></div></div>
          <table>
            <tbody>
              {Object.entries(dashboard.exceptions_by_state).map(([state, count]) => (
                <tr key={state}><td>{label(state)}</td><td>{count}</td></tr>
              ))}
            </tbody>
          </table>
        </article>
      </section>

      <section className="panel asset-panel">
        <div className="panel-heading"><div><p className="eyebrow">MODEL EVALUATION</p><h2>Drift de modelos e agentes</h2></div></div>
        <div className="notice">
          Métrica ainda não disponível nesta plataforma. Depende da futura integração com
          avaliações e regressões (ragforge), item separado do backlog.
        </div>
      </section>
    </div>
  );
}
