import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { MarkdownDocument } from "@/components/MarkdownDocument";
import { getDocumentTemplate, getDocumentTemplates } from "@/lib/documents";

type DocumentPageProps = {
  params: Promise<{ slug: string }>;
};

export const dynamicParams = false;

export function generateStaticParams() {
  return getDocumentTemplates().map((document) => ({ slug: document.slug }));
}

export async function generateMetadata({ params }: DocumentPageProps): Promise<Metadata> {
  const { slug } = await params;
  const document = getDocumentTemplate(slug);
  if (!document) return {};

  return {
    title: `${document.title} | Documentação`,
    description: document.description,
  };
}

function statusLabel(status: string): string {
  return status === "draft" ? "Rascunho" : status;
}

export default async function DocumentPage({ params }: DocumentPageProps) {
  const { slug } = await params;
  const document = getDocumentTemplate(slug);
  if (!document) notFound();

  const relatedDocuments = getDocumentTemplates().filter((item) => item.slug !== document.slug);

  return (
    <div className="page-shell document-page">
      <div className="breadcrumb">
        <Link href="/">Portfólio</Link><span>/</span>
        <Link href="/documentacao">Documentação</Link><span>/</span>
        <span>{document.title}</span>
      </div>

      <header className="document-header">
        <div className="document-kicker">
          <span>{document.scopeLabel}</span>
          <span>Versão {document.version}</span>
          <span>{statusLabel(document.status)}</span>
        </div>
        <h1>{document.title}</h1>
        <p>{document.description}</p>
        <div className="document-facts" aria-label="Metadados do documento">
          <div><span>Responsável</span><strong>{document.owner}</strong></div>
          <div><span>Seções</span><strong>{document.sections.length}</strong></div>
          <div><span>Leitura</span><strong>{document.readingMinutes} min</strong></div>
          <div><span>ID do template</span><strong>{document.id}</strong></div>
        </div>
      </header>

      <div className="document-layout">
        <aside className="document-sidebar">
          <nav aria-label="Sumário do documento">
            <p>NA PÁGINA</p>
            <ol>
              {document.sections.map((section) => (
                <li key={section.id}><a href={`#${section.id}`}>{section.title}</a></li>
              ))}
            </ol>
          </nav>

          {(document.requiresLegalReview || document.approvalRequired.length > 0) && (
            <div className="document-review-note">
              <strong>Revisão necessária</strong>
              {document.requiresLegalReview && <span>Validação de Privacidade/Jurídico</span>}
              {document.approvalRequired.length > 0 && (
                <span>{document.approvalRequired.join(" · ")}</span>
              )}
            </div>
          )}

          <div className="related-documents">
            <p>OUTROS TEMPLATES</p>
            {relatedDocuments.map((item) => (
              <Link href={`/documentacao/${item.slug}`} key={item.slug}>{item.title}</Link>
            ))}
          </div>
        </aside>

        <article className="document-content">
          <div className="template-banner">
            <span aria-hidden>i</span>
            <p>Use este conteúdo como ponto de partida e preserve versão, responsáveis, decisões e evidências.</p>
          </div>
          <MarkdownDocument content={document.body} />
          <footer className="document-end">
            <span>Fim do template</span>
            <Link href="/documentacao">Voltar à biblioteca ↑</Link>
          </footer>
        </article>
      </div>
    </div>
  );
}
