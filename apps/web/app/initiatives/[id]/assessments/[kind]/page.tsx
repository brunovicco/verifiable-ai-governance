"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { useParams } from "next/navigation";

import { StatusPill } from "@/components/StatusPill";
import {
  getInitiative,
  listAssessments,
  saveAssessment,
  submitAssessment,
} from "@/lib/api";
import { label } from "@/lib/labels";
import type { Assessment, AssessmentKind, Initiative } from "@/lib/types";

const ASSESSMENT_KINDS: AssessmentKind[] = [
  "ai-impact-assessment",
  "ripd",
  "international-processing-assessment",
];

const INTRODUCTIONS: Record<AssessmentKind, string> = {
  "ai-impact-assessment":
    "Registre benefícios, pessoas afetadas, possíveis danos e como a organização manterá supervisão e contestação.",
  ripd:
    "Documente o tratamento de dados pessoais, seus riscos e as salvaguardas para análise da área de Privacidade.",
  "international-processing-assessment":
    "Mapeie inferência, armazenamento, logs, fornecedores e mecanismos aplicáveis ao fluxo internacional.",
};

/** Convert a comma-separated answer into normalized values. */
function splitList(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

/** Read a persisted scalar answer without trusting its runtime shape. */
function answerText(assessment: Assessment | null, field: string): string {
  const value = assessment?.answers[field];
  return typeof value === "string" ? value : "";
}

/** Read a persisted list answer as text suitable for a guided input. */
function answerList(assessment: Assessment | null, field: string): string {
  const value = assessment?.answers[field];
  return Array.isArray(value) ? value.filter((item) => typeof item === "string").join(", ") : "";
}

/** Narrow the dynamic route value to one supported assessment definition. */
function isAssessmentKind(value: string): value is AssessmentKind {
  return ASSESSMENT_KINDS.some((kind) => kind === value);
}

/** Map non-technical form fields to the versioned API definition. */
function buildAnswers(kind: AssessmentKind, data: FormData): Record<string, unknown> {
  const residualRisk = String(data.get("residual_risk"));
  if (kind === "ai-impact-assessment") {
    return {
      assessment_type: kind,
      affected_groups: splitList(data.get("affected_groups")),
      intended_benefits: String(data.get("intended_benefits")),
      potential_harms: splitList(data.get("potential_harms")),
      human_oversight: String(data.get("human_oversight")),
      contestability: String(data.get("contestability")),
      mitigation_measures: splitList(data.get("mitigation_measures")),
      residual_risk: residualRisk,
    };
  }
  if (kind === "ripd") {
    return {
      assessment_type: kind,
      controller_area: String(data.get("controller_area")),
      processing_purpose: String(data.get("processing_purpose")),
      personal_data_categories: splitList(data.get("personal_data_categories")),
      data_subjects: splitList(data.get("data_subjects")),
      legal_basis: String(data.get("legal_basis")),
      necessity_assessment: String(data.get("necessity_assessment")),
      risk_scenarios: splitList(data.get("risk_scenarios")),
      safeguards: splitList(data.get("safeguards")),
      residual_risk: residualRisk,
    };
  }
  const subprocessorName = String(data.get("subprocessor_name") ?? "").trim();
  return {
    assessment_type: kind,
    data_categories: splitList(data.get("data_categories")),
    source_country: String(data.get("source_country")),
    inference_countries: splitList(data.get("inference_countries")),
    storage_regions: splitList(data.get("storage_regions")),
    log_regions: splitList(data.get("log_regions")),
    subprocessors: subprocessorName
      ? [
          {
            name: subprocessorName,
            countries: splitList(data.get("subprocessor_countries")),
            purpose: String(data.get("subprocessor_purpose")),
          },
        ]
      : [],
    transfer_mechanism: String(data.get("transfer_mechanism")),
    legal_basis: String(data.get("legal_basis")),
    safeguards: splitList(data.get("safeguards")),
    residual_risk: residualRisk,
  };
}

/** Render definition-specific fields while preserving a single lifecycle form. */
function AssessmentFields({
  assessment,
  disabled,
  kind,
}: {
  assessment: Assessment | null;
  disabled: boolean;
  kind: AssessmentKind;
}) {
  if (kind === "ai-impact-assessment") {
    return (
      <>
        <fieldset disabled={disabled}>
          <legend><span>01</span><div>Impacto esperado<small>Pessoas afetadas, benefício e possíveis danos</small></div></legend>
          <label>Quem pode ser afetado?<input name="affected_groups" required defaultValue={answerList(assessment, "affected_groups")} placeholder="Ex.: clientes, atendentes, fornecedores" /><small>Separe os grupos por vírgula.</small></label>
          <label>Quais benefícios são esperados?<textarea name="intended_benefits" required minLength={10} rows={4} defaultValue={answerText(assessment, "intended_benefits")} /></label>
          <label>Quais danos ou efeitos indesejados são plausíveis?<input name="potential_harms" required defaultValue={answerList(assessment, "potential_harms")} placeholder="Ex.: orientação incorreta, tratamento desigual" /><small>Separe os cenários por vírgula.</small></label>
        </fieldset>
        <fieldset disabled={disabled}>
          <legend><span>02</span><div>Salvaguardas humanas<small>Supervisão, contestação e mitigação</small></div></legend>
          <label>Como ocorrerá a supervisão humana?<textarea name="human_oversight" required minLength={10} rows={4} defaultValue={answerText(assessment, "human_oversight")} /></label>
          <label>Como uma pessoa poderá questionar ou corrigir o resultado?<textarea name="contestability" required minLength={10} rows={4} defaultValue={answerText(assessment, "contestability")} /></label>
          <label>Quais medidas reduzem os riscos?<input name="mitigation_measures" required defaultValue={answerList(assessment, "mitigation_measures")} placeholder="Ex.: revisão humana, limites de uso, avaliação periódica" /><small>Separe as medidas por vírgula.</small></label>
        </fieldset>
      </>
    );
  }
  if (kind === "ripd") {
    return (
      <>
        <fieldset disabled={disabled}>
          <legend><span>01</span><div>Tratamento de dados<small>Finalidade, titulares e necessidade</small></div></legend>
          <div className="field-grid">
            <label>Área controladora<input name="controller_area" required minLength={2} defaultValue={answerText(assessment, "controller_area")} /></label>
            <label>Hipótese ou base legal<input name="legal_basis" required minLength={3} defaultValue={answerText(assessment, "legal_basis")} /></label>
          </div>
          <label>Qual é a finalidade do tratamento?<textarea name="processing_purpose" required minLength={10} rows={4} defaultValue={answerText(assessment, "processing_purpose")} /></label>
          <div className="field-grid">
            <label>Categorias de dados pessoais<input name="personal_data_categories" required defaultValue={answerList(assessment, "personal_data_categories")} placeholder="Ex.: nome, e-mail, histórico" /></label>
            <label>Grupos de titulares<input name="data_subjects" required defaultValue={answerList(assessment, "data_subjects")} placeholder="Ex.: clientes, colaboradores" /></label>
          </div>
          <label>Por que o tratamento é necessário e proporcional?<textarea name="necessity_assessment" required minLength={10} rows={4} defaultValue={answerText(assessment, "necessity_assessment")} /></label>
        </fieldset>
        <fieldset disabled={disabled}>
          <legend><span>02</span><div>Riscos de privacidade<small>Cenários e medidas de proteção</small></div></legend>
          <label>Cenários de risco<input name="risk_scenarios" required defaultValue={answerList(assessment, "risk_scenarios")} placeholder="Ex.: acesso indevido, retenção excessiva" /></label>
          <label>Salvaguardas aplicadas<input name="safeguards" required defaultValue={answerList(assessment, "safeguards")} placeholder="Ex.: minimização, criptografia, controle de acesso" /></label>
        </fieldset>
      </>
    );
  }
  const subprocessors = assessment?.answers.subprocessors;
  const firstSubprocessor = Array.isArray(subprocessors) && subprocessors.length > 0 && typeof subprocessors[0] === "object" && subprocessors[0] !== null
    ? subprocessors[0] as Record<string, unknown>
    : null;
  const subprocessorCountries = Array.isArray(firstSubprocessor?.countries)
    ? firstSubprocessor.countries.filter((item) => typeof item === "string").join(", ")
    : "";
  return (
    <>
      <fieldset disabled={disabled}>
        <legend><span>01</span><div>Mapa do fluxo internacional<small>Dados, inferência, armazenamento e logs</small></div></legend>
        <label>Categorias de dados enviadas ou acessadas<input name="data_categories" required defaultValue={answerList(assessment, "data_categories")} placeholder="Ex.: prompts, documentos, telemetria" /></label>
        <div className="field-grid">
          <label>País de origem<input name="source_country" required minLength={2} defaultValue={answerText(assessment, "source_country") || "Brasil"} /></label>
          <label>Países de inferência<input name="inference_countries" required defaultValue={answerList(assessment, "inference_countries")} /></label>
          <label>Regiões de armazenamento<input name="storage_regions" required defaultValue={answerList(assessment, "storage_regions")} /></label>
          <label>Regiões dos logs e telemetria<input name="log_regions" required defaultValue={answerList(assessment, "log_regions")} /></label>
        </div>
      </fieldset>
      <fieldset disabled={disabled}>
        <legend><span>02</span><div>Fornecedor e salvaguardas<small>Suboperadores, fundamento e controles</small></div></legend>
        <div className="field-grid">
          <label>Fornecedor ou suboperador<input name="subprocessor_name" defaultValue={typeof firstSubprocessor?.name === "string" ? firstSubprocessor.name : ""} placeholder="Opcional" /></label>
          <label>Países do suboperador<input name="subprocessor_countries" defaultValue={subprocessorCountries} /></label>
        </div>
        <label>Finalidade do suboperador<input name="subprocessor_purpose" defaultValue={typeof firstSubprocessor?.purpose === "string" ? firstSubprocessor.purpose : ""} /></label>
        <div className="field-grid">
          <label>Mecanismo de transferência<input name="transfer_mechanism" required minLength={3} defaultValue={answerText(assessment, "transfer_mechanism")} /></label>
          <label>Hipótese ou base legal<input name="legal_basis" required minLength={3} defaultValue={answerText(assessment, "legal_basis")} /></label>
        </div>
        <label>Salvaguardas técnicas e contratuais<input name="safeguards" required defaultValue={answerList(assessment, "safeguards")} placeholder="Ex.: criptografia, retenção limitada, proibição de treinamento" /></label>
      </fieldset>
    </>
  );
}

/** Guided assessment page for initiative owners. */
export default function AssessmentPage() {
  const { id, kind: routeKind } = useParams<{ id: string; kind: string }>();
  const kind = isAssessmentKind(routeKind) ? routeKind : null;
  const [initiative, setInitiative] = useState<Initiative | null>(null);
  const [assessment, setAssessment] = useState<Assessment | null>(null);
  const [loading, setLoading] = useState(Boolean(kind));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const formRef = useRef<HTMLFormElement>(null);

  useEffect(() => {
    if (!kind) return;
    Promise.all([getInitiative(id), listAssessments(id)])
      .then(([initiativeValue, assessments]) => {
        setInitiative(initiativeValue);
        setAssessment(assessments.find((item) => item.assessment_type === kind) ?? null);
      })
      .catch((reason: Error) => setError(reason.message))
      .finally(() => setLoading(false));
  }, [id, kind]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!kind) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const updated = await saveAssessment(
        id,
        kind,
        buildAnswers(kind, new FormData(event.currentTarget)),
        assessment?.version ?? null,
      );
      setAssessment(updated);
      setMessage("Rascunho salvo com trilha de auditoria.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível salvar o assessment.");
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!kind || !formRef.current || !formRef.current.reportValidity()) return;
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const saved = await saveAssessment(
        id,
        kind,
        buildAnswers(kind, new FormData(formRef.current)),
        assessment?.version ?? null,
      );
      setAssessment(await submitAssessment(saved.id, saved.version));
      setMessage("Assessment enviado para revisão independente.");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível enviar para revisão.");
    } finally {
      setBusy(false);
    }
  }

  if (!kind) return <div className="page-shell"><div className="notice notice-error">Tipo de assessment desconhecido.</div></div>;
  if (loading) return <div className="page-shell"><div className="empty">Carregando assessment…</div></div>;
  if (error && !initiative) return <div className="page-shell"><div className="notice notice-error">{error}</div></div>;
  if (!initiative) return null;
  const editable = !assessment || assessment.status === "draft";

  return (
    <div className="page-shell form-page assessment-page">
      <div className="breadcrumb"><Link href="/">Portfólio</Link><span>/</span><Link href={`/initiatives/${id}`}>{initiative.name}</Link><span>/</span><span>{label(kind)}</span></div>
      <section className="form-intro assessment-intro">
        <div>
          <p className="eyebrow">ASSESSMENT ESTRUTURADO · SCHEMA 1.0.0</p>
          <h1>{label(kind)}</h1>
          <p>{INTRODUCTIONS[kind]}</p>
        </div>
        {assessment && <div className="assessment-score"><span>Risco residual</span><strong>{assessment.risk_score}</strong><StatusPill value={assessment.risk_tier} /><StatusPill value={assessment.status} /></div>}
      </section>
      {!editable && <div className="notice notice-success">Este assessment está em revisão e permanece somente para leitura.</div>}
      {error && <div className="notice notice-error">Revise as informações: {error}</div>}
      {message && <div className="notice notice-success">{message}</div>}
      <form key={assessment?.version ?? "new"} onSubmit={save} ref={formRef}>
        <AssessmentFields assessment={assessment} disabled={!editable || busy} kind={kind} />
        <fieldset disabled={!editable || busy}>
          <div className="risk-decision">
            <label>Risco residual após as salvaguardas
              <select name="residual_risk" required defaultValue={answerText(assessment, "residual_risk") || "medium"}>
                <option value="low">Baixo</option>
                <option value="medium">Médio</option>
                <option value="high">Alto</option>
                <option value="critical">Crítico</option>
              </select>
              <small>A área revisora poderá confirmar ou ajustar esta classificação.</small>
            </label>
          </div>
        </fieldset>
        <div className="form-actions">
          <Link className="button" href={`/initiatives/${id}`}>Voltar à iniciativa</Link>
          {editable && <button className="button" disabled={busy} type="submit">{busy ? "Salvando…" : "Salvar rascunho"}</button>}
          {editable && <button className="button button-primary" disabled={busy} onClick={submit} type="button">Salvar e enviar para revisão</button>}
        </div>
      </form>
    </div>
  );
}
