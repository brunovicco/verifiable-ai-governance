"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";

import { StatusPill } from "@/components/StatusPill";
import {
  createAISystem,
  decideApproval,
  getInitiative,
  getInitiativeControls,
  listAssessments,
  listEvidence,
  listReviewHistory,
  resubmitInitiative,
  saveInitiativeRevision,
  submitInitiative,
  uploadEvidence,
} from "@/lib/api";
import { label } from "@/lib/labels";
import { getPortalAuthConfig } from "@/lib/auth/config";
import type {
  AISystem,
  Approval,
  Assessment,
  AssessmentKind,
  ControlEvaluation,
  Evidence,
  EvidenceKind,
  Initiative,
  InitiativeControlReport,
  ReviewSubmission,
} from "@/lib/types";

const EVIDENCE_KINDS: Array<{ value: EvidenceKind; label: string }> = [
  { value: "assessment", label: "Assessment" },
  { value: "architecture", label: "Arquitetura" },
  { value: "security_test", label: "Teste de segurança" },
  { value: "policy", label: "Política" },
  { value: "approval", label: "Aprovação" },
  { value: "other", label: "Outro" },
];

const ASSESSMENT_KINDS: AssessmentKind[] = [
  "ai-impact-assessment",
  "ripd",
  "international-processing-assessment",
];

function isAssessmentKind(value: string): value is AssessmentKind {
  return ASSESSMENT_KINDS.some((kind) => kind === value);
}

function AssessmentWorkspace({
  assessments,
  initiative,
}: {
  assessments: Assessment[];
  initiative: Initiative;
}) {
  const required = initiative.required_documents.filter(isAssessmentKind);

  return (
    <section className="panel assessments-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">AVALIAÇÕES E EVIDÊNCIAS</p>
          <h2>Assessments estruturados</h2>
        </div>
        <small>Rascunhos versionados e enviados para revisão independente</small>
      </div>
      <div className="assessment-grid">
        {required.map((kind) => {
          const assessment = assessments.find((item) => item.assessment_type === kind);
          return (
            <Link className="assessment-card" href={`/initiatives/${initiative.id}/assessments/${kind}`} key={kind}>
              <div>
                <strong>{label(kind)}</strong>
                <small>{assessment ? `Schema ${assessment.schema_version} · versão ${assessment.version}` : "Formulário guiado pendente"}</small>
              </div>
              <div className="assessment-card-status">
                {assessment && <StatusPill value={assessment.risk_tier} />}
                <StatusPill value={assessment?.status ?? "not_started"} />
                <span aria-hidden>→</span>
              </div>
            </Link>
          );
        })}
      </div>
    </section>
  );
}

function ControlWorkspace({ report }: { report: InitiativeControlReport }) {
  const [showAll, setShowAll] = useState(false);
  const applicable = report.controls.filter((item) => item.applicable);
  const visible = showAll ? report.controls : applicable;
  const domainTotals = report.controls.reduce<Record<string, number>>((result, item) => {
    result[item.control.domain] = (result[item.control.domain] ?? 0) + 1;
    return result;
  }, {});
  const grouped = visible.reduce<Record<string, ControlEvaluation[]>>((result, item) => {
    (result[item.control.domain] ??= []).push(item);
    return result;
  }, {});

  return (
    <section className="panel controls-panel">
      <div className="panel-heading control-heading">
        <div>
          <p className="eyebrow">CATÁLOGO DE CONTROLES · V{report.catalog_version}</p>
          <h2>{applicable.length} de {report.controls.length} controles aplicáveis</h2>
        </div>
        <button className="button button-small" onClick={() => setShowAll(!showAll)}>
          {showAll ? "Mostrar somente aplicáveis" : "Ver catálogo completo"}
        </button>
      </div>
      <div className="control-groups">
        {Object.entries(grouped).map(([domain, controls]) => (
          <section className="control-group" key={domain}>
            <div className="control-domain-heading">
              <strong>{label(domain)}</strong>
              <span>{controls.filter((item) => item.applicable).length}/{domainTotals[domain]}</span>
            </div>
            <div className="control-list">
              {controls.map((item) => (
                <details className={`control-card ${item.applicable ? "is-applicable" : "is-not-applicable"}`} key={item.control.control_id}>
                  <summary>
                    <div>
                      <small>{item.control.control_id} · {label(item.control.control_type)}</small>
                      <strong>{item.control.title}</strong>
                      <span>{item.reasons[0]}</span>
                    </div>
                    <StatusPill value={item.applicable ? "applicable" : "not_applicable"} />
                  </summary>
                  <div className="control-details">
                    <p>{item.control.objective}</p>
                    <dl>
                      <div><dt>Responsável</dt><dd>{item.control.owner}</dd></div>
                      <div><dt>Revisão</dt><dd>{item.control.review_frequency}</dd></div>
                    </dl>
                    <strong>Requisitos</strong>
                    <ul>{item.control.requirements.map((value) => <li key={value}>{value}</li>)}</ul>
                    <strong>Evidências esperadas</strong>
                    <ul>{item.control.evidence.map((value) => <li key={value}>{value}</li>)}</ul>
                    {item.control.implementation_reference && <small>Implementação de referência: {item.control.implementation_reference}</small>}
                  </div>
                </details>
              ))}
            </div>
          </section>
        ))}
      </div>
    </section>
  );
}

function EvidenceWorkspace({
  initiativeId,
  evidence,
  onUploaded,
}: {
  initiativeId: string;
  evidence: Evidence[];
  onUploaded: (record: Evidence) => void;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("file");
    try {
      if (!(file instanceof File) || file.size === 0) {
        throw new Error("Selecione um arquivo não vazio.");
      }
      const record = await uploadEvidence(
        initiativeId,
        data.get("kind") as EvidenceKind,
        file,
      );
      onUploaded(record);
      form.reset();
      setOpen(false);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao enviar evidência.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel evidence-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">ARTEFATOS VERIFICÁVEIS</p>
          <h2>Evidências anexadas</h2>
        </div>
        <button className="button button-small" onClick={() => setOpen(!open)}>
          {open ? "Cancelar" : "Anexar evidência"}
        </button>
      </div>
      {open && (
        <form className="evidence-form" onSubmit={upload}>
          <div className="field-grid">
            <label>
              Finalidade
              <select name="kind" defaultValue="assessment">
                {EVIDENCE_KINDS.map((kind) => (
                  <option value={kind.value} key={kind.value}>{kind.label}</option>
                ))}
              </select>
            </label>
            <label>
              Arquivo
              <input
                name="file"
                type="file"
                required
                accept=".pdf,.png,.jpg,.jpeg,.txt,.csv,.json"
              />
            </label>
          </div>
          <small>Limite padrão de 10 MiB. O arquivo será validado, escaneado e vinculado ao SHA-256.</small>
          {error && <div className="notice notice-error">{error}</div>}
          <button className="button button-primary" disabled={busy}>
            {busy ? "Validando e escaneando…" : "Enviar com verificação"}
          </button>
        </form>
      )}
      {evidence.length === 0 ? (
        <div className="empty compact-empty">
          <strong>Nenhum artefato anexado.</strong>
          <span>Referências informadas em aprovações não são tratadas como arquivos verificados.</span>
        </div>
      ) : (
        <div className="evidence-list">
          {evidence.map((record) => (
            <article className="evidence-row" key={record.id}>
              <div>
                <strong>{record.original_filename}</strong>
                <small>{EVIDENCE_KINDS.find((kind) => kind.value === record.kind)?.label}</small>
              </div>
              <div className="evidence-integrity">
                <StatusPill value={record.scan_status} />
                <code title={record.sha256}>SHA-256 {record.sha256.slice(0, 12)}…</code>
                <small>{(record.size_bytes / 1024).toFixed(1)} KiB · {record.scanner}</small>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}

function ApprovalCard({ approval, initiativeId, onUpdated }: { approval: Approval; initiativeId: string; onUpdated: (value: Initiative) => Promise<void> }) {
  const authConfig = getPortalAuthConfig();
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function decide(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const identity = authConfig.mode === "local"
        ? { userId: String(data.get("reviewer")), areas: [approval.area] }
        : undefined;
      const updated = await decideApproval(
        initiativeId,
        approval.id,
        {
          decision: data.get("decision") as "approved" | "rejected" | "changes_requested",
          comments: String(data.get("comments")),
          evidence_uri: String(data.get("evidence_uri")),
          expected_version: approval.version,
        },
        identity,
      );
      await onUpdated(updated); setOpen(false);
    } catch (reason) { setError(reason instanceof Error ? reason.message : "Falha ao registrar decisão."); }
    finally { setBusy(false); }
  }

  return <article className={`approval-card ${approval.required ? "" : "muted"}`}>
    <div className="approval-top"><span className="area-icon">{label(approval.area).slice(0, 2).toUpperCase()}</span><div><strong>{label(approval.area)}</strong><small>{approval.required ? "Aprovação obrigatória" : "Sem gate nesta proposta"}</small></div><StatusPill value={approval.status} /></div>
    <p>{approval.reason}</p>
    {approval.decided_by && <small>Decidido por {approval.decided_by}: {approval.comments}</small>}
    {approval.status === "pending" && <button className="link-button" onClick={() => setOpen(!open)}>{open ? "Fechar" : "Registrar decisão"}</button>}
    {open && <form className="decision-form" onSubmit={decide}>
      {authConfig.mode === "local" ? (
        <label>Identificação do revisor<input name="reviewer" required minLength={3} placeholder={`revisor.${approval.area}`} /></label>
      ) : (
        <p className="authenticated-reviewer">A decisão será vinculada à sua identidade corporativa autenticada.</p>
      )}
      <label>Decisão<select name="decision"><option value="approved">Aprovar</option><option value="changes_requested">Solicitar ajustes</option><option value="rejected">Rejeitar definitivamente</option></select></label>
      <label>Justificativa<textarea name="comments" required minLength={5} rows={2} /></label>
      <label>Referência da evidência<input name="evidence_uri" required placeholder="URL, ticket ou URN" /></label>
      {error && <div className="notice notice-error">{error}</div>}
      <button className="button button-primary button-small" disabled={busy}>{busy ? "Registrando…" : "Confirmar decisão"}</button>
    </form>}
  </article>;
}

function RevisionWorkspace({
  initiative,
  assessments,
  onUpdated,
}: {
  initiative: Initiative;
  assessments: Assessment[];
  onUpdated: (value: Initiative) => Promise<void>;
}) {
  const [saving, setSaving] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const requiredAssessments = initiative.required_documents.filter(isAssessmentKind);
  const blockingAssessments = requiredAssessments.filter(
    (kind) => assessments.find((item) => item.assessment_type === kind)?.status !== "under_review",
  );

  async function saveRevision(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const countries = String(data.get("inference_countries"))
      .split(",")
      .map((country) => country.trim())
      .filter(Boolean);
    try {
      const updated = await saveInitiativeRevision(initiative.id, {
        expected_version: initiative.version,
        change_reason: String(data.get("change_reason")),
        name: String(data.get("name")),
        description: String(data.get("description")),
        business_area: String(data.get("business_area")),
        intended_users: String(data.get("intended_users")),
        decision_impact: String(data.get("decision_impact")),
        data_classification: String(data.get("data_classification")),
        autonomy_level: String(data.get("autonomy_level")),
        hosting_model: String(data.get("hosting_model")),
        affects_rights: data.get("affects_rights") === "on",
        executes_actions: data.get("executes_actions") === "on",
        personal_data: data.get("personal_data") === "on",
        sensitive_data: data.get("sensitive_data") === "on",
        children_data: data.get("children_data") === "on",
        external_facing: data.get("external_facing") === "on",
        regulated_context: data.get("regulated_context") === "on",
        international_processing: data.get("international_processing") === "on",
        inference_countries: countries,
        uses_rag: data.get("uses_rag") === "on",
        uses_agents: data.get("uses_agents") === "on",
        uses_mcp: data.get("uses_mcp") === "on",
        uses_custom_model: data.get("uses_custom_model") === "on",
      });
      await onUpdated(updated);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao salvar a revisão.");
    } finally {
      setSaving(false);
    }
  }

  async function resubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const updated = await resubmitInitiative(initiative.id, {
        expected_version: initiative.version,
        revision_summary: String(data.get("revision_summary")),
      });
      await onUpdated(updated);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao reenviar a proposta.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <section className="panel revision-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">RODADA {initiative.current_review_round} · AÇÃO DO OWNER</p>
          <h2>Revisar e reenviar proposta</h2>
        </div>
        <StatusPill value="changes_requested" />
      </div>
      <form className="revision-form" onSubmit={saveRevision}>
        <div className="notice revision-notice">
          Salve os novos fatos para recalcular os requisitos. Depois, conclua os
          assessments exigidos e crie uma nova rodada.
        </div>
        <label>
          Motivo desta atualização
          <textarea name="change_reason" required minLength={5} maxLength={2000} rows={2} />
          <small>O log guarda somente um hash deste texto, não seu conteúdo.</small>
        </label>
        <div className="field-grid">
          <label>Nome<input name="name" required minLength={3} defaultValue={initiative.name} /></label>
          <label>Área de negócio<input name="business_area" required minLength={2} defaultValue={initiative.business_area} /></label>
        </div>
        <label>Descrição<textarea name="description" required minLength={20} rows={4} defaultValue={initiative.description} /></label>
        <label>Usuários previstos<textarea name="intended_users" required minLength={3} rows={2} defaultValue={initiative.intended_users} /></label>
        <div className="field-grid">
          <label>Impacto da decisão<select name="decision_impact" defaultValue={initiative.decision_impact}><option value="informational">Informacional</option><option value="operational">Operacional</option><option value="material">Material</option><option value="rights_or_safety">Direitos ou segurança</option></select></label>
          <label>Classificação dos dados<select name="data_classification" defaultValue={initiative.data_classification}><option value="public">Público</option><option value="internal">Interno</option><option value="confidential">Confidencial</option><option value="restricted">Restrito</option></select></label>
          <label>Autonomia<select name="autonomy_level" defaultValue={initiative.autonomy_level}><option value="a0_information">A0 · Informação</option><option value="a1_recommendation">A1 · Recomendação</option><option value="a2_prepare_for_approval">A2 · Prepara ação</option><option value="a3_reversible_actions">A3 · Ação reversível</option><option value="a4_high_impact_actions">A4 · Alto impacto</option><option value="a5_high_autonomy">A5 · Alta autonomia</option></select></label>
          <label>Hospedagem<select name="hosting_model" defaultValue={initiative.hosting_model}><option value="saas">Serviço SaaS</option><option value="cloud_managed">Nuvem gerenciada</option><option value="self_hosted">Própria</option><option value="hybrid">Híbrida</option></select></label>
        </div>
        <div className="check-grid revision-checks">
          {[
            ["affects_rights", "Afeta direitos", initiative.affects_rights],
            ["executes_actions", "Executa ações", initiative.executes_actions],
            ["personal_data", "Usa dados pessoais", initiative.personal_data],
            ["sensitive_data", "Usa dados sensíveis", initiative.sensitive_data],
            ["children_data", "Dados de crianças", initiative.children_data],
            ["external_facing", "Externo", initiative.external_facing],
            ["regulated_context", "Contexto regulado", initiative.regulated_context],
            ["international_processing", "Processamento internacional", initiative.international_processing],
            ["uses_rag", "Usa RAG", initiative.uses_rag],
            ["uses_agents", "Usa agentes", initiative.uses_agents],
            ["uses_mcp", "Usa MCP", initiative.uses_mcp],
            ["uses_custom_model", "Modelo customizado", initiative.uses_custom_model],
          ].map(([name, text, checked]) => (
            <label className="check" key={String(name)}>
              <input name={String(name)} type="checkbox" defaultChecked={Boolean(checked)} />
              <span>{String(text)}</span>
            </label>
          ))}
        </div>
        <label>
          Países de inferência
          <input name="inference_countries" defaultValue={initiative.inference_countries?.join(", ")} placeholder="Brasil, Estados Unidos" />
        </label>
        {error && <div className="notice notice-error">{error}</div>}
        <button className="button" disabled={saving}>
          {saving ? "Reavaliando política…" : "Salvar proposta revisada"}
        </button>
      </form>
      <form className="resubmission-form" onSubmit={resubmit}>
        <div>
          <strong>Nova rodada de revisão</strong>
          <small>A proposta e os assessments de cada rodada permanecem preservados.</small>
        </div>
        {blockingAssessments.length > 0 && (
          <div className="notice notice-error">
            Conclua e reenvie: {blockingAssessments.map((kind) => label(kind)).join(", ")}.
          </div>
        )}
        <label>
          Resumo final das correções
          <textarea name="revision_summary" required minLength={10} maxLength={2000} rows={3} />
        </label>
        <button className="button button-primary" disabled={submitting || blockingAssessments.length > 0}>
          {submitting ? "Criando rodada…" : "Criar nova rodada de revisão"}
        </button>
      </form>
    </section>
  );
}

function ReviewHistory({ history }: { history: ReviewSubmission[] }) {
  if (history.length === 0) return null;
  return (
    <section className="panel history-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">TRILHA IMUTÁVEL</p>
          <h2>Histórico de revisões</h2>
        </div>
        <small>{history.length} {history.length === 1 ? "rodada" : "rodadas"}</small>
      </div>
      <div className="history-list">
        {[...history].reverse().map((round) => (
          <article className="history-round" key={round.id}>
            <div className="history-round-heading">
              <div>
                <strong>Rodada {round.review_round}</strong>
                <small>{new Date(round.submitted_at).toLocaleString("pt-BR")} · {round.submitted_by}</small>
              </div>
              <div className="status-row"><StatusPill value={round.risk_tier} /><StatusPill value={round.status} /></div>
            </div>
            <p>{round.revision_summary}</p>
            <div className="history-gates">
              {round.approvals.filter((item) => item.required).map((approval) => (
                <span key={approval.id}>{label(approval.area)} <StatusPill value={approval.status} /></span>
              ))}
            </div>
            <small>Política {round.policy_id} v{round.policy_version} · score {round.risk_score}</small>
          </article>
        ))}
      </div>
    </section>
  );
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
  const [assessments, setAssessments] = useState<Assessment[]>([]);
  const [controlReport, setControlReport] = useState<InitiativeControlReport | null>(null);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [history, setHistory] = useState<ReviewSubmission[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    Promise.all([getInitiative(id), listAssessments(id), getInitiativeControls(id), listEvidence(id), listReviewHistory(id)])
      .then(([initiativeValue, assessmentValues, controls, evidenceValues, reviewHistory]) => {
        setInitiative(initiativeValue);
        setAssessments(assessmentValues);
        setControlReport(controls);
        setEvidence(evidenceValues);
        setHistory(reviewHistory);
      })
      .catch((reason: Error) => setError(reason.message));
  }, [id]);

  async function submit() {
    if (!initiative) return; setBusy(true); setError("");
    try { await refreshWorkflow(await submitInitiative(initiative.id, initiative.version)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Falha na submissão."); }
    finally { setBusy(false); }
  }

  async function refreshWorkflow(updated: Initiative) {
    setInitiative(updated);
    const [assessmentValues, controls, reviewHistory] = await Promise.all([
      listAssessments(updated.id),
      getInitiativeControls(updated.id),
      listReviewHistory(updated.id),
    ]);
    setAssessments(assessmentValues);
    setControlReport(controls);
    setHistory(reviewHistory);
  }

  if (error && !initiative) return <div className="page-shell"><div className="notice notice-error">{error}</div></div>;
  if (!initiative) return <div className="page-shell"><div className="empty">Carregando iniciativa…</div></div>;
  const currentApprovals = initiative.approvals?.filter(
    (item) => item.review_round === initiative.current_review_round,
  ) ?? [];
  const required = currentApprovals.filter((item) => item.required);
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
    <AssessmentWorkspace assessments={assessments} initiative={initiative} />
    {initiative.status === "changes_requested" && (
      <RevisionWorkspace
        initiative={initiative}
        assessments={assessments}
        onUpdated={refreshWorkflow}
      />
    )}
    <EvidenceWorkspace
      initiativeId={initiative.id}
      evidence={evidence}
      onUploaded={(record) => setEvidence((current) => [...current, record])}
    />
    {controlReport && <ControlWorkspace report={controlReport} />}
    {initiative.current_review_round > 0 && <section className="panel approvals-panel"><div className="panel-heading"><div><p className="eyebrow">FLUXO DE APROVAÇÃO · RODADA {initiative.current_review_round}</p><h2>{approved} de {required.length} gates concluídos</h2></div><div className="progress"><span style={{ width: `${required.length ? (approved / required.length) * 100 : 0}%` }} /></div></div><div className="approval-grid">{currentApprovals.map((approval) => <ApprovalCard approval={approval} initiativeId={initiative.id} key={approval.id} onUpdated={refreshWorkflow} />)}</div></section>}
    <ReviewHistory history={history} />
    {(initiative.status === "approved" || (initiative.systems?.length ?? 0) > 0) && (
      <SystemInventory initiative={initiative} onCreated={addSystem} />
    )}
  </div>;
}
