-- =========================================================================
-- SENTINEL — Missing-tables bootstrap (idempotent)
-- =========================================================================
-- Apply this in the Supabase SQL editor:
--   Dashboard -> SQL -> New query -> paste -> Run
--
-- This script only creates the tables that do NOT already exist in your
-- Supabase project. The tables that Phase 7 already created
-- (investigations, evidence_items, human_decisions, audit_events) are
-- left untouched.
-- =========================================================================

CREATE TABLE IF NOT EXISTS agent_sections(
    inv_id     TEXT NOT NULL,
    agent      TEXT NOT NULL,
    section    TEXT NOT NULL,
    payload    JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (inv_id, agent, section));

CREATE TABLE IF NOT EXISTS graph_results(
    inv_id        TEXT PRIMARY KEY,
    analysis_mode TEXT,
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
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS regulatory_findings(
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
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS idx_regulatory_inv ON regulatory_findings(investigation_id);

CREATE TABLE IF NOT EXISTS investigation_reports(
    inv_id          TEXT PRIMARY KEY,
    report_payload  JSONB NOT NULL,
    generated_at    TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS action_recommendations(
    inv_id          TEXT PRIMARY KEY,
    action          TEXT NOT NULL,
    confidence      REAL,
    reasons         JSONB,
    supporting_evidence JSONB,
    human_review_required BOOLEAN DEFAULT TRUE,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS feedback_dataset(
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
    stored_at           TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS live_transactions(
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
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS model_versions(
    model_name     TEXT PRIMARY KEY,
    version        TEXT NOT NULL,
    metrics        JSONB,
    deployed_at    TIMESTAMPTZ NOT NULL DEFAULT now());

-- Optional: a small RPC that lets the Python app create further
-- tables / run migrations without needing the SQL editor.
CREATE OR REPLACE FUNCTION public.exec_sql(sql text) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  EXECUTE sql;
END;
$$;