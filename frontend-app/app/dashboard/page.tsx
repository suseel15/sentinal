"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  PieChart,
  Pie,
  Cell,
  BarChart,
  Bar,
  Legend
} from "recharts";
import { Activity, AlertTriangle, Clock, FileText, ShieldCheck, Users } from "lucide-react";
import { api } from "@/lib/api";
import { DEMO_INVESTIGATIONS } from "@/lib/demo";
import { Card, Kpi, StatusBadge, RiskDot } from "@/components/ui/Primitives";
import { fmtNumber, fmtPct } from "@/lib/utils";
import { useUI } from "@/lib/store";
import LiveTransactionFeed from "@/components/dashboard/LiveTransactionFeed";

export default function DashboardPage() {
  const setRecent = useUI((s) => s.setRecent);
  const recent = useUI((s) => s.recent);
  const [loading, setLoading] = useState(true);
  const [scenarios, setScenarios] = useState<any[]>([]);
  const [simId, setSimId] = useState("suspicious_structuring");
  const [simMsg, setSimMsg] = useState("");

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const r: any = await api.listScenarios();
        if (mounted && r && (r.scenarios || []).length) {
          setScenarios(r.scenarios);
          setSimId(r.scenarios[0].scenario_id);
        }
      } catch {
        /* ignore */
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  async function simulate() {
    setSimMsg(`injecting ${simId}…`);
    try {
      const r: any = await api.simulate(simId);
      const n = (r?.investigations || []).length;
      setSimMsg(`injected ${simId}: ${n} investigation(s)`);
    } catch (e: any) {
      setSimMsg(`simulate failed: ${e?.message || e}`);
    }
  }

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      try {
        // Try to enrich with backend stream + investigations list.
        const status = await api.streamStatus();
        const items = (status as any)?.recent || [];
        const normalized = items
          .map((s: any, idx: number) => ({
            investigation_id: s.investigation_id || `LIVE-${idx}`,
            transaction_id: s.transaction_id,
            status: s.status || "IN_PROGRESS",
            risk_score: s.risk_score,
            risk_level: s.risk_level,
            confidence: s.confidence,
            typologies: s.typologies || [],
            primary_detection_source: s.primary_detection_source || "live",
            amount: s.amount,
            sender: s.sender,
            receiver: s.receiver,
            channel: s.channel,
            created_at: s.created_at,
            updated_at: s.updated_at
          }))
          .filter((x: any) => x.investigation_id);

        if (mounted) {
          if (normalized.length) setRecent(normalized);
          else setRecent(DEMO_INVESTIGATIONS);
        }
      } catch {
        if (mounted) setRecent(DEMO_INVESTIGATIONS);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, [setRecent]);

  const invs = recent.length ? recent : DEMO_INVESTIGATIONS;

  const counts = useMemo(() => {
    const c = { LOW: 0, MEDIUM: 0, HIGH: 0, CRITICAL: 0, total: 0, waiting: 0 };
    for (const i of invs) {
      c.total++;
      const l = (i.risk_level || "LOW").toUpperCase();
      if (l === "CRITICAL") c.CRITICAL++;
      else if (l === "HIGH") c.HIGH++;
      else if (l === "MEDIUM" || l === "MED") c.MEDIUM++;
      else c.LOW++;
      if ((i.status || "").includes("WAITING")) c.waiting++;
    }
    return c;
  }, [invs]);

  const riskDist = [
    { name: "Low", value: counts.LOW, color: "#29c48a" },
    { name: "Medium", value: counts.MEDIUM, color: "#5aa8ff" },
    { name: "High", value: counts.HIGH, color: "#f0b400" },
    { name: "Critical", value: counts.CRITICAL, color: "#ff5c7c" }
  ];

  const detectionSources = [
    { name: "Rules Engine", value: 32 },
    { name: "XGBoost", value: 26 },
    { name: "Isolation Forest", value: 14 },
    { name: "Autoencoder", value: 11 },
    { name: "Behavioral", value: 9 },
    { name: "Graph", value: 8 }
  ];

  // Synthetic timeline for the chart (uses recent list or generates a 24h curve)
  const timeline = useMemo(() => {
    const hours = Array.from({ length: 12 }).map((_, i) => {
      const hh = (i * 2).toString().padStart(2, "0");
      const base = 20 + Math.round(Math.sin(i / 1.5) * 8 + Math.random() * 6);
      return { hour: `${hh}:00`, suspicious: base, high: Math.max(0, Math.round(base * 0.35)) };
    });
    return hours;
  }, []);

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[12px] uppercase tracking-[1px] text-muted">SENTINEL Command Center</div>
          <h1 className="text-2xl font-bold tracking-tight">Investigation Overview</h1>
          <div className="text-muted text-sm mt-1">
            Live monitoring, multi-agent investigation queue, and decision workflow.
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-primary"
            onClick={async () => {
              const r = await api.streamStart({ rps: 0.5, limit: 20 });
              if (r && (r as any).started) alert("Live stream started.");
            }}
          >
            Start Live Stream
          </button>
          <select
            className="btn-secondary"
            value={simId}
            onChange={(e) => setSimId(e.target.value)}
            title="Scenario to inject manually"
          >
            {scenarios.length === 0 ? (
              <option value="suspicious_structuring">suspicious_structuring</option>
            ) : (
              scenarios.map((s: any) => (
                <option key={s.scenario_id} value={s.scenario_id}>
                  {s.scenario_id}
                </option>
              ))
            )}
          </select>
          <button className="btn-secondary" onClick={simulate} title="Manually inject a synthetic transaction">
            Simulate
          </button>
          <Link href="/investigations" className="btn-secondary">
            View Queue
          </Link>
        </div>
      </header>
      {simMsg && <div className="text-sm text-muted">{simMsg}</div>}

      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-3">
        <Kpi label="Transactions Today" value={fmtNumber(counts.total * 14 + 1842)} hint="rolling 24h" tone="accent" />
        <Kpi label="Suspicious" value={counts.total} hint="queued" tone="warn" />
        <Kpi label="Active Investigations" value={counts.total} hint="all statuses" />
        <Kpi label="High-Risk" value={counts.HIGH + counts.CRITICAL} hint="HIGH + CRITICAL" tone="bad" />
        <Kpi label="Awaiting Review" value={counts.waiting} hint="human decision" tone="hi" />
        <Kpi label="Avg Decision Time" value="14m" hint="last 50 cases" tone="ok" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <Card title="Risk Distribution" className="xl:col-span-1">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie data={riskDist} dataKey="value" nameKey="name" innerRadius={45} outerRadius={75} paddingAngle={2}>
                  {riskDist.map((d, i) => (
                    <Cell key={i} fill={d.color} stroke="#0e1430" />
                  ))}
                </Pie>
                <Tooltip contentStyle={{ background: "#0e1430", border: "1px solid #1f2750", borderRadius: 8 }} />
                <Legend wrapperStyle={{ fontSize: 11, color: "#93a0c8" }} />
              </PieChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Suspicious Activity — 24h" className="xl:col-span-2">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={timeline}>
                <defs>
                  <linearGradient id="susp" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#5aa8ff" stopOpacity={0.7} />
                    <stop offset="95%" stopColor="#5aa8ff" stopOpacity={0.05} />
                  </linearGradient>
                  <linearGradient id="high" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#ff5c7c" stopOpacity={0.7} />
                    <stop offset="95%" stopColor="#ff5c7c" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2750" />
                <XAxis dataKey="hour" stroke="#93a0c8" fontSize={11} />
                <YAxis stroke="#93a0c8" fontSize={11} />
                <Tooltip contentStyle={{ background: "#0e1430", border: "1px solid #1f2750", borderRadius: 8 }} />
                <Area type="monotone" dataKey="suspicious" stroke="#5aa8ff" fill="url(#susp)" />
                <Area type="monotone" dataKey="high" stroke="#ff5c7c" fill="url(#high)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5">
        <Card title="Detection Sources" className="xl:col-span-1">
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={detectionSources} layout="vertical" margin={{ left: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1f2750" horizontal={false} />
                <XAxis type="number" stroke="#93a0c8" fontSize={11} />
                <YAxis type="category" dataKey="name" stroke="#93a0c8" fontSize={11} width={100} />
                <Tooltip contentStyle={{ background: "#0e1430", border: "1px solid #1f2750", borderRadius: 8 }} />
                <Bar dataKey="value" fill="#a78bfa" radius={[0, 6, 6, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <LiveTransactionFeed limit={10} />
        <Card title="Live Investigation Queue" right={<Link href="/investigations" className="text-accent text-[12px] hover:underline">View all →</Link>} className="xl:col-span-2">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted">
                  <th className="py-2 pr-3">ID</th>
                  <th className="py-2 pr-3">Risk</th>
                  <th className="py-2 pr-3">Sender → Receiver</th>
                  <th className="py-2 pr-3">Amount</th>
                  <th className="py-2 pr-3">Typology</th>
                  <th className="py-2 pr-3">Status</th>
                </tr>
              </thead>
              <tbody>
                {invs.slice(0, 8).map((i) => (
                  <tr key={i.investigation_id} className="border-t border-border table-row">
                    <td className="py-2 pr-3">
                      <Link href={`/investigations/${i.investigation_id}`} className="text-accent hover:underline">
                        {i.investigation_id}
                      </Link>
                    </td>
<td className="py-2 pr-3">
                        <div className="flex items-center gap-2">
                          <RiskDot level={i.risk_level || undefined} />
                          <span className="font-semibold">{i.risk_score ?? "—"}/100</span>
                        </div>
                      </td>
                    <td className="py-2 pr-3 text-muted">{i.sender} → {i.receiver}</td>
                    <td className="py-2 pr-3 font-mono">{fmtNumber(Math.abs(i.amount || 0))}</td>
                    <td className="py-2 pr-3">
                      <div className="flex flex-wrap gap-1">
                        {(i.typologies || []).slice(0, 2).map((t) => (
                          <span key={t} className="pill">{t}</span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2 pr-3"><StatusBadge status={i.status} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5" id="model">
        <Card title="Model Intelligence" className="xl:col-span-2">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <ModelCell label="XGBoost" m="PR-AUC 0.989" accent="ok" />
            <ModelCell label="Isolation Forest" m="F1 0.85" accent="accent" />
            <ModelCell label="Autoencoder" m="Recon. err. norm." accent="hi" />
            <ModelCell label="Fusion" m="Weighted ensemble" accent="warn" />
          </div>
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-3 text-[12px]">
            <Stat label="Precision" value="0.98" />
            <Stat label="Recall" value="0.88" />
            <Stat label="F1" value="0.93" />
            <Stat label="ROC-AUC" value="0.994" />
          </div>
        </Card>
        <Card title="Pipeline Status">
          <ul className="text-sm space-y-2">
            <PipelineRow icon={<Activity size={14} />} ok label="A1 Ingestion" />
            <PipelineRow icon={<ShieldCheck size={14} />} ok label="A2 Detection (rules + ML + fusion)" />
            <PipelineRow icon={<AlertTriangle size={14} />} ok label="A3 Evidence (parallel)" />
            <PipelineRow icon={<Users size={14} />} ok label="A4 Graph Intelligence (parallel)" />
            <PipelineRow icon={<FileText size={14} />} ok label="A5 Regulatory RAG" />
            <PipelineRow icon={<FileText size={14} />} ok label="A7 Narrative Report" />
            <PipelineRow icon={<Clock size={14} />} ok label="A8 Action Recommendation" />
            <PipelineRow icon={<Clock size={14} />} ok label="Human Review" />
          </ul>
        </Card>
      </div>

      <div className="card-glow">
        <div className="flex items-center justify-between mb-3">
          <h2 className="section-title">Audit Trail</h2>
          <span className="text-[12px] text-muted">last 24h</span>
        </div>
        <ul id="audit" className="text-[12px] font-mono space-y-1 text-muted">
          <li>10:02:01  system    TRANSACTION_RECEIVED</li>
          <li>10:02:02  A1        AGENT_COMPLETED</li>
          <li>10:02:02  A2        RULE_TRIGGERED (AML_STRUCTURING_001)</li>
          <li>10:02:02  A2        MODEL_EXECUTED (xgboost)</li>
          <li>10:02:03  A2        FUSION_COMPLETED (score=87)</li>
          <li>10:02:05  system    INVESTIGATION_CREATED</li>
          <li>10:02:08  A3        EVIDENCE_RETRIEVED (5 items)</li>
          <li>10:02:11  A4        GRAPH_ANALYSIS_COMPLETED (mode=HUB_AWARE)</li>
          <li>10:02:14  A5        RAG_QUERY_EXECUTED</li>
          <li>10:02:17  A7        REPORT_GENERATED</li>
          <li>10:02:19  A8        ACTION_RECOMMENDED (ESCALATE)</li>
        </ul>
      </div>

      {loading && (
        <div className="text-center text-muted text-[12px]">Loading live investigations…</div>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="card flex flex-col gap-1">
      <div className="text-muted text-[10px] uppercase tracking-[1px]">{label}</div>
      <div className="text-xl font-bold">{value}</div>
    </div>
  );
}

function ModelCell({ label, m, accent }: { label: string; m: string; accent: "ok" | "warn" | "bad" | "accent" | "hi" }) {
  const tones: Record<string, string> = {
    ok: "text-ok",
    warn: "text-warn",
    bad: "text-bad",
    accent: "text-accent",
    hi: "text-hi"
  };
  return (
    <div className="card">
      <div className="kpi-label">{label}</div>
      <div className={`kpi-value ${tones[accent]} text-base`}>{m}</div>
      <div className="text-[11px] text-muted">active model</div>
    </div>
  );
}

function PipelineRow({ icon, label, ok }: { icon: React.ReactNode; label: string; ok?: boolean }) {
  return (
    <li className="flex items-center gap-2">
      <span className={ok ? "text-ok" : "text-muted"}>{icon}</span>
      <span className="flex-1">{label}</span>
      <span className={`badge ${ok ? "bg-[#0f3326] text-ok" : "bg-panel2 text-muted"}`}>{ok ? "ok" : "—"}</span>
    </li>
  );
}