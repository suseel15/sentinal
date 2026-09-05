-- =========================================================================
-- SENTINEL Financial Crime Investigation Platform — Supabase Schema
-- Phase 15 — Investigator UI
-- =========================================================================
-- This script is idempotent (uses IF NOT EXISTS). Apply with:
--     psql -h <host> -U postgres -d sentinel -f supabase_schema.sql
-- or via the Supabase SQL editor.
-- =========================================================================

-- 1. Investigations (canonical record per case) ---------------------------
CREATE TABLE IF NOT EXISTS investigations (
    investigation_id   TEXT PRIMARY KEY,
    transaction_id     TEXT NOT NULL,
    source_account     TEXT,
    destination_account TEXT,
    amount             NUMERIC,
    channel            TEXT,
    status             TEXT NOT NULL,
    risk_score         REAL,
    risk_level         TEXT,
    confidence_score   REAL,
    confidence_level   TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_investigations_status ON investigations(status);
CREATE INDEX IF NOT EXISTS idx_investigations_risk ON investigations(risk_level, risk_score DESC);
CREATE INDEX IF NOT EXISTS idx_investigations_created ON investigations(created_at DESC);

-- 2. Per-agent sections (A2 detection, A3 evidence, A4 graph, ...) ---------
CREATE TABLE IF NOT EXISTS agent_sections (
    inv_id     TEXT NOT NULL,
    agent      TEXT NOT NULL,
    section    TEXT NOT NULL,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (inv_id, agent, section)
);

-- 3. Evidence items -------------------------------------------------------
CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id          TEXT PRIMARY KEY,
    investigation_id     TEXT NOT NULL,
    type                 TEXT NOT NULL,
    direction            TEXT,                 -- SUPPORTS_RISK | CONTRADICTS_RISK | NEUTRAL
    source_type          TEXT,                 -- INTERNAL_BANK_DATA, EXTERNAL_VERIFIED_SOURCE, ...
    source_reliability   REAL,
    confidence           REAL,
    relevance            REAL,
    corroboration_count  INTEGER DEFAULT 1,
    finding              TEXT,
    summary              TEXT,
    status               TEXT,                 -- AVAILABLE | PARTIAL | UNAVAILABLE
    content_reference    TEXT,
    retrieved_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_evidence_inv ON evidence_items(investigation_id);

-- 4. Graph results --------------------------------------------------------
CREATE TABLE IF NOT EXISTS graph_results (
    inv_id        TEXT PRIMARY KEY,
    analysis_mode TEXT,                         -- FULL | HUB_AWARE | SIZE_FALLBACK
    node_count    INTEGER,
    edge_count    INTEGER,
    avg_degree    REAL,
    community_count INTEGER,
    community_id  TEXT,
    risk_score    REAL,
    nodes         JSONB,
    edges         JSONB,
    patterns      JSONB,
    manual_review_required BOOLEAN DEFAULT FALSE,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 5. Regulatory findings (A5) --------------------------------------------
CREATE TABLE IF NOT EXISTS regulatory_findings (
    id                  BIGSERIAL PRIMARY KEY,
    investigation_id    TEXT NOT NULL,
    framework           TEXT,
    section             TEXT,
    provision           TEXT,
    citation            TEXT,
    relevance           REAL,
    confidence          REAL,
    summary             TEXT,
    human_review_required BOOLEAN DEFAULT TRUE,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_regulatory_inv ON regulatory_findings(investigation_id);

-- 6. Investigation reports (A7) -------------------------------------------
CREATE TABLE IF NOT EXISTS investigation_reports (
    inv_id          TEXT PRIMARY KEY,
    report_payload  JSONB NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 7. Action recommendations (A8) ------------------------------------------
CREATE TABLE IF NOT EXISTS action_recommendations (
    inv_id          TEXT PRIMARY KEY,
    action          TEXT NOT NULL,             -- CLEAR | MONITOR | FURTHER_INVESTIGATION | ESCALATE | ...
    confidence      REAL,
    reasons         JSONB,
    supporting_evidence JSONB,
    human_review_required BOOLEAN DEFAULT TRUE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 8. Human investigator decisions -----------------------------------------
CREATE TABLE IF NOT EXISTS human_decisions (
    inv_id                    TEXT PRIMARY KEY,
    investigator_id           TEXT NOT NULL,
    decision                  TEXT NOT NULL,    -- ACCEPT | OVERRIDE | REQUEST_MORE_EVIDENCE | ESCALATE
    original_recommendation   TEXT,
    justification             TEXT,
    confirmed_outcome         TEXT,
    decided_at                TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_decisions_investigator ON human_decisions(investigator_id);

-- 9. Feedback dataset (continuous learning) -------------------------------
CREATE TABLE IF NOT EXISTS feedback_dataset (
    inv_id              TEXT PRIMARY KEY,
    txn_id              TEXT NOT NULL,
    features            JSONB,
    original_risk       REAL,
    ml_predictions      JSONB,
    rules_triggered     JSONB,
    graph_features      JSONB,
    recommendation      TEXT,
    human_decision      TEXT,
    confirmed_outcome   TEXT,
    stored_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 10. Audit events -------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_events (
    id        BIGSERIAL PRIMARY KEY,
    inv_id    TEXT NOT NULL,
    actor     TEXT NOT NULL,
    event     TEXT NOT NULL,
    payload   JSONB,
    at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_inv ON audit_events(inv_id, at);

-- 11. Live transaction stream (optional mirror) --------------------------
CREATE TABLE IF NOT EXISTS live_transactions (
    id            BIGSERIAL PRIMARY KEY,
    investigation_id TEXT,
    transaction_id TEXT,
    amount        NUMERIC,
    sender        TEXT,
    receiver      TEXT,
    channel       TEXT,
    status        TEXT,
    risk_score    REAL,
    risk_level    TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 12. Model versions registry --------------------------------------------
CREATE TABLE IF NOT EXISTS model_versions (
    model_name     TEXT PRIMARY KEY,
    version        TEXT NOT NULL,
    metrics        JSONB,
    deployed_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Row-Level Security (optional, enable when auth is wired) ---------------
-- ALTER TABLE investigations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY investigator_read ON investigations
--     FOR SELECT USING (auth.jwt() ->> 'role' IN ('ADMIN','INVESTIGATOR','COMPLIANCE_OFFICER','ANALYST'));
-- CREATE POLICY investigator_write ON investigations
--     FOR INSERT WITH CHECK (auth.jwt() ->> 'role' IN ('ADMIN','INVESTIGATOR'));

-- Realtime publication (optional) ----------------------------------------
-- Run in the Supabase SQL editor:
--     ALTER PUBLICATION supabase_realtime ADD TABLE live_transactions,
--                                                investigations,
--                                                agent_sections,
--                                                human_decisions,
--                                                audit_events;