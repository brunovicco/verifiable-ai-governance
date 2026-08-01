import { describe, expect, it } from "vitest";

import { getDocumentTemplate, getDocumentTemplates, slugifyHeading } from "./documents";

describe("document template catalog", () => {
  it("loads every Markdown template in manifest order", () => {
    const documents = getDocumentTemplates();

    expect(documents.map((document) => document.slug)).toEqual([
      "acceptable-ai-use-policy",
      "new-ai-proposal",
      "ai-impact-assessment",
      "ripd",
      "international-processing-assessment",
      "monitoring-plan",
    ]);
    expect(documents).toHaveLength(6);
  });

  it("combines manifest and frontmatter metadata without exposing frontmatter", () => {
    const proposal = getDocumentTemplate("new-ai-proposal");
    const international = getDocumentTemplate("international-processing-assessment");

    expect(proposal).toMatchObject({ owner: "Business", scopeLabel: "Iniciativa", version: "1.0.0" });
    expect(proposal?.body).not.toContain("template_id:");
    expect(international?.requiresLegalReview).toBe(true);
  });

  it("creates stable anchors for Portuguese headings", () => {
    expect(slugifyHeading("Decisão e revisão")).toBe("decisao-e-revisao");
  });
});
