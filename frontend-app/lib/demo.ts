import { InvestigationSummary, InvestigationState, GraphVisualization, EvidenceItem, RegulatoryFinding, Recommendation, AuditEvent } from "@/types/investigation";

/**
 * Demo / fallback data — only used when NEXT_PUBLIC_DEMO_MODE=1 and the
 * FastAPI backend is unreachable. The frontend NEVER invents ML scores or
 * regulatory conclusions; this module just mirrors the schema of the real
 * Phase 7 backend responses so the dashboard renders end-to-end.
 */

const now = () => new Date().toISOString();
const ago = (mins: number) => new Date(Date.now() - mins * 60_000).toISOString();

export const DEMO_INVESTIGATIONS: InvestigationSummary[] = [
  {
    investigation_id: "INV-2026-0042",
    transaction_id: "TXN-0af1c9b1",
    status: "WAITING_FOR_HUMAN",
    risk_score: 87,
    risk_level: "HIGH",
    confidence: 0.91,
    typologies: ["STRUCTURING", "RAPID_MOVEMENT", "POSSIBLE_MULE_ACTIVITY"],
    primary_detection_source: "XGBoost + Rules",
    amount: -4500000,
    sender: "A1 / Acme Logistics Pvt Ltd",
    receiver: "B2 / Helios Trading Co",
    channel: "NEFT",
    created_at: ago(2),
    updated_at: ago(1)
  },
  {
    investigation_id: "INV-2026-0041",
    transaction_id: "TXN-77b2d4e9",
    status: "IN_PROGRESS",
    risk_score: 72,
    risk_level: "MEDIUM",
    confidence: 0.78,
    typologies: ["NEW_BENEFICIARY", "VELOCITY"],
    primary_detection_source: "Isolation Forest",
    amount: -250000,
    sender: "A14 / Orion Pharma",
    receiver: "C9 / Coast Exports",
    channel: "IMPS",
    created_at: ago(14),
    updated_at: ago(3)
  },
  {
    investigation_id: "INV-2026-0040",
    transaction_id: "TXN-1a3e88cc",
    status: "AUTO_CLOSED",
    risk_score: 18,
    risk_level: "LOW",
    confidence: 0.94,
    typologies: [],
    primary_detection_source: "Rules (no trigger)",
    amount: -12500,
    sender: "A3 / Sunita Mehra",
    receiver: "D11 / D-Mart",
    channel: "UPI",
    created_at: ago(40),
    updated_at: ago(38)
  },
  {
    investigation_id: "INV-2026-0039",
    transaction_id: "TXN-f082d2a1",
    status: "ESCALATED",
    risk_score: 96,
    risk_level: "CRITICAL",
    confidence: 0.97,
    typologies: ["MULE_CHAIN", "FAN_OUT", "HIGH_VELOCITY"],
    primary_detection_source: "Graph + Isolation Forest",
    amount: -9800000,
    sender: "A77 / BlueOrbit Capital",
    receiver: "B41 / Northwind Pay",
    channel: "RTGS",
    created_at: ago(90),
    updated_at: ago(15)
  },
  {
    investigation_id: "INV-2026-0038",
    transaction_id: "TXN-5e1ab3cd",
    status: "COMPLETED",
    risk_score: 64,
    risk_level: "MEDIUM",
    confidence: 0.81,
    typologies: ["UNUSUAL_TIME", "NEW_BENEFICIARY"],
    primary_detection_source: "Autoencoder",
    amount: -380000,
    sender: "A22 / Vihaan Industries",
    receiver: "C12 / Sunrise Distributors",
    channel: "NEFT",
    created_at: ago(180),
    updated_at: ago(120)
  },
  {
    investigation_id: "INV-2026-0037",
    transaction_id: "TXN-bf99d1e2",
    status: "WAITING_FOR_HUMAN",
    risk_score: 81,
    risk_level: "HIGH",
    confidence: 0.86,
    typologies: ["STRUCTURING", "SHARED_DEVICE"],
    primary_detection_source: "Rules + Graph",
    amount: -1850000,
    sender: "A61 / Mehta & Sons",
    receiver: "B19 / Kanchan Forex",
    channel: "NEFT",
    created_at: ago(240),
    updated_at: ago(60)
  }
];

export const DEMO_STATE: Record<string, InvestigationState> = Object.fromEntries(
  DEMO_INVESTIGATIONS.map((i) => [
    i.investigation_id,
    {
      investigation_id: i.investigation_id,
      status: i.status,
      created_at: i.created_at,
      updated_at: i.updated_at,
      sections: {
        A1: {
          agent: "A1",
          result: {
            normalized_transaction: {
              transaction_id: i.transaction_id,
              source_account: i.sender,
              target_account: i.receiver,
              amount: i.amount,
              channel: i.channel,
              timestamp: i.created_at
            },
            validation_status: "VALID",
            ingestion_timestamp: i.created_at,
            duplicate: false
          }
        },
        A2: {
          agent: "A2",
          result: {
            risk_score: i.risk_score,
            confidence: i.confidence,
            risk_level: i.risk_level,
            detected_typologies: i.typologies,
            model_outputs: {
              xgboost: ((i.risk_score || 0) / 100) * 0.95 + 0.02,
              isolation_forest: Math.min(0.99, ((i.risk_score || 0) / 100) * 1.05),
              autoencoder: ((i.risk_score || 0) / 100) * 0.9 + 0.05,
              behavioral_deviation: Math.min(0.99, ((i.risk_score || 0) / 100) * 0.95),
              rules_score: (i.risk_score || 0) / 20
            },
            rules_triggered: (i.typologies || []).map((t, idx) => ({
              rule_id: `RULE_${(idx + 1).toString().padStart(3, "0")}_${t}`,
              name: t,
              severity: i.risk_level === "CRITICAL" ? "CRITICAL" : i.risk_level === "HIGH" ? "HIGH" : "MEDIUM",
              description: `Detected pattern: ${t.replace(/_/g, " ").toLowerCase()}`
            })),
            shap: [
              { feature: "Transaction amount deviation", contribution: 0.21 },
              { feature: "Velocity 1h", contribution: 0.18 },
              { feature: "New beneficiary", contribution: 0.15 },
              { feature: "Unusual transaction time", contribution: 0.12 },
              { feature: "Pass-through ratio", contribution: 0.09 }
            ],
            fusion_explanation:
              "Final risk score is the weighted fusion of rules (0.25), XGBoost (0.30), Isolation Forest (0.20), Autoencoder (0.15) and behavioral deviation (0.10)."
          }
        }
      }
    }
  ])
);

export const DEMO_GRAPH: GraphVisualization = {
  investigation_id: "INV-2026-0042",
  nodes: [
    { id: "A1", degree: 4, in_degree: 1, out_degree: 3, volume: 4500000, is_hub: false, type: "ACCOUNT" },
    { id: "B2", degree: 5, in_degree: 2, out_degree: 3, volume: 4400000, is_hub: false, type: "ACCOUNT" },
    { id: "C3", degree: 3, in_degree: 1, out_degree: 2, volume: 2200000, is_hub: false, type: "ACCOUNT" },
    { id: "C4", degree: 2, in_degree: 1, out_degree: 1, volume: 1100000, is_hub: false, type: "ACCOUNT" },
    { id: "C5", degree: 2, in_degree: 1, out_degree: 1, volume: 1100000, is_hub: false, type: "ACCOUNT" },
    { id: "D9", degree: 1, in_degree: 0, out_degree: 1, volume: 0, is_hub: false, type: "DEVICE" },
    { id: "P2", degree: 2, in_degree: 0, out_degree: 2, volume: 0, is_hub: false, type: "PHONE" }
  ],
  edges: [
    { source: "A1", target: "B2", amount: 4500000, timestamp: ago(2), txn_id: "TXN-0af1c9b1", via_hub: false },
    { source: "B2", target: "C3", amount: 2200000, timestamp: ago(1.7), txn_id: "TXN-77b1a", via_hub: false },
    { source: "B2", target: "C4", amount: 1100000, timestamp: ago(1.6), txn_id: "TXN-77b1b", via_hub: false },
    { source: "B2", target: "C5", amount: 1100000, timestamp: ago(1.5), txn_id: "TXN-77b1c", via_hub: false },
    { source: "C3", target: "D9", amount: 0, timestamp: ago(1), txn_id: "META", via_hub: false },
    { source: "C4", target: "D9", amount: 0, timestamp: ago(1), txn_id: "META", via_hub: false },
    { source: "C3", target: "P2", amount: 0, timestamp: ago(1), txn_id: "META", via_hub: false },
    { source: "C5", target: "P2", amount: 0, timestamp: ago(1), txn_id: "META", via_hub: false }
  ],
  analysis_mode: "HUB_AWARE",
  status: "GRAPH_ANALYSIS_COMPLETE"
};

export const DEMO_EVIDENCE: EvidenceItem[] = [
  {
    evidence_id: "EV-001",
    source: "Customer KYC",
    source_type: "INTERNAL",
    entity_id: "A1",
    transaction_id: "TXN-0af1c9b1",
    timestamp: ago(2),
    relevance: 0.92,
    confidence: 0.95,
    content_reference: "kyc://A1/profile.json",
    summary: "KYC profile retrieved. Customer declared turnover ₹2.1 Cr/month.",
    status: "AVAILABLE"
  },
  {
    evidence_id: "EV-002",
    source: "Transaction history",
    source_type: "INTERNAL",
    entity_id: "A1",
    transaction_id: "TXN-0af1c9b1",
    timestamp: ago(2),
    relevance: 0.88,
    confidence: 0.93,
    content_reference: "txn://A1/history.csv",
    summary: "Average transaction amount ₹1.2 L over last 90 days.",
    status: "AVAILABLE"
  },
  {
    evidence_id: "EV-003",
    source: "Shared device",
    source_type: "GRAPH",
    entity_id: "D9",
    transaction_id: "TXN-0af1c9b1",
    timestamp: ago(1),
    relevance: 0.81,
    confidence: 0.84,
    content_reference: "graph://shared-device/D9",
    summary: "Two receiving accounts share the same device identifier D9.",
    status: "AVAILABLE"
  },
  {
    evidence_id: "EV-004",
    source: "Previous alerts",
    source_type: "INTERNAL",
    entity_id: "B2",
    transaction_id: "TXN-0af1c9b1",
    timestamp: ago(1440),
    relevance: 0.74,
    confidence: 0.88,
    content_reference: "alerts://B2/history.json",
    summary: "1 previous alert on counterparty B2 in last 30 days — closed as MONITOR.",
    status: "AVAILABLE"
  },
  {
    evidence_id: "EV-005",
    source: "External sanctions list",
    source_type: "EXTERNAL",
    entity_id: "B2",
    transaction_id: "TXN-0af1c9b1",
    timestamp: ago(2),
    relevance: 0.0,
    confidence: 0.0,
    content_reference: "n/a",
    summary: "External sanctions intelligence not configured.",
    status: "UNAVAILABLE"
  }
];

export const DEMO_REGULATORY: RegulatoryFinding[] = [
  {
    framework: "PMLA 2002",
    section: "Section 12",
    provision: "Obligation of banking companies to furnish information",
    citation: "PMLA / S12 / reporting-obligation",
    relevance: 0.84,
    confidence: 0.9,
    summary: "Suspicious transactions must be reported to the FIU-IND within the prescribed timeline."
  },
  {
    framework: "RBI Master Direction — KYC",
    section: "Chapter IV",
    provision: "Ongoing monitoring of transactions and risk profiling",
    citation: "RBI / DBR / KYC / 2016-17",
    relevance: 0.71,
    confidence: 0.86,
    summary: "Banks are required to exercise ongoing due diligence including monitoring of complex or unusual transactions."
  },
  {
    framework: "FATF Recommendation 20",
    section: "STRs",
    provision: "Reporting of suspicious transactions",
    citation: "FATF / R20 / STR",
    relevance: 0.68,
    confidence: 0.83,
    summary: "Financial institutions should report promptly any suspicious transaction regardless of amount."
  }
];

export const DEMO_RECOMMENDATION: Recommendation = {
  action: "ESCALATE",
  confidence: 0.89,
  reasons: [
    "Final risk score 87/100 (HIGH) with strong corroborating evidence",
    "Three ML layers (XGBoost, Isolation Forest, Autoencoder) agree on suspicious pattern",
    "Shared device identifier between two downstream accounts",
    "Funds were distributed within ~30 minutes (rapid-movement indicator)"
  ],
  supporting_evidence: ["EV-001", "EV-002", "EV-003", "EV-004"],
  human_review_required: true
};

export const DEMO_AUDIT: AuditEvent[] = [
  { actor: "system", event: "TRANSACTION_RECEIVED", at: ago(2) },
  { actor: "A1", event: "AGENT_STARTED", at: ago(2) },
  { actor: "A1", event: "AGENT_COMPLETED", at: ago(2) },
  { actor: "A2", event: "AGENT_STARTED", at: ago(1.9) },
  { actor: "A2", event: "RULE_TRIGGERED", at: ago(1.9) },
  { actor: "A2", event: "MODEL_EXECUTED", at: ago(1.85) },
  { actor: "A2", event: "FUSION_COMPLETED", at: ago(1.8) },
  { actor: "A2", event: "AGENT_COMPLETED", at: ago(1.8) },
  { actor: "A3", event: "AGENT_STARTED", at: ago(1.7) },
  { actor: "A3", event: "EVIDENCE_RETRIEVED", at: ago(1.5) },
  { actor: "A4", event: "GRAPH_ANALYSIS_STARTED", at: ago(1.7) },
  { actor: "A4", event: "GRAPH_ANALYSIS_COMPLETED", at: ago(1.4) },
  { actor: "A5", event: "AGENT_STARTED", at: ago(1.2) },
  { actor: "A5", event: "REPORT_GENERATED", at: ago(1.1) },
  { actor: "A7", event: "REPORT_GENERATED", at: ago(0.9) },
  { actor: "A8", event: "ACTION_RECOMMENDED", at: ago(0.8) },
  { actor: "system", event: "WAITING_FOR_HUMAN", at: ago(0.8) }
];