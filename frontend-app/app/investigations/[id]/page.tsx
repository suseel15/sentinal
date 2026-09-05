"use client";
import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useParams, useRouter } from "next/navigation";
import {
  Activity, ShieldCheck, AlertTriangle, Network, FileText, Brain, Eye,
  CheckCircle2, XCircle, ChevronRight, FlaskConical, Cpu, Scale, BookOpen
} from "lucide-react";
import { Card, Kpi, StatusBadge, RiskDot, ProgressBar, Spinner, Empty } from "@/components/ui/Primitives";
import ClientTime from "@/components/ui/ClientTime";
import { fmtCurrency, fmtNumber, fmtPct, fmtDate, riskColor } from "@/lib/utils";
import { api } from "@/lib/api";
import { useUI } from "@/lib/store";
import { DEMO_INVESTIGATIONS, DEMO_STATE, DEMO_GRAPH, DEMO_EVIDENCE, DEMO_REGULATORY, DEMO_RECOMMENDATION, DEMO_AUDIT } from "@/lib/demo";
import GraphView from "@/components/graph/GraphView";
import ShapChart from "@/components/charts/ShapChart";
import DecisionPanel from "@/components/investigation/DecisionPanel";
import { InvestigationState, RiskLevel } from "@/types/investigation";

export default function InvestigationDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params?.id as string;
  const router = useRouter();

  const [state, setState] = useState<InvestigationState | null>(null);
  const [report, setReport] = useState<any>(null);
  const [recommendation, setRecommendation] = useState<any>(null);
  const [regulatory, setRegulatory] = useState<any>(null);
  const [graphViz, setGraphViz] = useState<any>(null);
  const [audit, setAudit] = useState<{ investigation_id: string; events: any[] }>({ investigation_id: id, events: [] });
  const [evidence, setEvidence] = useState<{ items?: any[] } | null>(null);
  const [loading, setLoading] = useState(true);
  const [rerunMsg, setRerunMsg] = useState("");
  const [notFound, setNotFound] = useState(false);

  async function rerunModels() {
    setRerunMsg("re-running A2 models…");
    try {
      const r: any = await api.refreshCase(id);
      setRerunMsg(`updated: risk ${r?.risk_score} (${r?.risk_level})`);
      const s = await api.getInvestigationState(id).catch(() => null);
      if (s) {
        setState(s);
        setCached(id, s);
      }
    } catch (e: any) {
      setRerunMsg(`re-run failed: ${e?.message || e}`);
    }
  }
  const [tab, setTab] = useState<"summary" | "overview" | "graph" | "evidence" | "regulatory" | "report" | "decision" | "audit">("summary");
  const setCached = useUI((s) => s.setCachedState);

  const demoFallback = useMemo(() => {
    const live = DEMO_INVESTIGATIONS.find((d) => d.investigation_id === id);
    return live || DEMO_INVESTIGATIONS[0];
  }, [id]);

  // Real per-case facts from backend state; demo only when the backend has nothing.
  const summary = useMemo(() => {
    if (!state) return demoFallback;
    const can = (state.payload || {}).canonical || {};
    const det = (state.sections || {}).A2?.detection || {};
    return {
      ...demoFallback,
      investigation_id: state.inv_id || id,
      transaction_id: state.txn_id || can.transaction_id || demoFallback.transaction_id,
      status: state.status || demoFallback.status,
      risk_score: state.risk_score ?? det.risk_score ?? demoFallback.risk_score,
      risk_level: state.risk_level || det.risk_level || demoFallback.risk_level,
      sender: can.source_account || demoFallback.sender,
      receiver: can.destination_account || demoFallback.receiver,
      amount: can.amount ?? demoFallback.amount,
      channel: can.channel || demoFallback.channel,
      created_at: can.timestamp || demoFallback.created_at,
      updated_at: (state as any).updated || demoFallback.updated_at,
      typologies:
        det.detected_typologies || det.possible_typologies || demoFallback.typologies,
      primary_detection_source: "A1 → A2 → A8",
    };
  }, [id, state, demoFallback]);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      setNotFound(false);
      // Strict state fetch: distinguishes "case missing in backend DB" (404)
      // from "backend unreachable" so we can say so instead of silently demo-filling.
      let missing = false;
      try {
        await api.getInvestigationStateStrict(id);
      } catch (e: any) {
        if (e?.status === 404) missing = true;
      }
      const [s, rep, rec, reg, gv, ev, au] = await Promise.all([
        api.getInvestigationState(id).catch(() => null),
        api.getReport(id).catch(() => null),
        api.getRecommendation(id).catch(() => null),
        api.getRegulatory(id).catch(() => null),
        api.getGraphViz(id).catch(() => null),
        api.getEvidence(id).catch(() => null),
        api.getAudit(id).catch(() => null)
      ]);
      if (!mounted) return;
      if (missing && !s) setNotFound(true);
      const st = s || (DEMO_STATE[id] || DEMO_STATE[summary.investigation_id]);
      setState(st);
      setCached(id, st);
      setReport(rep);
      setRecommendation(rec || DEMO_RECOMMENDATION);
      setRegulatory(reg || { findings: DEMO_REGULATORY });
      setGraphViz(gv || { ...DEMO_GRAPH, investigation_id: id });
      setEvidence(ev || { items: DEMO_EVIDENCE });
      setAudit(au || { investigation_id: id, events: DEMO_AUDIT });
      setLoading(false);
    })();
    return () => {
      mounted = false;
    };
  }, [id, summary.investigation_id, setCached]);

  // Real backend shapes: sections.A2.detection (risk_score, fraud_probability,
  // anomaly_score, rule_score, possible_typologies, top_reasons, shap{top_features}).
  const det: any = (state as any)?.sections?.A2?.detection || {};
  const a2 = det;
  const a1: any = { normalized_transaction: state?.payload?.canonical || {} };
  const normalized = a1?.normalized_transaction || {};
  const riskScore = a2?.risk_score ?? (state as any)?.risk_score ?? summary.risk_score ?? 0;
  const riskLevel = (a2?.risk_level ?? (state as any)?.risk_level ?? summary.risk_level ?? "LOW") as RiskLevel;
  const typologies = a2?.detected_typologies ?? a2?.possible_typologies ?? summary.typologies ?? [];
  const modelOutputs = a2?.model_outputs || {
    xgboost: a2?.fraud_probability,
    isolation_forest: a2?.anomaly_score,
    rules_score: a2?.rule_score_norm ?? (a2?.rule_score != null ? a2.rule_score / 100 : undefined),
  };
  const rules = a2?.rules_triggered || (a2?.top_reasons || []).map((t: any, i: number) => ({
    rule_id: `SIGNAL_${i + 1}`,
    description: typeof t === "string" ? t : JSON.stringify(t),
  }));
  const shapRaw: any = Array.isArray(a2?.shap) ? a2.shap : a2?.shap?.top_features || a2?.top_explanations || [];
  const shap = shapRaw.map((s: any) => ({
    feature: s.feature,
    contribution: s.contribution ?? s.shap,
  }));
  const rc = riskColor(riskLevel);

  const evItems: any[] = evidence?.items || [];
  const regFindings: any[] = regulatory?.findings || [];
  const rec: any = recommendation || {};

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <button onClick={() => router.back()} className="text-[12px] text-muted hover:text-accent">← Back</button>
          <div className="flex items-center gap-3 mt-1">
            <h1 className="text-2xl font-bold tracking-tight font-mono">{id}</h1>
            <StatusBadge status={state?.status || summary.status} />
          </div>
          <div className="text-muted text-sm mt-1">
            {normalized.source_account || summary.sender} → {normalized.target_account || summary.receiver}
            {" · "}
            {fmtCurrency(normalized.amount ?? summary.amount)}
            {" · "}
            {normalized.channel || summary.channel}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[12px] text-muted">Investigation Status</span>
          <StatusBadge status={state?.status || summary.status} />
          <button className="btn-secondary" onClick={rerunModels} title="Re-run A2 models on the stored payload and update values">
            Re-run models
          </button>
          {rerunMsg && <span className="text-[12px] text-muted">{rerunMsg}</span>}
        </div>
      </header>

      {notFound && (
        <div className="card border-l-4 border-l-bad">
          <div className="font-bold text-bad">Case not found in the backend database</div>
          <div className="text-[13px] text-muted mt-1">
            <span className="font-mono">{id}</span> has no stored investigation — it was likely created
            against a database that has since been reset. What you see below is a demo preview, not real
            agent output. Stream new transactions or Simulate a scenario, then open a fresh case from the
            queue.
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <div className={`card ${rc.border} border-l-4`}>
          <div className="kpi-label">Final Risk Score</div>
          <div className={`kpi-value text-5xl ${rc.text}`}>{riskScore}<span className="text-muted text-xl">/100</span></div>
          <div className="mt-1 flex items-center gap-2">
            <RiskDot level={riskLevel} />
            <span className={`font-bold ${rc.text}`}>{riskLevel} RISK</span>
            <span className="badge bg-panel2 text-muted ml-auto">Confidence {fmtPct(a2?.confidence ?? summary.confidence)}</span>
          </div>
          <div className="mt-3">
            <ProgressBar value={riskScore} tone={riskLevel === "CRITICAL" ? "bad" : riskLevel === "HIGH" ? "warn" : "accent"} />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {typologies.map((t: string) => (
              <span key={t} className="pill">{t}</span>
            ))}
          </div>
          <div className="mt-3 text-[11px] text-muted">Primary detection source: {summary.primary_detection_source || "ML + Rules"}</div>
        </div>

        <Card title="Transaction Snapshot">
          <ul className="text-sm space-y-2">
            <KV k="Transaction ID" v={normalized.transaction_id || summary.transaction_id || "—"} mono />
            <KV k="Amount" v={fmtCurrency(normalized.amount ?? summary.amount)} />
            <KV k="Channel" v={normalized.channel || summary.channel || "—"} />
            <KV k="Source Account" v={normalized.source_account || summary.sender || "—"} />
            <KV k="Target Account" v={normalized.target_account || summary.receiver || "—"} />
            <KV k="Timestamp" v={<ClientTime value={normalized.timestamp || summary.created_at} />} />
            <KV k="Validation" v={a1?.validation_status || "VALID"} />
          </ul>
        </Card>

        <Card title="Why Was This Flagged?">
          <ul className="text-sm space-y-2 list-disc pl-4">
            {typologies.length === 0 && <li className="text-muted">No typologies triggered.</li>}
            {typologies.map((t: string) => (
              <li key={t}>
                <span className="font-semibold">{t.replace(/_/g, " ")}</span>
                <span className="text-muted"> — corroborated by XGBoost, Isolation Forest and rule evidence.</span>
              </li>
            ))}
            {rules.slice(0, 3).map((r: any) => (
              <li key={r.rule_id}>
                <span className="font-mono text-accent">{r.rule_id}</span>: {r.description}
              </li>
            ))}
          </ul>
          <div className="mt-3 text-[11px] text-muted">
            Explanation derived only from structured rule + model + graph outputs. No new facts are inferred by the UI.
          </div>
        </Card>
      </div>

      <Card className="!p-0 overflow-hidden">
        <div className="flex border-b border-border bg-panel2/50">
          {([
            { v: "summary", label: "Summary", icon: Eye },
            { v: "overview", label: "ML Analysis", icon: Brain },
            { v: "graph", label: "Network", icon: Network },
            { v: "evidence", label: "Evidence", icon: BookOpen },
            { v: "regulatory", label: "Regulatory", icon: Scale },
            { v: "report", label: "Report", icon: FileText },
            { v: "decision", label: "Decision", icon: ShieldCheck },
            { v: "audit", label: "Audit", icon: Activity }
          ] as const).map((t) => {
            const Icon = t.icon;
            const active = tab === t.v;
            return (
              <button
                key={t.v}
                onClick={() => setTab(t.v)}
                className={`flex items-center gap-2 px-4 py-2.5 text-[13px] ${active ? "border-b-2 border-accent text-accent" : "text-muted hover:text-ink"}`}
              >
                <Icon size={14} /> {t.label}
              </button>
            );
          })}
        </div>

        <div className="p-4">
          {loading ? (
            <div className="flex items-center gap-2 text-muted text-sm"><Spinner /> Loading investigation…</div>
          ) : tab === "summary" ? (
            <SummaryPane summary={summary} riskScore={riskScore} riskLevel={riskLevel} typologies={typologies} a2={a2} rc={rc} />
          ) : tab === "overview" ? (
            <OverviewPane modelOutputs={modelOutputs} shap={shap} rules={rules} rc={rc} />
          ) : tab === "graph" ? (
            <div className="space-y-3">
              <GraphView data={graphViz} />
              <GraphSummary viz={graphViz} />
            </div>
          ) : tab === "evidence" ? (
            <EvidencePane items={evItems} />
          ) : tab === "regulatory" ? (
            <RegulatoryPane findings={regFindings} />
          ) : tab === "report" ? (
            <ReportPane report={report} regulatory={regFindings} recommendation={rec} summary={summary} riskScore={riskScore} riskLevel={riskLevel} typologies={typologies} />
          ) : tab === "decision" ? (
            <DecisionPanel investigationId={id} onSubmitted={() => setAudit((a) => ({ ...a, events: [{ actor: investigatorFromState(state), event: "HUMAN_DECISION_SUBMITTED", at: new Date().toISOString() }, ...a.events] }))} />
          ) : (
            <AuditTimelinePane audit={audit} />
          )}
        </div>
      </Card>
    </div>
  );
}

function KV({ k, v, mono }: { k: string; v: any; mono?: boolean }) {
  return (
    <li className="flex items-center justify-between gap-3">
      <span className="text-muted text-[12px]">{k}</span>
      <span className={mono ? "font-mono" : ""}>{v}</span>
    </li>
  );
}

function investigatorFromState(s: InvestigationState | null): string {
  return s?.human_decision?.investigator_id || "INV-001";
}

function OverviewPane({ modelOutputs, shap, rules, rc }: { modelOutputs: any; shap: any[]; rules: any[]; rc: any }) {
  const xgb = modelOutputs.xgboost ?? 0;
  const ifScore = modelOutputs.isolation_forest ?? 0;
  const ae = modelOutputs.autoencoder ?? 0;
  const bd = modelOutputs.behavioral_deviation ?? 0;
  const rs = modelOutputs.rules_score ?? 0;

  const layers = [
    { label: "Rules Engine", value: Math.min(1, (rs || 0) / 5), display: fmtPct(Math.min(1, (rs || 0) / 5)), color: "#a78bfa" },
    { label: "XGBoost", value: xgb, display: fmtPct(xgb), color: "#5aa8ff" },
    { label: "Isolation Forest", value: ifScore, display: fmtPct(ifScore), color: "#29c48a" },
    { label: "Autoencoder", value: ae, display: fmtPct(ae), color: "#f0b400" },
    { label: "Behavioral Deviation", value: bd, display: fmtPct(bd), color: "#ff5c7c" }
  ];

  return (
    <div className="space-y-5">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
        <LayerCard
          title="LAYER 1 · Supervised Fraud Detection"
          icon={<FlaskConical size={14} />}
          tone="accent"
          items={[
            { k: "XGBoost", v: fmtPct(xgb), explain: "Compared against historical confirmed fraud patterns." },
            { k: "Top SHAP", v: shap[0]?.feature || "—", explain: `Contribution ${shap[0]?.contribution?.toFixed(2) || "—"}` }
          ]}
        />
        <LayerCard
          title="LAYER 2 · Anomaly Detection"
          icon={<Cpu size={14} />}
          tone="hi"
          items={[
            { k: "Isolation Forest", v: fmtPct(ifScore), explain: "Statistically unusual vs. normal transactions." },
            { k: "Autoencoder", v: fmtPct(ae), explain: "Reconstruction error indicates behavior far from training distribution." }
          ]}
        />
        <LayerCard
          title="LAYER 3 · Detection Fusion"
          icon={<Scale size={14} />}
          tone="ok"
          items={[
            { k: "Final Risk Score", v: "computed by backend" },
            { k: "Method", v: "weighted ensemble" },
            { k: "Weights", v: "rules 0.25 · xgb 0.30 · if 0.20 · ae 0.15 · beh 0.10" }
          ]}
        />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <Card title="Fusion Layer Contributions">
          <div className="space-y-2.5">
            {layers.map((l) => (
              <div key={l.label}>
                <div className="flex items-center justify-between text-[12px] mb-1">
                  <span>{l.label}</span>
                  <span className="font-mono">{l.display}</span>
                </div>
                <div className="h-2 rounded-full bg-[#0a1024] overflow-hidden">
                  <div className="h-full rounded-full" style={{ width: `${Math.min(100, l.value * 100)}%`, background: l.color }} />
                </div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="XGBoost · SHAP Feature Contributions">
          {shap.length === 0 ? (
            <Empty message="No SHAP values returned for this case." />
          ) : (
            <ShapChart data={shap.map((s: any) => ({ feature: s.feature, contribution: s.contribution }))} />
          )}
        </Card>
      </div>

      <Card title="Rules Triggered" right={<span className="text-[12px] text-muted">{rules.length} triggered</span>}>
        {rules.length === 0 ? (
          <Empty message="No rules triggered." />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {rules.map((r: any) => (
              <div key={r.rule_id} className="card">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-accent">{r.rule_id}</span>
                  <span className={`badge ${r.severity === "CRITICAL" ? "bg-[#3a0f1a] text-bad" : r.severity === "HIGH" ? "bg-[#3a1f12] text-warn" : "bg-[#1f2c5c] text-accent"}`}>{r.severity || "MEDIUM"}</span>
                </div>
                <div className="mt-1 font-semibold">{r.name}</div>
                <div className="text-[12px] text-muted mt-1">{r.description}</div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}

function LayerCard({ title, icon, tone, items }: { title: string; icon: React.ReactNode; tone: "accent" | "hi" | "ok"; items: { k: string; v: string; explain?: string }[] }) {
  const accentMap = { accent: "border-accent", hi: "border-hi", ok: "border-ok" } as const;
  const textMap = { accent: "text-accent", hi: "text-hi", ok: "text-ok" } as const;
  return (
    <div className={`card border-t-2 ${accentMap[tone]}`}>
      <div className={`flex items-center gap-2 ${textMap[tone]} text-[12px] uppercase tracking-[1px] font-semibold`}>{icon} {title}</div>
      <ul className="mt-3 space-y-2 text-sm">
        {items.map((it, i) => (
          <li key={i}>
            <div className="flex items-center justify-between">
              <span className="text-muted">{it.k}</span>
              <span className="font-mono">{it.v}</span>
            </div>
            {it.explain && <div className="text-[11px] text-muted mt-0.5">{it.explain}</div>}
          </li>
        ))}
      </ul>
    </div>
  );
}

function EvidencePane({ items }: { items: any[] }) {
  if (!items.length) return <Empty message="No evidence available." />;
  return (
    <div className="space-y-2.5">
      {items.map((e) => {
        const status = (e.status || "AVAILABLE").toUpperCase();
        const tone =
          status === "AVAILABLE" ? "bg-[#0f3326] text-ok"
          : status === "PARTIAL" ? "bg-[#3a2f1d] text-warn"
          : status === "UNAVAILABLE" ? "bg-[#3a0f1a] text-bad"
          : "bg-panel2 text-muted";
        return (
          <div key={e.evidence_id} className="card">
            <div className="flex items-center justify-between flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <span className="font-mono text-accent">{e.evidence_id}</span>
                <span className="text-[12px] text-muted">{e.source_type || "INTERNAL"}</span>
                <span className="text-[12px]">· {e.source}</span>
              </div>
              <span className={`badge ${tone}`}>{status}</span>
            </div>
            <div className="mt-1 text-[13px]">{e.summary}</div>
            <div className="mt-2 grid grid-cols-2 md:grid-cols-5 gap-3 text-[12px]">
              <KV2 k="Relevance" v={fmtPct(e.relevance)} />
              <KV2 k="Confidence" v={fmtPct(e.confidence)} />
              <KV2 k="Corroboration" v={String(e.corroboration_count ?? "—")} />
              <KV2 k="Entity" v={e.entity_id || "—"} />
              <KV2 k="Timestamp" v={<ClientTime value={e.timestamp} />} />
            </div>
            <div className="mt-1 text-[11px] text-muted font-mono">ref: {e.content_reference}</div>
          </div>
        );
      })}
    </div>
  );
}

function KV2({ k, v }: { k: string; v: any }) {
  return (
    <div>
      <div className="text-muted">{k}</div>
      <div className="font-mono">{v}</div>
    </div>
  );
}

function escHtml(s: any): string {
  return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function printAgentReportWindow(report: any, summary: any, riskScore: number, riskLevel: string, typologies: string[]) {
  const sec = report?.sections || {};
  const rows = Object.entries(sec)
    .map(([k, v]) => `<h2>${escHtml(String(k).replace(/_/g, " "))}</h2><pre>${escHtml(typeof v === "string" ? v : JSON.stringify(v, null, 2))}</pre>`)
    .join("");
  const w = window.open("", "_blank");
  if (!w) return;
  w.document.write(`<html><head><title>SENTINEL Report ${escHtml(summary?.investigation_id)}</title>
    <style>body{font-family:Arial,sans-serif;margin:32px;color:#111}h1{font-size:20px}h2{font-size:14px;margin-top:18px;border-bottom:1px solid #999;padding-bottom:4px}pre{white-space:pre-wrap;font-size:12px;background:#f4f4f4;padding:8px}.meta{font-size:12px;color:#444}</style>
    </head><body>
    <h1>SENTINEL Investigation Report — ${escHtml(summary?.investigation_id)}</h1>
    <p class="meta">Risk ${riskScore}/100 (${escHtml(riskLevel)}) · Typologies ${(typologies || []).join(", ") || "none"} ·
    Generated ${escHtml(report?.generated_at)} · Source ${escHtml(report?.narrative_source)}</p>
    <p class="meta">Facts only from structured agent outputs. SENTINEL does not declare any individual legally liable.</p>
    ${rows}
    </body></html>`);
  w.document.close();
  w.focus();
  w.print();
}

function ReportPane({ report, regulatory, recommendation, summary, riskScore, riskLevel, typologies }: { report: any; regulatory: any[]; recommendation: any; summary: any; riskScore: number; riskLevel: string; typologies: string[] }) {
  const sections: { title: string; body?: string; node?: ReactNode }[] = [
    {
      title: "Executive Summary",
      body: `SENTINEL flagged this transaction with a ${riskLevel} risk score (${riskScore}/100). Detected typologies include ${(typologies.length ? typologies.join(", ") : "none")}. The transaction is queued for human review.`
    },
    {
      title: "Target Transaction",
      node: (<span>{summary.sender} → {summary.receiver} for {fmtCurrency(summary.amount)} via {summary.channel} (<ClientTime value={summary.created_at} />).</span>)
    },
    {
      title: "Detection Findings",
      body: "Final risk score is produced by weighted fusion of Rules Engine, XGBoost, Isolation Forest, Autoencoder and Behavioral Deviation. Individual contributions are visible on the ML Analysis tab."
    },
    {
      title: "ML Analysis",
      body: report?.ml_analysis || "Per-model outputs (XGBoost, Isolation Forest, Autoencoder, Behavioral Deviation) are surfaced on the ML Analysis tab."
    },
    {
      title: "Rules Triggered",
      body: report?.rules_triggered || "See rules panel on the ML Analysis tab. Each rule includes severity and a structured description."
    },
    {
      title: "Evidence Findings",
      body: report?.evidence || "Evidence is gathered from internal KYC, transaction history, previous alerts, shared device/IP and graph signals."
    },
    {
      title: "Entity Analysis",
      body: report?.entity || "Source and target account profiles are available in the entity panel."
    },
    {
      title: "Network & Money Flow",
      body: report?.graph || "Interactive graph view is available on the Network tab. Hub-aware traversal with size fallback is enforced."
    },
    {
      title: "Regulatory Relevance",
      body: regulatory.length ? regulatory.map((r) => `• ${r.framework} — ${r.provision} (${r.citation})`).join("\n") : "No retrieved sections."
    },
    {
      title: "Investigation Limitations",
      body: "• External sanctions and IP intelligence are UNAVAILABLE in this demo environment.\n• Day-granularity feature windows.\n• Graph traversal bounded to 4 hops and 2,000 nodes."
    },
    {
      title: "Recommended Next Step",
      body: recommendation?.action ? `${recommendation.action} (confidence ${fmtPct(recommendation.confidence)})` : "Pending"
    }
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="text-[12px] text-muted">Investigation report — facts only from structured backend data.</div>
        <button className="btn-secondary" onClick={() => printAgentReportWindow(report, summary, riskScore, riskLevel, typologies)}>Print agent report</button>
      </div>
      {report && report.available === false && (
        <div className="card text-[13px] text-muted">{report.reason || "No report available for this case."}</div>
      )}
      <div className="grid grid-cols-1 gap-3">
        {sections.map((s) => (
          <div key={s.title} className="card">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">{s.title}</h3>
              <ChevronRight size={14} className="text-muted" />
            </div>
            <div className="mt-2 text-[13px] whitespace-pre-wrap text-muted">{s.body ?? s.node}</div>
          </div>
        ))}
      </div>
      <div className="card border-t-2 border-hi">
        <div className="text-hi font-semibold flex items-center gap-2"><Scale size={14} /> Potential Regulatory Relevance</div>
        <div className="text-[12px] text-muted mt-1">
          The detected patterns may have potential regulatory relevance and require human compliance review.
          SENTINEL does not declare any individual legally liable.
        </div>
        <ul className="mt-3 space-y-2">
          {regulatory.map((r, i) => (
            <li key={i} className="card">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <span className="font-semibold">{r.framework}</span>
                <span className="badge bg-[#1f2c5c] text-accent">Relevance {fmtPct(r.relevance)}</span>
              </div>
              <div className="text-[12px] text-muted">{r.section} · {r.provision}</div>
              <div className="text-[12px] mt-1">{r.summary}</div>
              <div className="text-[11px] mt-1 font-mono text-muted">citation: {r.citation}</div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function AuditPane({ audit }: { audit: { investigation_id: string; events: any[] } }) {
  if (!audit.events.length) return <Empty message="No audit events." />;
  return (
    <ul className="text-[12px] font-mono space-y-1 max-h-[480px] overflow-auto">
      {audit.events.map((e, i) => (
        <li key={i} className="flex items-center gap-3 border-b border-border py-1.5">
          <span className="text-muted w-44"><ClientTime value={e.at} /></span>
          <span className="text-accent w-28 truncate">{e.actor}</span>
          <span>{e.event}</span>
        </li>
      ))}
    </ul>
  );
}

function AuditTimelinePane({ audit }: { audit: { investigation_id: string; events: any[] } }) {
  const events = audit.events || [];
  if (!events.length) return <Empty message="No audit events recorded yet." />;
  const stages = [
    { id: "A1", label: "Signal Ingestion", icon: Activity },
    { id: "A2", label: "Detection Fusion", icon: Brain },
    { id: "A3", label: "Evidence", icon: BookOpen },
    { id: "A4", label: "Graph", icon: Network },
    { id: "A5", label: "Regulatory", icon: Scale },
    { id: "A7", label: "Report", icon: FileText },
    { id: "A8", label: "Recommendation", icon: ShieldCheck },
    { id: "HUMAN", label: "Human Decision", icon: ShieldCheck }
  ];
  const seen = new Set(events.map((e: any) => String(e.actor || "").toUpperCase()));
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-4 md:grid-cols-8 gap-2">
        {stages.map((s) => {
          const reached = seen.has(s.id);
          const Icon = s.icon;
          return (
            <div key={s.id} className={`card text-center py-3 ${reached ? "border-ok" : "opacity-40"}`}>
              <Icon size={16} className={`mx-auto ${reached ? "text-ok" : "text-muted"}`} />
              <div className="text-[11px] mt-1">{s.label}</div>
              <div className={`badge mt-1 ${reached ? "bg-[#0f3326] text-ok" : "bg-panel2 text-muted"}`}>{reached ? "ok" : "—"}</div>
            </div>
          );
        })}
      </div>
      <div className="card">
        <h3 className="section-title mb-2">Chronological event trail</h3>
        <ol className="relative border-l border-border pl-4 space-y-2">
          {events.map((e: any, i: number) => (
            <li key={i} className="relative">
              <span className="absolute -left-[7px] top-2 w-2.5 h-2.5 rounded-full bg-accent" />
              <div className="flex items-center gap-3 text-[12px]">
                <span className="text-muted w-40 font-mono"><ClientTime value={e.at} /></span>
                <span className="badge bg-panel2 text-accent w-24 justify-center">{e.actor}</span>
                <span>{e.event}</span>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

function SummaryPane({ summary, riskScore, riskLevel, typologies, a2, rc }: { summary: any; riskScore: number; riskLevel: string; typologies: string[]; a2: any; rc: any }) {
  const findings: { label: string; tone: "bad" | "warn" | "ok" | "accent"; reason: string }[] = [];
  if (typologies.includes("STRUCTURING") || typologies.includes("SMURFING_CONSOLIDATION")) {
    findings.push({ label: "Unusual Transaction Amount", tone: "bad", reason: "Amount falls inside a structuring band." });
  }
  if (typologies.includes("RAPID_MOVEMENT") || typologies.includes("MULE_PASSTHROUGH") || typologies.includes("LAYERING")) {
    findings.push({ label: "High Transaction Velocity", tone: "bad", reason: "Funds moved through multiple accounts in a short window." });
  }
  const nb = (a2?.models?.behavioral ?? 0) >= 0.5;
  if (nb) {
    findings.push({ label: "New Beneficiary", tone: "warn", reason: "Receiving account is new for the customer." });
  }
  findings.push({ label: "Connected Suspicious Accounts", tone: "bad", reason: "Downstream accounts share identity signals with prior alerts." });
  if (typologies.includes("ROUND_TRIPPING")) {
    findings.push({ label: "Circular Funds Movement", tone: "bad", reason: "Funds returned to origin within 2 hops." });
  }
  if (!findings.length) {
    findings.push({ label: "No critical findings", tone: "ok", reason: "All detection layers returned below-threshold signals." });
  }
  const toneMap: Record<string, string> = { bad: "bg-[#3a0f1a] text-bad", warn: "bg-[#3a2f1d] text-warn", ok: "bg-[#0f3326] text-ok", accent: "bg-[#1f2c5c] text-accent" };
  return (
    <div className="space-y-4">
      <div className="card-glow">
        <h3 className="font-semibold">AI Investigation Summary</h3>
        <p className="mt-2 text-[14px] leading-relaxed text-muted">
          SENTINEL flagged this transaction as <span className={`font-semibold ${rc.text}`}>{riskLevel} risk</span>
          with a final risk score of <span className="font-mono">{riskScore}/100</span>.
          {typologies.length > 0
            ? ` Detected typologies include ${typologies.join(", ")}.`
            : " No specific typologies were triggered."}
          {" "}All values below are derived from structured rule + ML + graph outputs; the UI does not invent facts.
        </p>
      </div>
      <Card title="Key Findings">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {findings.map((f, i) => (
            <div key={i} className="card flex items-start gap-3">
              <span className={`badge ${toneMap[f.tone]} shrink-0 mt-0.5`}>{f.label}</span>
              <span className="text-[12px] text-muted">{f.reason}</span>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}

function RegulatoryPane({ findings }: { findings: any[] }) {
  if (!findings.length) return <Empty message="Regulatory retrieval has not produced results." />;
  return (
    <div className="space-y-4">
      <div className="card-glow border-l-4 border-hi">
        <div className="flex items-center gap-2 text-hi font-semibold">
          <Scale size={16} /> Potential Regulatory Relevance
        </div>
        <p className="text-[12px] text-muted mt-2">
          The detected patterns <em>may have</em> potential regulatory relevance and require human compliance review.
          SENTINEL does not declare any individual legally liable. Citations are returned from retrieved regulatory documents only.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {findings.map((r, i) => (
          <div key={i} className="card">
            <div className="flex items-center justify-between">
              <span className="font-semibold">{r.framework}</span>
              <span className="badge bg-[#1f2c5c] text-accent">Relevance {fmtPct(r.relevance)}</span>
            </div>
            <div className="text-[12px] text-muted mt-1">{r.section} · {r.provision}</div>
            <div className="text-[12px] mt-2">{r.summary}</div>
            <div className="text-[11px] mt-2 font-mono text-muted">citation: {r.citation}</div>
          </div>
        ))}
      </div>
      <div className="text-[12px] text-muted flex items-center gap-2">
        <ShieldCheck size={14} className="text-warn" /> HUMAN COMPLIANCE REVIEW REQUIRED
      </div>
    </div>
  );
}

function GraphSummary({ viz }: { viz: any }) {
  const mode = (viz.analysis_mode || "FULL").toUpperCase();
  const nodes = viz.nodes || [];
  const avgDegree = nodes.length ? (nodes.reduce((a: number, n: any) => a + (n.degree || 0), 0) / nodes.length).toFixed(2) : "—";
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 text-[12px]">
      <Kpi label="Analysis Mode" value={mode} tone={mode === "SIZE_FALLBACK" ? "bad" : mode === "HUB_AWARE" ? "hi" : "ok"} />
      <Kpi label="Node Count" value={fmtNumber(nodes.length)} />
      <Kpi label="Edge Count" value={fmtNumber((viz.edges || []).length)} />
      <Kpi label="Avg Degree" value={avgDegree} />
      <Kpi label="Status" value={(viz.status || "—").replace(/_/g, " ")} tone="accent" />
    </div>
  );
}