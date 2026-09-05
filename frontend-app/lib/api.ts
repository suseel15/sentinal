import {
  InvestigationSummary,
  InvestigationState,
  GraphVisualization,
  DetectionResult,
  EvidenceItem,
  RegulatoryFinding,
  Recommendation,
  AuditEvent
} from "@/types/investigation";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const DEMO_MODE = (process.env.NEXT_PUBLIC_DEMO_MODE || "1") === "1";

export class ApiError extends Error {
  status: number;
  body?: any;
  constructor(message: string, status: number, body?: any) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function safeFetch<T>(path: string, init?: RequestInit & { timeoutMs?: number; strict?: boolean }, fallback?: T): Promise<T> {
  if (!API_URL) {
    return (fallback !== undefined ? fallback : (undefined as unknown)) as T;
  }
  try {
    const ctrl = new AbortController();
    const tid = setTimeout(() => ctrl.abort(), init?.timeoutMs ?? 4000);
    const { timeoutMs: _t, strict: _s, ...fetchInit } = init || {};
    const res = await fetch(`${API_URL}${path}`, {
      ...fetchInit,
      signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
      cache: "no-store"
    });
    clearTimeout(tid);
    if (!res.ok) {
      throw new ApiError(`HTTP ${res.status} on ${path}`, res.status);
    }
    return (await res.json()) as T;
  } catch (err: any) {
    if (init?.strict) throw err instanceof ApiError ? err : new ApiError(String(err?.message || err), 0);
    // Silent fallback to demo data — never crash the UI on transient backend absence.
    if (DEMO_MODE && fallback !== undefined) return fallback;
    if (DEMO_MODE) return undefined as unknown as T;
    // Re-throw with a clearer message only when demo mode is OFF.
    throw new ApiError(
      `Could not reach SENTINEL backend at ${API_URL}. ` +
      `Start it with: uvicorn app.main:app --reload  (from E:\\senfin)`,
      0
    );
  }
}

export { supabaseConfigured } from "./supabase";
export const api = {
  baseUrl: API_URL,
  demoMode: DEMO_MODE,

  async startInvestigation(payload: { transaction_id?: string; sync?: boolean }) {
    return safeFetch(`/investigations/start`, {
      method: "POST",
      body: JSON.stringify(payload), timeoutMs: 180000
    });
  },

  async getInvestigationState(id: string): Promise<InvestigationState | null> {
    return safeFetch<InvestigationState | null>(
      `/investigations/${id}/state`,
      undefined,
      null
    );
  },

  /** Strict variant: throws ApiError (status 404 when the case is not in the DB)
   *  instead of falling back to demo data. Use to detect stale case IDs. */
  async getInvestigationStateStrict(id: string): Promise<InvestigationState> {
    return safeFetch<InvestigationState>(
      `/investigations/${id}/state`,
      { strict: true }
    );
  },

  async getReport(id: string): Promise<any> {
    return safeFetch(`/investigations/${id}/report`, undefined, null);
  },

  async getRecommendation(id: string): Promise<Recommendation | null> {
    return safeFetch<Recommendation | null>(
      `/investigations/${id}/recommendation`,
      undefined,
      null
    );
  },

  async getRegulatory(id: string): Promise<any> {
    return safeFetch(`/investigations/${id}/regulatory`, undefined, null);
  },

  async getAudit(id: string): Promise<{ investigation_id: string; events: AuditEvent[] }> {
    return safeFetch(`/investigations/${id}/audit`, undefined, { investigation_id: id, events: [] });
  },

  async getGraphViz(id: string): Promise<GraphVisualization | null> {
    return safeFetch<GraphVisualization | null>(
      `/investigations/${id}/graph/visualization`,
      undefined,
      null
    );
  },

  async getEvidence(id: string): Promise<{ items?: EvidenceItem[] } | null> {
    return safeFetch(`/evidence/${id}`, undefined, null);
  },

  async submitDecision(
    id: string,
    body: { investigator_id: string; decision: string; justification?: string; confirmed_outcome?: string }
  ) {
    return safeFetch(`/investigations/${id}/human-decision`, {
      method: "POST",
      body: JSON.stringify(body)
    });
  },

  async listInvestigations(status?: string, limit = 100): Promise<InvestigationSummary[]> {
    const q = `?limit=${limit}${status ? `&status=${encodeURIComponent(status)}` : ""}`;
    const r: any = await safeFetch(`/investigations${q}`, undefined, { investigations: [] });
    const items = (r?.investigations || []).map((i: any) => ({
      investigation_id: i.investigation_id,
      transaction_id: i.transaction_id,
      status: i.status,
      risk_score: i.risk_score,
      risk_level: i.risk_level,
      updated_at: i.updated,
    }));
    return items as InvestigationSummary[];
  },

  async streamStart(payload: { rps?: number; limit?: number }) {
    return safeFetch(`/stream/start`, {
      method: "POST",
      body: JSON.stringify({ rps: payload.rps ?? 0.5, limit: payload.limit ?? 20 })
    });
  },

  async streamStatus() {
    return safeFetch(`/stream/status`, undefined, { running: false, recent: [] });
  },

  async llmStatus() {
    return safeFetch(`/llm/status`, undefined, { available: false, model: "", url: "" });
  },

  async health() {
    return safeFetch(`/health`, undefined, { status: "demo" });
  },

  async getEvidenceTimeline(id: string): Promise<EvidenceItem[]> {
    return safeFetch(`/evidence/${id}/timeline`, undefined, []);
  },

  async getSystemHealth() {
    return safeFetch(`/system/full-health`, undefined, {
      overall_status: "DEMO", components: {},
    });
  },

  async getDemoScenarios() {
    return safeFetch(`/demo/scenarios`, undefined, { scenarios: [] });
  },

  async runDemoScenario(scenarioId: string, sync = true) {
    return safeFetch(`/demo/run`, {
      method: "POST",
      body: JSON.stringify({ scenario_id: scenarioId, sync })
    });
  },

  async getModelEvaluation() {
    return safeFetch(`/models/evaluation`, undefined, {
      models: {}, threshold_analysis: []
    });
  },

  async runModelEvaluation() {
    return safeFetch(`/models/evaluation/run`, {
      method: "POST"
    });
  },

  async getReports(limit = 200) {
    return safeFetch(`/reports?limit=${limit}`, undefined, { count: 0, reports: [] });
  },

  async refreshCase(id: string) {
    return safeFetch(`/investigations/${id}/refresh`, {
      method: "POST", timeoutMs: 120000
    });
  },

  async simulate(scenarioId: string) {
    return safeFetch(`/simulate`, {
      method: "POST", body: JSON.stringify({ scenario_id: scenarioId }), timeoutMs: 300000
    });
  },

  async listScenarios() {
    return safeFetch(`/simulate/scenarios`, undefined, { scenarios: [] });
  }
};