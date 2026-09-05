export type RiskLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

export type InvestigationStatus =
  | "NEW"
  | "IN_PROGRESS"
  | "A1_COMPLETED"
  | "A2_COMPLETED"
  | "A3_COMPLETED"
  | "A4_COMPLETED"
  | "A5_COMPLETED"
  | "WAITING_FOR_HUMAN"
  | "RECOMMENDATION_READY"
  | "REPORT_GENERATING"
  | "AUTO_CLOSED"
  | "COMPLETED"
  | "ESCALATED"
  | "REQUESTED_MORE_EVIDENCE"
  | "FAILED"
  | "DUPLICATE_LOGGED"
  | "LOG_ONLY";

export interface InvestigationSummary {
  investigation_id: string;
  transaction_id?: string;
  status: InvestigationStatus;
  risk_score?: number | null;
  risk_level?: RiskLevel | null;
  confidence?: number | null;
  typologies?: string[];
  primary_detection_source?: string | null;
  amount?: number | null;
  sender?: string | null;
  receiver?: string | null;
  channel?: string | null;
  created_at?: string;
  updated_at?: string;
}

export interface AgentSection {
  agent: string;
  result: any;
  updated_at?: string;
  // Real backend stores per-agent payloads under their section name,
  // e.g. sections.A2.detection, sections.A3.evidence, sections.A4.graph.
  [key: string]: any;
}

export interface InvestigationState {
  investigation_id: string;
  status: InvestigationStatus;
  sections?: Record<string, AgentSection>;
  human_decision?: HumanDecision | null;
  created_at?: string;
  updated_at?: string;
  // Real backend state fields (see GET /investigations/{id}/state).
  inv_id?: string;
  txn_id?: string;
  risk_score?: number | null;
  risk_level?: string | null;
  payload?: { canonical?: any; [key: string]: any } | null;
}

export interface HumanDecision {
  investigator_id: string;
  decision: "ACCEPT" | "OVERRIDE" | "REQUEST_MORE_EVIDENCE" | "ESCALATE" | string;
  justification?: string | null;
  confirmed_outcome?: string | null;
  submitted_at?: string;
}

export interface DetectionResult {
  risk_score: number;
  confidence: number;
  risk_level: RiskLevel;
  detected_typologies: string[];
  model_outputs: {
    xgboost?: number;
    isolation_forest?: number;
    autoencoder?: number;
    behavioral_deviation?: number;
    rules_score?: number;
    [k: string]: any;
  };
  rules_triggered: { rule_id: string; name?: string; severity?: string; description?: string }[];
  top_explanations?: { feature: string; contribution: number; value?: any }[];
  shap?: { feature: string; contribution: number }[];
}

export interface GraphNode {
  id: string;
  degree?: number;
  in_degree?: number;
  out_degree?: number;
  volume?: number;
  is_hub?: boolean;
  type?: string;
}

export interface GraphEdge {
  source: string;
  target: string;
  amount?: number;
  timestamp?: string;
  txn_id?: string;
  via_hub?: boolean;
}

export interface GraphVisualization {
  investigation_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
  analysis_mode?: "FULL" | "HUB_AWARE" | "SIZE_FALLBACK" | string;
  status?: string;
}

export interface EvidenceItem {
  evidence_id: string;
  source: string;
  source_type: string;
  entity_id?: string;
  transaction_id?: string;
  timestamp?: string;
  relevance?: number;
  confidence?: number;
  content_reference?: string;
  summary?: string;
  status?: "AVAILABLE" | "PARTIAL" | "UNAVAILABLE" | string;
}

export interface RegulatoryFinding {
  framework: string;
  section?: string;
  provision?: string;
  citation?: string;
  relevance?: number;
  confidence?: number;
  summary?: string;
}

export interface Recommendation {
  action: "CLEAR" | "MONITOR" | "FURTHER_INVESTIGATION" | "ESCALATE" | "COMPLIANCE_REVIEW" | "STR_REVIEW";
  confidence: number;
  reasons: string[];
  supporting_evidence: string[];
  human_review_required?: boolean;
}

export interface AuditEvent {
  actor: string;
  event: string;
  at: string;
}