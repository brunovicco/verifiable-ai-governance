"use client";

import { useEffect, useState } from "react";

import { StatusPill } from "@/components/StatusPill";
import { getControlCatalog, getControlCrosswalk } from "@/lib/api";
import { label } from "@/lib/labels";
import type {
  ControlCatalog,
  ControlCrosswalk,
  ControlDefinition,
  CrosswalkFramework,
  CrosswalkReference,
} from "@/lib/types";

const FRAMEWORK_LABELS: Record<CrosswalkFramework, string> = {
  nist_ai_rmf: "NIST AI RMF",
  nist_ai_600_1: "NIST AI 600-1",
  owasp_llm_top10: "OWASP LLM Top 10",
  owasp_agentic_top10: "OWASP Agentic Top 10",
  mitre_atlas: "MITRE ATLAS",
  iso_iec_42001: "ISO/IEC 42001",
};

function CrosswalkBadges({ references }: { references: CrosswalkReference[] }) {
  if (references.length === 0) {
    return <small>Sem referência mapeada nos frameworks cobertos.</small>;
  }
  return (
    <div className="crosswalk-badges">
      {references.map((reference, index) => (
        <span
          className="crosswalk-badge"
          key={`${reference.framework}-${reference.reference}-${index}`}
          title={reference.note ?? undefined}
        >
          <strong>{FRAMEWORK_LABELS[reference.framework]}</strong>
          {reference.reference}
        </span>
      ))}
    </div>
  );
}

export default function ControlCataloguePage() {
  const [catalog, setCatalog] = useState<ControlCatalog | null>(null);
  const [crosswalk, setCrosswalk] = useState<ControlCrosswalk | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([getControlCatalog(), getControlCrosswalk()])
      .then(([catalogResult, crosswalkResult]) => {
        setCatalog(catalogResult);
        setCrosswalk(crosswalkResult);
      })
      .catch((reason: Error) => setError(reason.message));
  }, []);

  if (error && !catalog) {
    return <div className="page-shell"><div className="notice notice-error">{error}</div></div>;
  }
  if (!catalog || !crosswalk) {
    return <div className="page-shell"><div className="empty">Carregando catálogo de controles…</div></div>;
  }

  const referencesByControl = new Map(
    crosswalk.entries.map((entry) => [entry.control_id, entry.references]),
  );
  const grouped = catalog.controls.reduce<Record<string, ControlDefinition[]>>((result, control) => {
    (result[control.domain] ??= []).push(control);
    return result;
  }, {});

  return (
    <div className="page-shell detail-page">
      <section className="detail-header">
        <div>
          <p className="eyebrow">CONTROL CATALOG · V{catalog.version}</p>
          <h1>Catálogo de controles e crosswalk de apoio</h1>
          <p>{catalog.controls.length} controles baseline em {Object.keys(grouped).length} domínios.</p>
        </div>
      </section>

      <div className="notice">
        {crosswalk.disclaimer}
        {" "}Frameworks cobertos: {crosswalk.frameworks_covered.map((framework) => FRAMEWORK_LABELS[framework]).join(", ")}.
        {" "}Pendente: {crosswalk.frameworks_pending.map((framework) => FRAMEWORK_LABELS[framework]).join(", ")}.
      </div>

      <section className="panel controls-panel">
        <div className="control-groups">
          {Object.entries(grouped).map(([domain, controls]) => (
            <section className="control-group" key={domain}>
              <div className="control-domain-heading">
                <strong>{label(domain)}</strong>
                <span>{controls.length} controles</span>
              </div>
              <div className="control-list">
                {controls.map((control) => (
                  <details className="control-card" key={control.control_id}>
                    <summary>
                      <div>
                        <small>{control.control_id} · {label(control.control_type)}</small>
                        <strong>{control.title}</strong>
                        <span>{control.objective}</span>
                      </div>
                      <StatusPill value={control.control_type} />
                    </summary>
                    <div className="control-details">
                      <dl>
                        <div><dt>Responsável</dt><dd>{control.owner}</dd></div>
                        <div><dt>Revisão</dt><dd>{control.review_frequency}</dd></div>
                      </dl>
                      <strong>Requisitos</strong>
                      <ul>{control.requirements.map((value) => <li key={value}>{value}</li>)}</ul>
                      <strong>Evidências esperadas</strong>
                      <ul>{control.evidence.map((value) => <li key={value}>{value}</li>)}</ul>
                      <strong>Crosswalk de apoio</strong>
                      <CrosswalkBadges references={referencesByControl.get(control.control_id) ?? []} />
                    </div>
                  </details>
                ))}
              </div>
            </section>
          ))}
        </div>
      </section>
    </div>
  );
}
