import type { Metadata } from "next";
import Link from "next/link";

import { getDocumentTemplates } from "@/lib/documents";

export const metadata: Metadata = {
  title: "Documentação | Verifiable AI Governance",
  description: "Templates versionados para documentar a governança de iniciativas e sistemas de IA.",
};

function statusLabel(status: string): string {
  return status === "draft" ? "Rascunho" : status;
}

export default function DocumentationPage() {
  const documents = getDocumentTemplates();
  const scopeCount = new Set(documents.map((document) => document.scope)).size;

  return (
    <div className="page-shell documentation-page">
      <section className="documentation-hero">
        <div>
          <p className="eyebrow">CENTRAL DE DOCUMENTAÇÃO</p>
          <h1>Governança que deixa<br />registro.</h1>
        </div>
        <p>
          Consulte modelos versionados para transformar decisões, riscos e controles em
          documentação consistente. Os arquivos desta biblioteca vêm diretamente do pacote
          <code>document-templates</code>.
        </p>
      </section>

      <section className="documentation-summary" aria-label="Resumo da biblioteca">
        <article><strong>{documents.length}</strong><span>templates disponíveis</span></article>
        <article><strong>{scopeCount}</strong><span>contextos de aplicação</span></article>
        <article><strong>v1.0</strong><span>biblioteca versionada</span></article>
      </section>

      <section className="documentation-catalog" aria-labelledby="catalog-title">
        <div className="catalog-heading">
          <div>
            <p className="eyebrow">BIBLIOTECA</p>
            <h2 id="catalog-title">Documentos e modelos</h2>
          </div>
          <p>Escolha um documento para consultar sua estrutura e orientações.</p>
        </div>

        <div className="document-grid">
          {documents.map((document, index) => (
            <article className="document-card" key={document.slug}>
              <div className="document-card-top">
                <span>{document.scopeLabel}</span>
                <small>{String(index + 1).padStart(2, "0")}</small>
              </div>
              <div>
                <h3><Link href={`/documentacao/${document.slug}`}>{document.title}</Link></h3>
                <p>{document.description}</p>
              </div>
              <dl>
                <div><dt>Responsável</dt><dd>{document.owner}</dd></div>
                <div><dt>Versão</dt><dd>{document.version}</dd></div>
                <div><dt>Status</dt><dd>{statusLabel(document.status)}</dd></div>
              </dl>
              <Link className="document-card-link" href={`/documentacao/${document.slug}`}>
                Consultar documento <span aria-hidden>→</span>
              </Link>
            </article>
          ))}
        </div>
      </section>

      <aside className="documentation-note">
        <strong>Uso responsável</strong>
        <p>
          Estes templates apoiam o processo de governança. Eles não substituem parecer jurídico,
          revisão das áreas responsáveis ou evidências específicas de cada iniciativa.
        </p>
      </aside>
    </div>
  );
}
