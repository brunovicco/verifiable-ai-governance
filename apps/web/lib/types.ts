export type ApprovalStatus = "not_required" | "pending" | "approved" | "rejected";

export interface Approval {
  id: string;
  area: string;
  required: boolean;
  reason: string;
  status: ApprovalStatus;
  decided_by: string | null;
  comments: string | null;
  version: number;
}

export interface Initiative {
  id: string;
  name: string;
  description: string;
  business_owner_id: string;
  business_area: string;
  intended_users: string;
  status: string;
  risk_score: number;
  risk_tier: string;
  policy_id: string;
  policy_version: string;
  required_documents: string[];
  version: number;
  created_at: string;
  updated_at: string;
  decision_impact?: string;
  data_classification?: string;
  autonomy_level?: string;
  hosting_model?: string;
  international_processing?: boolean;
  inference_countries?: string[];
  approvals?: Approval[];
}

export interface Identity {
  userId: string;
  areas?: string[];
}
