export type ApprovalStatus =
  | "not_required"
  | "pending"
  | "approved"
  | "rejected"
  | "changes_requested"
  | "superseded";

export type AssessmentKind =
  | "ai-impact-assessment"
  | "ripd"
  | "international-processing-assessment";

export type RiskTier = "low" | "medium" | "high" | "critical";
export type AssetReviewState = "not_reviewed" | "current" | "expired";

export interface Assessment {
  id: string;
  initiative_id: string;
  assessment_type: AssessmentKind;
  schema_version: string;
  status: string;
  answers: Record<string, unknown>;
  risk_score: number;
  risk_tier: RiskTier;
  assessed_by: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface ControlDefinition {
  control_id: string;
  title: string;
  domain: string;
  objective: string;
  control_type: string;
  owner: string;
  review_frequency: string;
  requirements: string[];
  evidence: string[];
  implementation_reference: string | null;
}

export interface ControlEvaluation {
  control: ControlDefinition;
  applicable: boolean;
  reasons: string[];
}

export interface InitiativeControlReport {
  initiative_id: string;
  catalog_id: string;
  catalog_version: string;
  controls: ControlEvaluation[];
}

export type EvidenceKind =
  | "policy"
  | "assessment"
  | "architecture"
  | "security_test"
  | "approval"
  | "other";

export interface Evidence {
  id: string;
  initiative_id: string;
  kind: EvidenceKind;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  sha256: string;
  scan_status: "clean" | "infected";
  scanner: string;
  scanned_at: string;
  supplied_by: string;
  version: number;
  created_at: string;
}

export interface Approval {
  id: string;
  review_submission_id: string | null;
  review_round: number;
  area: string;
  required: boolean;
  reason: string;
  status: ApprovalStatus;
  decided_by: string | null;
  comments: string | null;
  version: number;
}

export interface ModelAsset {
  id: string;
  ai_system_id: string;
  provider: string;
  model_name: string;
  model_version: string;
  deployment_region: string;
  approved_use_cases: string[];
  prohibited_use_cases: string[];
  allowed_data_classes: string[];
  evaluation_baseline: Record<string, unknown>;
  deprecation_date: string | null;
  approved_scope_digest: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  next_review_at: string | null;
  review_reference: string | null;
  review_state: AssetReviewState;
  status: string;
  version: number;
}

export interface AgentAsset {
  id: string;
  ai_system_id: string;
  name: string;
  purpose: string;
  owner_id: string;
  agent_version: string;
  deployment_region: string;
  autonomy_level: string;
  allowed_models: string[];
  tools: string[];
  permissions: string[];
  max_cost: number | null;
  max_runtime_seconds: number | null;
  human_approval_points: string[];
  kill_switch_enabled: boolean;
  approved_scope_digest: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  next_review_at: string | null;
  review_reference: string | null;
  review_state: AssetReviewState;
  status: string;
  version: number;
}

export interface AISystem {
  id: string;
  initiative_id: string;
  name: string;
  purpose: string;
  owner_id: string;
  status: string;
  risk_tier: string;
  production: boolean;
  metadata_json: Record<string, unknown>;
  version: number;
  created_at: string;
  updated_at: string;
  models?: ModelAsset[];
  agents?: AgentAsset[];
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
  current_review_round: number;
  version: number;
  created_at: string;
  updated_at: string;
  decision_impact?: string;
  data_classification?: string;
  autonomy_level?: string;
  hosting_model?: string;
  affects_rights?: boolean;
  executes_actions?: boolean;
  personal_data?: boolean;
  sensitive_data?: boolean;
  children_data?: boolean;
  external_facing?: boolean;
  regulated_context?: boolean;
  international_processing?: boolean;
  inference_countries?: string[];
  uses_rag?: boolean;
  uses_agents?: boolean;
  uses_mcp?: boolean;
  uses_custom_model?: boolean;
  approvals?: Approval[];
  systems?: AISystem[];
}

export interface ReviewSubmission {
  id: string;
  initiative_id: string;
  review_round: number;
  status: string;
  submitted_by: string;
  submitted_at: string;
  resolved_at: string | null;
  revision_summary: string;
  policy_id: string;
  policy_version: string;
  risk_score: number;
  risk_tier: RiskTier;
  approvals: Approval[];
}

export interface Identity {
  userId: string;
  areas?: string[];
}
