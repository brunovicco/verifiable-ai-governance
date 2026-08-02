import type {
  AgentAsset,
  AgentKillSwitchState,
  AISystem,
  Assessment,
  AssessmentKind,
  Evidence,
  EvidenceKind,
  Incident,
  InitiativeControlReport,
  Identity,
  Initiative,
  ModelAsset,
  PolicyException,
  ReviewSubmission,
} from "@/lib/types";
import { applyRequestAuthentication } from "@/lib/auth/request";

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
  await applyRequestAuthentication(headers, identity);
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    cache: "no-store",
    credentials: "omit",
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

export function resubmitInitiative(
  id: string,
  payload: Record<string, unknown>,
): Promise<Initiative> {
  return request(`/api/v1/initiatives/${id}/resubmit`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function saveInitiativeRevision(
  id: string,
  payload: Record<string, unknown>,
): Promise<Initiative> {
  return request(`/api/v1/initiatives/${id}/revision`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function listReviewHistory(id: string): Promise<ReviewSubmission[]> {
  return request(`/api/v1/initiatives/${id}/review-history`);
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
    decision: "approved" | "rejected" | "changes_requested";
    comments: string;
    evidence_uri: string;
    expected_version: number;
  },
  identity: Identity = DEMO_REQUESTER,
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

export function reviewModel(
  id: string,
  version: number,
  nextReviewAt: string,
  reference: string,
  identity?: Identity,
): Promise<ModelAsset> {
  return request(
    `/api/v1/models/${id}/review`,
    {
      method: "POST",
      body: JSON.stringify({
        expected_version: version,
        next_review_at: nextReviewAt,
        reference,
      }),
    },
    identity,
  );
}

export function reviewAgent(
  id: string,
  version: number,
  nextReviewAt: string,
  reference: string,
  identity?: Identity,
): Promise<AgentAsset> {
  return request(
    `/api/v1/agents/${id}/review`,
    {
      method: "POST",
      body: JSON.stringify({
        expected_version: version,
        next_review_at: nextReviewAt,
        reference,
      }),
    },
    identity,
  );
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

export function listIncidents(systemId: string): Promise<Incident[]> {
  return request(`/api/v1/systems/${systemId}/incidents`);
}

export function getIncident(incidentId: string): Promise<Incident> {
  return request(`/api/v1/incidents/${incidentId}`);
}

export function reportIncident(
  systemId: string,
  payload: Record<string, unknown>,
): Promise<Incident> {
  return request(`/api/v1/systems/${systemId}/incidents`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function containIncident(
  incidentId: string,
  containment: string,
  expectedVersion: number,
): Promise<Incident> {
  return request(`/api/v1/incidents/${incidentId}/contain`, {
    method: "POST",
    body: JSON.stringify({ containment, expected_version: expectedVersion }),
  });
}

export function setRemediationPlan(
  incidentId: string,
  payload: {
    remediation_owner_id: string;
    remediation_description: string;
    remediation_due_at: string;
    expected_version: number;
  },
): Promise<Incident> {
  return request(`/api/v1/incidents/${incidentId}/remediation-plan`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function closeIncident(incidentId: string, expectedVersion: number): Promise<Incident> {
  return request(`/api/v1/incidents/${incidentId}/close`, {
    method: "POST",
    body: JSON.stringify({ expected_version: expectedVersion }),
  });
}

export function engageKillSwitch(
  incidentId: string,
  agentId: string,
  expectedVersion: number,
): Promise<AgentKillSwitchState> {
  return request(`/api/v1/incidents/${incidentId}/agents/${agentId}/kill-switch/engage`, {
    method: "POST",
    body: JSON.stringify({ expected_version: expectedVersion }),
  });
}

export function restoreKillSwitch(
  incidentId: string,
  agentId: string,
  expectedVersion: number,
): Promise<AgentKillSwitchState> {
  return request(`/api/v1/incidents/${incidentId}/agents/${agentId}/kill-switch/restore`, {
    method: "POST",
    body: JSON.stringify({ expected_version: expectedVersion }),
  });
}

export function listExceptions(incidentId: string): Promise<PolicyException[]> {
  return request(`/api/v1/incidents/${incidentId}/exceptions`);
}

export function requestException(
  incidentId: string,
  payload: {
    purpose: string;
    scope_description: string;
    compensating_controls: string;
    expires_at: string;
  },
): Promise<PolicyException> {
  return request(`/api/v1/incidents/${incidentId}/exceptions`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function decideException(
  exceptionId: string,
  payload: { approved: boolean; decision_reason: string; expected_version: number },
): Promise<PolicyException> {
  return request(`/api/v1/exceptions/${exceptionId}/decide`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function revokeException(
  exceptionId: string,
  payload: { decision_reason: string; expected_version: number },
): Promise<PolicyException> {
  return request(`/api/v1/exceptions/${exceptionId}/revoke`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
