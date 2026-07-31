"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useState } from "react";

import { StatusPill } from "@/components/StatusPill";
import {
  createAgent,
  createModel,
  getAISystem,
  retireAgent,
  retireAISystem,
  retireModel,
} from "@/lib/api";
import { label } from "@/lib/labels";
import type { AISystem, AgentAsset, ModelAsset } from "@/lib/types";

function csv(value: FormDataEntryValue | null): string[] {
  return String(value ?? "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function optionalNumber(value: FormDataEntryValue | null): number | null {
  const normalized = String(value ?? "").trim();
  return normalized ? Number(normalized) : null;
}

function ModelForm({
  systemId,
  onCreated,
}: {
  systemId: string;
  onCreated: (model: ModelAsset) => void;
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
      const model = await createModel(systemId, {
        provider: String(data.get("provider")),
        model_name: String(data.get("model_name")),
        model_version: String(data.get("model_version")),
        deployment_region: String(data.get("deployment_region")),
        approved_use_cases: csv(data.get("approved_use_cases")),
        prohibited_use_cases: csv(data.get("prohibited_use_cases")),
        allowed_data_classes: data.getAll("allowed_data_classes").map(String),
      });
      onCreated(model);
      form.reset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao cadastrar o modelo.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="asset-form" onSubmit={submit}>
      <h3>Novo modelo</h3>
      <div className="field-grid">
        <label>Provedor<input name="provider" required minLength={2} /></label>
        <label>Modelo<input name="model_name" required minLength={2} /></label>
        <label>Versão<input name="model_version" required /></label>
        <label>Região de inferência<input name="deployment_region" required minLength={2} /></label>
      </div>
      <label>Usos aprovados<input name="approved_use_cases" placeholder="Separe por vírgula" /></label>
      <label>Usos proibidos<input name="prohibited_use_cases" placeholder="Separe por vírgula" /></label>
      <span className="field-label">Classes de dados autorizadas</span>
      <div className="check-grid compact-checks">
        {["public", "internal", "confidential", "restricted"].map((value) => (
          <label className="check" key={value}>
            <input name="allowed_data_classes" type="checkbox" value={value} />
            <span>{label(value)}</span>
          </label>
        ))}
      </div>
      {error && <div className="notice notice-error">{error}</div>}
      <button className="button button-primary" disabled={busy}>
        {busy ? "Cadastrando…" : "Cadastrar modelo"}
      </button>
    </form>
  );
}

function AgentForm({
  system,
  onCreated,
}: {
  system: AISystem;
  onCreated: (agent: AgentAsset) => void;
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
      const agent = await createAgent(system.id, {
        name: String(data.get("name")),
        purpose: String(data.get("purpose")),
        owner_id: String(data.get("owner_id")),
        autonomy_level: String(data.get("autonomy_level")),
        allowed_models: data.getAll("allowed_models").map(String),
        tools: csv(data.get("tools")),
        permissions: csv(data.get("permissions")),
        max_cost: optionalNumber(data.get("max_cost")),
        max_runtime_seconds: optionalNumber(data.get("max_runtime_seconds")),
        human_approval_points: csv(data.get("human_approval_points")),
        kill_switch_enabled: data.get("kill_switch_enabled") === "on",
      });
      onCreated(agent);
      form.reset();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao cadastrar o agente.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="asset-form" onSubmit={submit}>
      <h3>Novo agente</h3>
      <div className="field-grid">
        <label>Nome<input name="name" required minLength={2} /></label>
        <label>Responsável<input name="owner_id" required defaultValue={system.owner_id} /></label>
        <label>
          Autonomia
          <select name="autonomy_level" defaultValue="a0_information">
            <option value="a0_information">Apenas informação</option>
            <option value="a1_recommendation">Recomenda ação</option>
            <option value="a2_prepare_for_approval">Prepara para aprovação</option>
            <option value="a3_reversible_actions">Executa ações reversíveis</option>
            <option value="a4_high_impact_actions">Executa ações de alto impacto</option>
            <option value="a5_high_autonomy">Alta autonomia</option>
          </select>
        </label>
        <label>Custo máximo por execução<input name="max_cost" min="0" step="0.01" type="number" /></label>
      </div>
      <label>Finalidade<textarea name="purpose" required minLength={10} rows={3} /></label>
      <div className="field-grid">
        <label>Tempo máximo em segundos<input name="max_runtime_seconds" min="1" type="number" /></label>
        <label>Ferramentas<input name="tools" placeholder="Separe por vírgula" /></label>
        <label>Permissões<input name="permissions" placeholder="Separe por vírgula" /></label>
        <label>Pontos de aprovação humana<input name="human_approval_points" placeholder="Separe por vírgula" /></label>
      </div>
      {(system.models?.length ?? 0) > 0 && (
        <>
          <span className="field-label">Modelos permitidos</span>
          <div className="check-grid compact-checks">
            {system.models?.map((model) => (
              <label className="check" key={model.id}>
                <input name="allowed_models" type="checkbox" value={model.id} />
                <span>{model.provider} · {model.model_name}</span>
              </label>
            ))}
          </div>
        </>
      )}
      <label className="check inline-check">
        <input name="kill_switch_enabled" type="checkbox" defaultChecked />
        <span>Kill switch disponível</span>
      </label>
      {error && <div className="notice notice-error">{error}</div>}
      <button className="button button-primary" disabled={busy}>
        {busy ? "Cadastrando…" : "Cadastrar agente"}
      </button>
    </form>
  );
}

export default function AISystemPage() {
  const { id } = useParams<{ id: string }>();
  const [system, setSystem] = useState<AISystem | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    getAISystem(id).then(setSystem).catch((reason: Error) => setError(reason.message));
  }, [id]);

  function addModel(model: ModelAsset) {
    setSystem((current) =>
      current ? { ...current, models: [...(current.models ?? []), model] } : current,
    );
  }

  function addAgent(agent: AgentAsset) {
    setSystem((current) =>
      current ? { ...current, agents: [...(current.agents ?? []), agent] } : current,
    );
  }

  async function retireSystem() {
    if (!system) return;
    setBusy("system");
    setError("");
    try {
      setSystem(await retireAISystem(system.id, system.version));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao aposentar o sistema.");
    } finally {
      setBusy("");
    }
  }

  async function retireRegisteredModel(model: ModelAsset) {
    setBusy(model.id);
    setError("");
    try {
      const retired = await retireModel(model.id, model.version);
      setSystem((current) => current ? {
        ...current,
        models: current.models?.map((item) => item.id === retired.id ? retired : item),
      } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao aposentar o modelo.");
    } finally {
      setBusy("");
    }
  }

  async function retireRegisteredAgent(agent: AgentAsset) {
    setBusy(agent.id);
    setError("");
    try {
      const retired = await retireAgent(agent.id, agent.version);
      setSystem((current) => current ? {
        ...current,
        agents: current.agents?.map((item) => item.id === retired.id ? retired : item),
      } : current);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Falha ao aposentar o agente.");
    } finally {
      setBusy("");
    }
  }

  if (error && !system) {
    return <div className="page-shell"><div className="notice notice-error">{error}</div></div>;
  }
  if (!system) {
    return <div className="page-shell"><div className="empty">Carregando sistema…</div></div>;
  }
  const mutable = system.status === "approved" || system.status === "active";

  return (
    <div className="page-shell detail-page">
      <div className="breadcrumb">
        <Link href="/">Portfólio</Link><span>/</span>
        <Link href={`/initiatives/${system.initiative_id}`}>Iniciativa</Link><span>/</span>
        <span>{system.name}</span>
      </div>
      <section className="detail-header">
        <div>
          <div className="status-row">
            <StatusPill value={system.status} />
            <StatusPill value={system.risk_tier} />
          </div>
          <h1>{system.name}</h1>
          <p>{system.purpose}</p>
        </div>
        {mutable && (
          <button className="button" disabled={busy === "system"} onClick={retireSystem}>
            {busy === "system" ? "Aposentando…" : "Aposentar sistema"}
          </button>
        )}
      </section>
      {error && <div className="notice notice-error">{error}</div>}
      <section className="asset-summary">
        <article className="panel"><span>Modelos registrados</span><strong>{system.models?.length ?? 0}</strong></article>
        <article className="panel"><span>Agentes registrados</span><strong>{system.agents?.length ?? 0}</strong></article>
        <article className="panel"><span>Responsável</span><strong>{system.owner_id}</strong></article>
      </section>

      <section className="asset-columns">
        <article className="panel asset-panel">
          <div className="panel-heading"><div><p className="eyebrow">MODEL REGISTRY</p><h2>Modelos</h2></div></div>
          <div className="asset-list">
            {system.models?.map((model) => (
              <div className="asset-card" key={model.id}>
                <div className="asset-card-heading">
                  <div><strong>{model.provider} · {model.model_name}</strong><small>{model.model_version} · {model.deployment_region}</small></div>
                  <StatusPill value={model.status} />
                </div>
                <p>Dados: {model.allowed_data_classes.map(label).join(", ") || "não definidos"}</p>
                {model.status !== "retired" && mutable && (
                  <button className="link-button" disabled={busy === model.id} onClick={() => retireRegisteredModel(model)}>Aposentar modelo</button>
                )}
              </div>
            ))}
            {(system.models?.length ?? 0) === 0 && <div className="empty compact-empty">Nenhum modelo registrado.</div>}
          </div>
          {mutable && <ModelForm systemId={system.id} onCreated={addModel} />}
        </article>

        <article className="panel asset-panel">
          <div className="panel-heading"><div><p className="eyebrow">AGENT REGISTRY</p><h2>Agentes</h2></div></div>
          <div className="asset-list">
            {system.agents?.map((agent) => (
              <div className="asset-card" key={agent.id}>
                <div className="asset-card-heading">
                  <div><strong>{agent.name}</strong><small>{label(agent.autonomy_level)} · {agent.owner_id}</small></div>
                  <StatusPill value={agent.status} />
                </div>
                <p>{agent.purpose}</p>
                {agent.status !== "retired" && mutable && (
                  <button className="link-button" disabled={busy === agent.id} onClick={() => retireRegisteredAgent(agent)}>Aposentar agente</button>
                )}
              </div>
            ))}
            {(system.agents?.length ?? 0) === 0 && <div className="empty compact-empty">Nenhum agente registrado.</div>}
          </div>
          {mutable && <AgentForm system={system} onCreated={addAgent} />}
        </article>
      </section>
    </div>
  );
}
