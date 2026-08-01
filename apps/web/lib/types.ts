export type ApprovalStatus = "not_required" | "pending" | "approved" | "rejected";

export type AssessmentKind =
  | "ai-impact-assessment"
  | "ripd"
  | "international-processing-assessment";

export type RiskTier = "low" | "medium" | "high" | "critical";

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
  status: string;
  version: number;
}

export interface AgentAsset {
  id: string;
  ai_system_id: string;
  name: string;
  purpose: string;
  owner_id: string;
  autonomy_level: string;
  allowed_models: string[];
  tools: string[];
  permissions: string[];
  max_cost: number | null;
  max_runtime_seconds: number | null;
  human_approval_points: string[];
  kill_switch_enabled: boolean;
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
  systems?: AISystem[];
}

export interface Identity {
  userId: string;
  areas?: string[];
}
