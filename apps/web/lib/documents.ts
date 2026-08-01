import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";

type FrontmatterValue = boolean | string | string[];

type ManifestEntry = {
  file: string;
  id: string;
  owner?: string;
  scope?: string;
  version?: string;
};

export type DocumentSection = {
  id: string;
  title: string;
};

export type DocumentTemplate = {
  approvalRequired: string[];
  body: string;
  description: string;
  id: string;
  owner: string;
  readingMinutes: number;
  requiresLegalReview: boolean;
  scope: string;
  scopeLabel: string;
  sections: DocumentSection[];
  slug: string;
  status: string;
  title: string;
  version: string;
};

const descriptions: Record<string, string> = {
  "acceptable-ai-use-policy":
    "Diretrizes corporativas para usar IA com segurança, supervisão e responsabilidades claras.",
  "ai-impact-assessment":
    "Avaliação estruturada de impactos, pessoas afetadas, controles e risco residual.",
  "international-processing-assessment":
    "Mapa de localização, transferências, subprocessadores e salvaguardas para dados.",
  "monitoring-plan":
    "Baseline operacional, indicadores, alertas e resposta a eventos de modelos e agentes.",
  "new-ai-proposal":
    "Ponto de partida para registrar finalidade, impacto, dados, fornecedores e operação.",
  ripd: "Relatório de riscos à proteção de dados, medidas, evidências e decisão de Privacidade.",
};

const scopeLabels: Record<string, string> = {
  ai_system: "Sistema de IA",
  corporate: "Corporativo",
  initiative: "Iniciativa",
};

function findTemplatePackage(): string {
  let current = process.cwd();

  for (let level = 0; level < 5; level += 1) {
    const candidate = path.join(current, "packages", "document-templates");
    if (existsSync(candidate)) return candidate;

    const parent = path.dirname(current);
    if (parent === current) break;
    current = parent;
  }

  throw new Error("Pacote packages/document-templates não encontrado.");
}

function cleanScalar(value: string): string {
  const trimmed = value.trim();
  if (
    (trimmed.startsWith('"') && trimmed.endsWith('"')) ||
    (trimmed.startsWith("'") && trimmed.endsWith("'"))
  ) {
    return trimmed.slice(1, -1);
  }
  return trimmed;
}

function parseFrontmatter(source: string): {
  body: string;
  metadata: Record<string, FrontmatterValue>;
} {
  const match = source.match(/^---\r?\n([\s\S]*?)\r?\n---\r?\n?/);
  if (!match) return { body: source.trim(), metadata: {} };

  const metadata: Record<string, FrontmatterValue> = {};
  for (const line of match[1].split(/\r?\n/)) {
    const separator = line.indexOf(":");
    if (separator < 1) continue;

    const key = line.slice(0, separator).trim();
    const rawValue = line.slice(separator + 1).trim();
    if (rawValue === "true" || rawValue === "false") {
      metadata[key] = rawValue === "true";
    } else if (rawValue.startsWith("[") && rawValue.endsWith("]")) {
      metadata[key] = rawValue
        .slice(1, -1)
        .split(",")
        .map(cleanScalar)
        .filter(Boolean);
    } else {
      metadata[key] = cleanScalar(rawValue);
    }
  }

  return { body: source.slice(match[0].length).trim(), metadata };
}

function parseManifest(source: string): ManifestEntry[] {
  const entries: ManifestEntry[] = [];
  let current: Partial<ManifestEntry> | undefined;

  for (const line of source.split(/\r?\n/)) {
    const entryStart = line.match(/^\s*-\s+id:\s*(.+)$/);
    if (entryStart) {
      if (current?.id && current.file) entries.push(current as ManifestEntry);
      current = { id: cleanScalar(entryStart[1]) };
      continue;
    }

    const property = line.match(/^\s+(file|owner|scope|version):\s*(.+)$/);
    if (current && property) {
      current[property[1] as keyof ManifestEntry] = cleanScalar(property[2]);
    }
  }

  if (current?.id && current.file) entries.push(current as ManifestEntry);
  return entries;
}

function withoutTitle(body: string): { content: string; title: string } {
  const lines = body.split(/\r?\n/);
  const titleIndex = lines.findIndex((line) => /^#\s+/.test(line));
  if (titleIndex === -1) return { content: body, title: "Documento sem título" };

  const title = lines[titleIndex].replace(/^#\s+/, "").trim();
  lines.splice(titleIndex, 1);
  return { content: lines.join("\n").trim(), title };
}

function fallbackDescription(body: string): string {
  const paragraph = body
    .split(/\r?\n\s*\r?\n/)
    .map((item) => item.replace(/\r?\n/g, " ").trim())
    .find((item) => item && !/^(#|>|-|\||\d+\.)/.test(item));

  if (!paragraph) return "Template versionado para apoiar o processo de governança de IA.";
  return paragraph.replace(/\*\*/g, "").slice(0, 180);
}

export function slugifyHeading(value: string): string {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/(^-|-$)/g, "");
}

function toStringValue(value: FrontmatterValue | undefined, fallback: string): string {
  return typeof value === "string" && value ? value : fallback;
}

export function getDocumentTemplates(): DocumentTemplate[] {
  const packageRoot = findTemplatePackage();
  const templateRoot = path.join(packageRoot, "templates");
  const manifestPath = path.join(packageRoot, "manifest.yaml");
  const manifest = existsSync(manifestPath)
    ? parseManifest(readFileSync(manifestPath, "utf8"))
    : [];
  const manifestByFile = new Map(manifest.map((entry) => [entry.file, entry]));
  const manifestOrder = new Map(manifest.map((entry, index) => [entry.file, index]));

  const files = readdirSync(templateRoot)
    .filter((file) => file.endsWith(".md"))
    .sort((left, right) => {
      const leftKey = `templates/${left}`;
      const rightKey = `templates/${right}`;
      const leftOrder = manifestOrder.get(leftKey) ?? Number.MAX_SAFE_INTEGER;
      const rightOrder = manifestOrder.get(rightKey) ?? Number.MAX_SAFE_INTEGER;
      return leftOrder - rightOrder || left.localeCompare(right);
    });

  return files.map((file) => {
    const slug = path.basename(file, ".md");
    const source = readFileSync(path.join(templateRoot, file), "utf8");
    const { body: bodyWithTitle, metadata } = parseFrontmatter(source);
    const { content: body, title } = withoutTitle(bodyWithTitle);
    const manifestEntry = manifestByFile.get(`templates/${file}`);
    const scope = manifestEntry?.scope ?? "reference";
    const words = body.match(/\p{L}+/gu)?.length ?? 0;
    const approvalRequired = Array.isArray(metadata.approval_required)
      ? metadata.approval_required
      : [];

    return {
      approvalRequired,
      body,
      description: descriptions[slug] ?? fallbackDescription(body),
      id: toStringValue(metadata.template_id, manifestEntry?.id ?? slug),
      owner: toStringValue(metadata.owner, manifestEntry?.owner ?? "AI Governance"),
      readingMinutes: Math.max(1, Math.ceil(words / 180)),
      requiresLegalReview: metadata.legal_review_required === true,
      scope,
      scopeLabel: scopeLabels[scope] ?? "Referência",
      sections: [...body.matchAll(/^##\s+(.+)$/gm)].map((match) => ({
        id: slugifyHeading(match[1]),
        title: match[1],
      })),
      slug,
      status: toStringValue(metadata.status, "draft"),
      title,
      version: toStringValue(metadata.template_version, manifestEntry?.version ?? "1.0.0"),
    };
  });
}

export function getDocumentTemplate(slug: string): DocumentTemplate | undefined {
  return getDocumentTemplates().find((document) => document.slug === slug);
}
