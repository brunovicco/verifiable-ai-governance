"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { StatusPill } from "@/components/StatusPill";
import { createAISystem, decideApproval, getInitiative, submitInitiative } from "@/lib/api";
import { label } from "@/lib/labels";
import type { AISystem, Approval, Initiative } from "@/lib/types";

function ApprovalCard({ approval, initiativeId, onUpdated }: { approval: Approval; initiativeId: string; onUpdated: (value: Initiative) => void }) {
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const updated = await decideApproval(initiativeId, approval.id, {
        decision: data.get("decision") as "approved" | "rejected",
        comments: String(data.get("comments")),
        evidence_uri: String(data.get("evidence_uri")),
        expected_version: approval.version,
      }, { userId: String(data.get("reviewer")), areas: [approval.area] });
      onUpdated(updated); setOpen(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao registrar decisão."); }
    finally { setBusy(false); }
  }

  return <article className={`approval-card ${approval.required ? "" : "muted"}`}>
    <div className="approval-top"><span className="area-icon">{label(approval.area).slice(0, 2).toUpperCase()}</span><div><strong>{label(approval.area)}</strong><small>{approval.required ? "Aprovação obrigatória" : "Sem gate nesta proposta"}</small></div><StatusPill value={approval.status} /></div>
    <p>{approval.reason}</p>
    {approval.decided_by && <small>Decidido por {approval.decided_by}: {approval.comments}</small>}
    {approval.status === "pending" && <button className="link-button" onClick={() => setOpen(!open)}>{open ? "Fechar" : "Registrar decisão"}</button>}
    {open && <form className="decision-form" onSubmit={decide}>
      <label>Identificação do revisor<input name="reviewer" required minLength={3} placeholder={`revisor.${approval.area}`} /></label>
      <label>Decisão<select name="decision"><option value="approved">Aprovar</option><option value="rejected">Rejeitar</option></select></label>
      <label>Justificativa<textarea name="comments" required minLength={5} rows={2} /></label>
      <label>Referência da evidência<input name="evidence_uri" required placeholder="URL, ticket ou URN" /></label>
      {error && <div className="notice notice-error">{error}</div>}
      <button className="button button-primary button-small" disabled={busy}>{busy ? "Registrando…" : "Confirmar decisão"}</button>
    </form>}
  </article>;
}

function SystemInventory({
  initiative,
  onCreated,
}: {
  initiative: Initiative;
  onCreated: (system: AISystem) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const systems = initiative.systems ?? [];

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const system = await createAISystem(initiative.id, {
        name: String(data.get("name")),
        purpose: String(data.get("purpose")),
        owner_id: String(data.get("owner_id")),
        production: data.get("production") === "on",
      });
      onCreated(system);
      form.reset();
      setOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao cadastrar o sistema.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel inventory-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">INVENTÁRIO OPERACIONAL</p>
          <h2>Sistemas de IA</h2>
        </div>
        {initiative.status === "approved" && (
          <button className="button button-small" onClick={() => setOpen(!open)}>
            {open ? "Cancelar" : "Cadastrar sistema"}
          </button>
        )}
      </div>
      {open && (
        <form className="inventory-form" onSubmit={create}>
          <div className="field-grid">
            <label>
              Nome do sistema
              <input name="name" required minLength={3} />
            </label>
            <label>
              Responsável
              <input name="owner_id" required defaultValue={initiative.business_owner_id} />
            </label>
          </div>
          <label>
            Finalidade operacional
            <textarea name="purpose" required minLength={20} rows={3} />
          </label>
          <label className="check inline-check">
            <input name="production" type="checkbox" />
            <span>Este sistema já está em produção</span>
          </label>
          {error && <div className="notice notice-error">{error}</div>}
          <button className="button button-primary" disabled={busy}>
            {busy ? "Cadastrando…" : "Adicionar ao inventário"}
          </button>
        </form>
      )}
      {systems.length === 0 ? (
        <div className="empty compact-empty">
          <strong>Nenhum sistema vinculado.</strong>
          <span>O cadastro é liberado depois da aprovação da iniciativa.</span>
        </div>
      ) : (
        <div className="inventory-list">
          {systems.map((system) => (
            <Link className="inventory-row" href={`/systems/${system.id}`} key={system.id}>
              <div>
                <strong>{system.name}</strong>
                <small>{system.purpose}</small>
              </div>
              <div className="status-row">
                <StatusPill value={system.status} />
                <span aria-hidden>→</span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

export default function InitiativePage() {
  const { id } = useParams<{ id: string }>();
  const [initiative, setInitiative] = useState<Initiative | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { getInitiative(id).then(setInitiative).catch((reason: Error) => setError(reason.message)); }, [id]);

  async function submit() {
    if (!initiative) return; setBusy(true); setError("");
    try { setInitiative(await submitInitiative(initiative.id, initiative.version)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Falha na submissão."); }
    finally { setBusy(false); }
  }

  if (error && !initiative) return <div className="page-shell"><div className="notice notice-error">{error}</div></div>;
  if (!initiative) return <div className="page-shell"><div className="empty">Carregando iniciativa…</div></div>;
  const required = initiative.approvals?.filter((item) => item.required) ?? [];
  const approved = required.filter((item) => item.status === "approved").length;

  function addSystem(system: AISystem) {
    setInitiative((current) =>
      current ? { ...current, systems: [...(current.systems ?? []), system] } : current,
    );
  }

  return <div className="page-shell detail-page">
    <div className="breadcrumb"><Link href="/">Portfólio</Link><span>/</span><span>{initiative.name}</span></div>
    <section className="detail-header">
      <div><div className="status-row"><StatusPill value={initiative.status} /><StatusPill value={initiative.risk_tier} /></div><h1>{initiative.name}</h1><p>{initiative.description}</p></div>
      {initiative.status === "draft" && <button className="button button-primary" disabled={busy} onClick={submit}>{busy ? "Enviando…" : "Enviar para aprovação"}</button>}
    </section>
    {error && <div className="notice notice-error">{error}</div>}
    <section className="detail-grid">
      <article className="panel summary-card"><p className="eyebrow">AVALIAÇÃO PRELIMINAR</p><div className="score"><strong>{initiative.risk_score}</strong><span>/ 100</span></div><StatusPill value={initiative.risk_tier} /><dl><div><dt>Área</dt><dd>{initiative.business_area}</dd></div><div><dt>Owner</dt><dd>{initiative.business_owner_id}</dd></div><div><dt>Política</dt><dd>{initiative.policy_id} v{initiative.policy_version}</dd></div><div><dt>Versão do registro</dt><dd>{initiative.version}</dd></div></dl></article>
      <article className="panel documents-card"><p className="eyebrow">DOCUMENTAÇÃO REQUERIDA</p><h2>{initiative.required_documents.length} artefatos</h2><ul className="document-list">{initiative.required_documents.map((document) => <li key={document}><span>✓</span>{label(document)}</li>)}</ul></article>
    </section>
    {initiative.status !== "draft" && <section className="panel approvals-panel"><div className="panel-heading"><div><p className="eyebrow">FLUXO DE APROVAÇÃO</p><h2>{approved} de {required.length} gates concluídos</h2></div><div className="progress"><span style={{ width: `${required.length ? (approved / required.length) * 100 : 0}%` }} /></div></div><div className="approval-grid">{initiative.approvals?.map((approval) => <ApprovalCard approval={approval} initiativeId={initiative.id} key={approval.id} onUpdated={setInitiative} />)}</div></section>}
    {(initiative.status === "approved" || (initiative.systems?.length ?? 0) > 0) && (
      <SystemInventory initiative={initiative} onCreated={addSystem} />
    )}
  </div>;
}
