"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { StatusPill } from "@/components/StatusPill";
import { listInitiatives } from "@/lib/api";
import { label } from "@/lib/labels";
import type { Initiative } from "@/lib/types";

export default function Dashboard() {
  const [initiatives, setInitiatives] = useState<Initiative[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    listInitiatives()
      .then(setInitiatives)
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, []);

  const summary = useMemo(
    () => ({
      total: initiatives.length,
      review: initiatives.filter((item) => item.status === "under_review").length,
      high: initiatives.filter((item) => ["high", "critical"].includes(item.risk_tier)).length,
      approved: initiatives.filter((item) => item.status === "approved").length,
    }),
    [initiatives],
  );

  return (
    <div className="page-shell">
      <section className="hero">
        <div>
          <p className="eyebrow">PORTFÓLIO DE IA</p>
          <h1>Decisões de IA claras,<br />da ideia à operação.</h1>
          <p className="hero-copy">
            Registre propostas, entenda o risco e coordene aprovações sem depender de
            planilhas ou linguagem técnica.
          </p>
        </div>
        <Link className="button button-primary" href="/initiatives/new">
          Cadastrar proposta <span aria-hidden>→</span>
        </Link>
      </section>

      <section className="metrics" aria-label="Resumo do portfólio">
        <article><span>Total no portfólio</span><strong>{summary.total}</strong></article>
        <article><span>Em avaliação</span><strong>{summary.review}</strong></article>
        <article><span>Risco elevado</span><strong>{summary.high}</strong></article>
        <article><span>Aprovadas</span><strong>{summary.approved}</strong></article>
      </section>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">INVENTÁRIO</p>
            <h2>Iniciativas recentes</h2>
          </div>
          <Link href="/initiatives/new">Adicionar iniciativa</Link>
        </div>
        {error && <div className="notice notice-error">Não foi possível acessar a API: {error}</div>}
        {loading ? (
          <div className="empty">Carregando portfólio…</div>
        ) : initiatives.length === 0 ? (
          <div className="empty">
            <strong>O portfólio ainda está vazio.</strong>
            <span>Cadastre a primeira proposta para receber uma avaliação preliminar.</span>
          </div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>Iniciativa</th><th>Área</th><th>Risco</th><th>Status</th><th /></tr></thead>
              <tbody>
                {initiatives.map((initiative) => (
                  <tr key={initiative.id}>
                    <td><strong>{initiative.name}</strong><small>Owner: {initiative.business_owner_id}</small></td>
                    <td>{initiative.business_area}</td>
                    <td><StatusPill value={initiative.risk_tier} /></td>
                    <td><StatusPill value={initiative.status} /></td>
                    <td><Link aria-label={`Abrir ${initiative.name}`} href={`/initiatives/${initiative.id}`}>Ver →</Link></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      <p className="context-note">Classificação inicial baseada em impacto, dados, autonomia, exposição e contexto regulatório.</p>
    </div>
  );
}
