"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";

import { createInitiative } from "@/lib/api";

const checks = [
  ["affects_rights", "Pode afetar direitos, benefícios ou oportunidades"],
  ["executes_actions", "Executa ações em sistemas ou processos"],
  ["personal_data", "Trata dados pessoais"],
  ["sensitive_data", "Trata dados pessoais sensíveis"],
  ["children_data", "Envolve crianças ou adolescentes"],
  ["external_facing", "Interage com clientes, cidadãos ou público externo"],
  ["regulated_context", "Opera em atividade regulada"],
  ["international_processing", "Processa ou permite acesso a dados fora do Brasil"],
  ["uses_rag", "Consulta base de conhecimento (RAG)"],
  ["uses_agents", "Utiliza agentes de IA"],
  ["uses_mcp", "Conecta ferramentas ou servidores MCP"],
  ["uses_custom_model", "Treina, ajusta ou hospeda modelo próprio"],
] as const;

export default function NewInitiativePage() {
  const router = useRouter();
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [international, setInternational] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const payload: Record<string, unknown> = {
      name: data.get("name"),
      description: data.get("description"),
      business_area: data.get("business_area"),
      intended_users: data.get("intended_users"),
      decision_impact: data.get("decision_impact"),
      data_classification: data.get("data_classification"),
      autonomy_level: data.get("autonomy_level"),
      hosting_model: data.get("hosting_model"),
      inference_countries: String(data.get("inference_countries") ?? "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
    };
    for (const [name] of checks) payload[name] = data.get(name) === "on";
    try {
      const initiative = await createInitiative(payload);
      router.push(`/initiatives/${initiative.id}`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Não foi possível cadastrar a proposta.");
      setSubmitting(false);
    }
  }

  return (
    <div className="page-shell form-page">
      <div className="breadcrumb"><Link href="/">Portfólio</Link><span>/</span><span>Nova iniciativa</span></div>
      <section className="form-intro">
        <p className="eyebrow">NOVA PROPOSTA</p>
        <h1>Conte-nos o que você quer construir.</h1>
        <p>Leva cerca de cinco minutos. A avaliação é preliminar e poderá ser revisada pelas áreas responsáveis.</p>
      </section>
      <form onSubmit={handleSubmit}>
        <fieldset>
          <legend><span>01</span><div>Contexto de negócio<small>Finalidade, responsável e público</small></div></legend>
          <label>Nome da iniciativa<input name="name" required minLength={3} placeholder="Ex.: Assistente de atendimento" /></label>
          <label>Qual problema será resolvido?<textarea name="description" required minLength={20} rows={4} placeholder="Descreva o objetivo e o resultado esperado." /></label>
          <div className="field-grid">
            <label>Área responsável<input name="business_area" required placeholder="Ex.: Experiência do Cliente" /></label>
            <label>Quem utilizará?<input name="intended_users" required placeholder="Ex.: Analistas internos" /></label>
          </div>
        </fieldset>

        <fieldset>
          <legend><span>02</span><div>Impacto e autonomia<small>Como a IA influencia ou executa decisões</small></div></legend>
          <div className="field-grid">
            <label>Impacto de uma saída incorreta<select name="decision_impact" defaultValue="informational"><option value="informational">Informativo, facilmente revisável</option><option value="operational">Impacto operacional limitado</option><option value="material">Impacto financeiro, jurídico ou reputacional</option><option value="rights_or_safety">Direitos, acesso, saúde ou segurança</option></select></label>
            <label>Nível de autonomia<select name="autonomy_level" defaultValue="a0_information"><option value="a0_information">Apenas informa</option><option value="a1_recommendation">Recomenda uma ação</option><option value="a2_prepare_for_approval">Prepara ação para aprovação</option><option value="a3_reversible_actions">Executa ações reversíveis</option><option value="a4_high_impact_actions">Executa ações de alto impacto</option><option value="a5_high_autonomy">Alta autonomia e delegação</option></select></label>
          </div>
        </fieldset>

        <fieldset>
          <legend><span>03</span><div>Dados e tecnologia<small>Informações usadas e forma de hospedagem</small></div></legend>
          <div className="field-grid">
            <label>Classificação mais alta dos dados<select name="data_classification" defaultValue="internal"><option value="public">Públicos</option><option value="internal">Internos</option><option value="confidential">Confidenciais</option><option value="restricted">Restritos</option></select></label>
            <label>Modelo de hospedagem<select name="hosting_model" defaultValue="saas"><option value="saas">Serviço SaaS</option><option value="cloud_managed">Cloud gerenciada</option><option value="self_hosted">Infraestrutura própria</option><option value="hybrid">Híbrida</option></select></label>
          </div>
          <div className="check-grid">
            {checks.map(([name, text]) => (
              <label className="check" key={name}>
                <input name={name} type="checkbox" onChange={name === "international_processing" ? (event) => setInternational(event.target.checked) : undefined} />
                <span>{text}</span>
              </label>
            ))}
          </div>
          {international && <label>Países de inferência, armazenamento, logs ou suporte<input name="inference_countries" required placeholder="Ex.: Estados Unidos, Irlanda" /><small>Separe os países por vírgula.</small></label>}
        </fieldset>

        {error && <div className="notice notice-error">Revise as informações: {error}</div>}
        <div className="form-actions"><Link className="button" href="/">Cancelar</Link><button className="button button-primary" disabled={submitting} type="submit">{submitting ? "Avaliando…" : "Criar e avaliar proposta"}</button></div>
      </form>
    </div>
  );
}
