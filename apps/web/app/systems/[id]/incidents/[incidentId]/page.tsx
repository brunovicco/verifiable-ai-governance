"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { StatusPill } from "@/components/StatusPill";
import {
  closeIncident,
  containIncident,
  engageKillSwitch,
  getAISystem,
  getIncident,
  listExceptions,
  requestException,
  restoreKillSwitch,
  setRemediationPlan,
} from "@/lib/api";
import type { AgentAsset, AISystem, Incident, PolicyException } from "@/lib/types";

function formatDate(value: string | null): string {
  if (!value) return "não definida";
  return new Intl.DateTimeFormat("pt-BR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(new Date(value));
}

function ContainForm({
  incident,
  onUpdated,
}: {
  incident: Incident;
  onUpdated: (incident: Incident) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      onUpdated(
        await containIncident(incident.id, String(data.get("containment")), incident.version),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao conter o incidente.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="asset-form" onSubmit={submit}>
      <h3>Conter incidente</h3>
      <label>Medidas de contenção<textarea name="containment" required minLength={5} rows={2} /></label>
      {error && <div className="notice notice-error">{error}</div>}
      <button className="button button-primary button-small" disabled={busy}>
        {busy ? "Registrando…" : "Registrar contenção"}
      </button>
    </form>
  );
}

function RemediationPlanForm({
  incident,
  onUpdated,
}: {
  incident: Incident;
  onUpdated: (incident: Incident) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      onUpdated(
        await setRemediationPlan(incident.id, {
          remediation_owner_id: String(data.get("remediation_owner_id")),
          remediation_description: String(data.get("remediation_description")),
          remediation_due_at: new Date(String(data.get("remediation_due_at"))).toISOString(),
          expected_version: incident.version,
        }),
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao registrar o plano.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="asset-form" onSubmit={submit}>
      <h3>Plano de remediação</h3>
      <div className="field-grid">
        <label>
          Responsável
          <input
            name="remediation_owner_id"
            required
            defaultValue={incident.remediation_owner_id ?? incident.owner_id}
          />
        </label>
        <label>Prazo<input name="remediation_due_at" required type="datetime-local" /></label>
      </div>
      <label>
        Descrição
        <textarea
          name="remediation_description"
          required
          minLength={10}
          rows={3}
          defaultValue={incident.remediation_description ?? ""}
        />
      </label>
      {error && <div className="notice notice-error">{error}</div>}
      <button className="button button-primary button-small" disabled={busy}>
        {busy ? "Salvando…" : "Salvar plano"}
      </button>
    </form>
  );
}

function ExceptionRequestForm({
  incidentId,
  onCreated,
}: {
  incidentId: string;
  onCreated: (exception: PolicyException) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const exception = await requestException(incidentId, {
        purpose: String(data.get("purpose")),
        scope_description: String(data.get("scope_description")),
        compensating_controls: String(data.get("compensating_controls")),
        expires_at: new Date(String(data.get("expires_at"))).toISOString(),
      });
      onCreated(exception);
      form.reset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao solicitar a exceção.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="asset-form" onSubmit={submit}>
      <h3>Solicitar exceção temporária</h3>
      <label>Finalidade<textarea name="purpose" required minLength={5} rows={2} /></label>
      <label>Escopo excepcionado<textarea name="scope_description" required minLength={5} rows={2} /></label>
      <label>Controles compensatórios<textarea name="compensating_controls" required minLength={5} rows={2} /></label>
      <label>Expira em<input name="expires_at" required type="datetime-local" /></label>
      <small>
        A aprovação exige um administrador independente do solicitante, conforme segregação de
        funções.
      </small>
      {error && <div className="notice notice-error">{error}</div>}
      <button className="button button-primary button-small" disabled={busy}>
        {busy ? "Enviando…" : "Solicitar exceção"}
      </button>
    </form>
  );
}

export default function IncidentPage() {
  const { id, incidentId } = useParams<{ id: string; incidentId: string }>();
  const [incident, setIncident] = useState<Incident | null>(null);
  const [system, setSystem] = useState<AISystem | null>(null);
  const [exceptions, setExceptions] = useState<PolicyException[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    getIncident(incidentId).then(setIncident).catch((reason: Error) => setError(reason.message));
    getAISystem(id).then(setSystem).catch(() => undefined);
    listExceptions(incidentId).then(setExceptions).catch(() => undefined);
  }, [id, incidentId]);

  async function toggleKillSwitch(agent: AgentAsset) {
    if (!incident) return;
    setBusy(agent.id);
    setError("");
    try {
      const state = agent.kill_switch_engaged
        ? await restoreKillSwitch(incident.id, agent.id, agent.version)
        : await engageKillSwitch(incident.id, agent.id, agent.version);
      setSystem((current) =>
        current
          ? {
              ...current,
              agents: current.agents?.map((item) =>
                item.id === agent.id
                  ? { ...item, kill_switch_engaged: state.kill_switch_engaged, version: state.version }
                  : item,
              ),
            }
          : current,
      );
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao acionar o kill switch.");
    } finally {
      setBusy("");
    }
  }

  async function close() {
    if (!incident) return;
    setBusy("close");
    setError("");
    try {
      setIncident(await closeIncident(incident.id, incident.version));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao encerrar o incidente.");
    } finally {
      setBusy("");
    }
  }

  if (error && !incident) {
    return <div className="page-shell"><div className="notice notice-error">{error}</div></div>;
  }
  if (!incident) {
    return <div className="page-shell"><div className="empty">Carregando incidente…</div></div>;
  }

  return (
    <div className="page-shell detail-page">
      <div className="breadcrumb">
        <Link href="/">Portfólio</Link><span>/</span>
        <Link href={`/systems/${id}`}>Sistema</Link><span>/</span>
        <span>{incident.title}</span>
      </div>
      <section className="detail-header">
        <div>
          <div className="status-row">
            <StatusPill value={incident.severity} />
            <StatusPill value={incident.status} />
          </div>
          <h1>{incident.title}</h1>
          <p>{incident.description}</p>
        </div>
        {incident.status === "remediating" && (
          <button className="button" disabled={busy === "close"} onClick={close}>
            {busy === "close" ? "Encerrando…" : "Encerrar incidente"}
          </button>
        )}
      </section>
      {error && <div className="notice notice-error">{error}</div>}

      <section className="asset-summary">
        <article className="panel"><span>Detectado em</span><strong>{formatDate(incident.detected_at)}</strong></article>
        <article className="panel"><span>Responsável</span><strong>{incident.owner_id}</strong></article>
        <article className="panel"><span>Encerrado em</span><strong>{formatDate(incident.resolved_at)}</strong></article>
      </section>

      {incident.containment && (
        <div className="asset-review-meta">
          <small>Contenção registrada</small>
          <p>{incident.containment}</p>
        </div>
      )}
      {incident.remediation_description && (
        <div className="asset-review-meta">
          <small>Plano de remediação · responsável {incident.remediation_owner_id} · prazo {formatDate(incident.remediation_due_at)}</small>
          <p>{incident.remediation_description}</p>
        </div>
      )}

      <section className="asset-columns">
        <article className="panel asset-panel">
          <div className="panel-heading"><div><p className="eyebrow">RESPONSE</p><h2>Ações do incidente</h2></div></div>
          <div className="asset-list">
            {incident.status === "open" && <ContainForm incident={incident} onUpdated={setIncident} />}
            {incident.status !== "closed" && (
              <RemediationPlanForm incident={incident} onUpdated={setIncident} />
            )}
          </div>
        </article>

        <article className="panel asset-panel">
          <div className="panel-heading"><div><p className="eyebrow">KILL SWITCH</p><h2>Agentes do sistema</h2></div></div>
          <div className="asset-list">
            {system?.agents?.map((agent) => (
              <div className="asset-card" key={agent.id}>
                <div className="asset-card-heading">
                  <div><strong>{agent.name}</strong><small>{agent.agent_version}</small></div>
                  <StatusPill value={agent.kill_switch_engaged ? "suspended" : "active"} />
                </div>
                {agent.kill_switch_enabled ? (
                  <button
                    className="link-button"
                    disabled={busy === agent.id || incident.status === "closed"}
                    onClick={() => toggleKillSwitch(agent)}
                  >
                    {agent.kill_switch_engaged ? "Restaurar kill switch" : "Acionar kill switch"}
                  </button>
                ) : (
                  <small>Agente não declara kill switch.</small>
                )}
              </div>
            ))}
            {(system?.agents?.length ?? 0) === 0 && (
              <div className="empty compact-empty">Nenhum agente registrado neste sistema.</div>
            )}
          </div>
        </article>
      </section>

      <section className="asset-columns">
        <article className="panel asset-panel">
          <div className="panel-heading"><div><p className="eyebrow">TEMPORARY EXCEPTIONS</p><h2>Exceções</h2></div></div>
          <div className="asset-list">
            {exceptions.map((exception) => (
              <div className="asset-card" key={exception.id}>
                <div className="asset-card-heading">
                  <div><strong>{exception.purpose}</strong><small>Expira em {formatDate(exception.expires_at)}</small></div>
                  <StatusPill value={exception.state} />
                </div>
                <p>{exception.scope_description}</p>
                <p>Controles compensatórios: {exception.compensating_controls}</p>
                {exception.decided_by && (
                  <small>Decidido por {exception.decided_by} em {formatDate(exception.decided_at)}</small>
                )}
              </div>
            ))}
            {exceptions.length === 0 && <div className="empty compact-empty">Nenhuma exceção solicitada.</div>}
          </div>
          {incident.status !== "closed" && (
            <ExceptionRequestForm
              incidentId={incident.id}
              onCreated={(exception) => setExceptions((current) => [exception, ...current])}
            />
          )}
        </article>
      </section>
    </div>
  );
}
