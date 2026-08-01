import type {
  AgentAsset,
  AISystem,
  Assessment,
  AssessmentKind,
  Evidence,
  EvidenceKind,
  InitiativeControlReport,
  Identity,
  Initiative,
  ModelAsset,
} from "@/lib/types";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const DEMO_REQUESTER: Identity = { userId: "demo.requester" };

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  identity: Identity = DEMO_REQUESTER,
): Promise<T> {
  const headers = new Headers(options.headers);
  if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  headers.set("X-User-Id", identity.userId);
  headers.set("X-User-Areas", identity.areas?.join(",") ?? "");
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    cache: "no-store",
    headers,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: unknown };
    const detail =
      typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail ?? body);
    throw new ApiError(detail, response.status);
  }
  return (await response.json()) as T;
}

export function listInitiatives(): Promise<Initiative[]> {
  return request("/api/v1/initiatives");
}

export function getInitiative(id: string): Promise<Initiative> {
  return request(`/api/v1/initiatives/${id}`);
}

export function createInitiative(payload: Record<string, unknown>): Promise<Initiative> {
  return request("/api/v1/initiatives", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function submitInitiative(id: string, version: number): Promise<Initiative> {
  return request(`/api/v1/initiatives/${id}/submit`, {
    method: "POST",
    body: JSON.stringify({ expected_version: version }),
  });
}

export function listAssessments(initiativeId: string): Promise<Assessment[]> {
  return request(`/api/v1/initiatives/${initiativeId}/assessments`);
}

export function getInitiativeControls(initiativeId: string): Promise<InitiativeControlReport> {
  return request(`/api/v1/initiatives/${initiativeId}/controls`);
}

export function listEvidence(initiativeId: string): Promise<Evidence[]> {
  return request(`/api/v1/initiatives/${initiativeId}/evidence`);
}

export function uploadEvidence(
  initiativeId: string,
  kind: EvidenceKind,
  file: File,
): Promise<Evidence> {
  const body = new FormData();
  body.set("kind", kind);
  body.set("file", file);
  return request(`/api/v1/initiatives/${initiativeId}/evidence`, {
    method: "POST",
    body,
  });
}

export function saveAssessment(
  initiativeId: string,
  kind: AssessmentKind,
  answers: Record<string, unknown>,
  expectedVersion: number | null,
): Promise<Assessment> {
  return request(`/api/v1/initiatives/${initiativeId}/assessments/${kind}`, {
    method: "PUT",
    body: JSON.stringify({ expected_version: expectedVersion, answers }),
  });
}

export function submitAssessment(id: string, version: number): Promise<Assessment> {
  return request(`/api/v1/assessments/${id}/submit`, {
    method: "POST",
    body: JSON.stringify({ expected_version: version }),
  });
}

export function decideApproval(
  initiativeId: string,
  approvalId: string,
  payload: {
    decision: "approved" | "rejected";
    comments: string;
    evidence_uri: string;
    expected_version: number;
  },
  identity: Identity,
): Promise<Initiative> {
  return request(
    `/api/v1/initiatives/${initiativeId}/approvals/${approvalId}/decision`,
    { method: "POST", body: JSON.stringify(payload) },
    identity,
  );
}

export function createAISystem(
  initiativeId: string,
  payload: Record<string, unknown>,
): Promise<AISystem> {
  return request(`/api/v1/initiatives/${initiativeId}/systems`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getAISystem(id: string): Promise<AISystem> {
  return request(`/api/v1/systems/${id}`);
}

export function createModel(
  systemId: string,
  payload: Record<string, unknown>,
): Promise<ModelAsset> {
  return request(`/api/v1/systems/${systemId}/models`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function createAgent(
  systemId: string,
  payload: Record<string, unknown>,
): Promise<AgentAsset> {
  return request(`/api/v1/systems/${systemId}/agents`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function retireAISystem(id: string, version: number): Promise<AISystem> {
  return request(`/api/v1/systems/${id}/retire`, {
    method: "POST",
    body: JSON.stringify({
      expected_version: version,
      reason: "Sistema retirado pelo responsável no portal de governança.",
    }),
  });
}

export function retireModel(id: string, version: number): Promise<ModelAsset> {
  return request(`/api/v1/models/${id}/retire`, {
    method: "POST",
    body: JSON.stringify({
      expected_version: version,
      reason: "Modelo retirado pelo responsável no portal de governança.",
    }),
  });
}

export function retireAgent(id: string, version: number): Promise<AgentAsset> {
  return request(`/api/v1/agents/${id}/retire`, {
    method: "POST",
    body: JSON.stringify({
      expected_version: version,
      reason: "Agente retirado pelo responsável no portal de governança.",
    }),
  });
}
