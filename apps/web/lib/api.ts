import type { Identity, Initiative } from "@/lib/types";

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
  const response = await fetch(`${API_URL}${path}`, {
    ...options,
    cache: "no-store",
    headers: {
      "Content-Type": "application/json",
      "X-User-Id": identity.userId,
      "X-User-Areas": identity.areas?.join(",") ?? "",
      ...options.headers,
    },
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
