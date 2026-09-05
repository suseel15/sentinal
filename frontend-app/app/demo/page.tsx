"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Play, FlaskConical, AlertTriangle, CheckCircle2, RefreshCcw } from "lucide-react";
import { api } from "@/lib/api";
import { Card, Kpi, Spinner, Empty } from "@/components/ui/Primitives";
import { fmtNumber } from "@/lib/utils";

interface Scenario {
  scenario_id: string;
  title: string;
  description: string;
  expected_outcome: any;
}

export default function DemoPage() {
  const [scenarios, setScenarios] = useState<Scenario[]>([]);
  const [running, setRunning] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<any>(null);
  const [health, setHealth] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [s, h] = await Promise.all([api.getDemoScenarios(), api.getSystemHealth()]);
        if (!mounted) return;
        setScenarios(((s as any)?.scenarios) || []);
        setHealth(h);
      } catch {
        if (mounted) {
          setScenarios([]);
          setHealth(null);
        }
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  async function run(id: string) {
    setRunning(id);
    setLastResult(null);
    try {
      const res: any = await api.runDemoScenario(id, true);
      setLastResult({ scenario_id: id, ...res });
    } catch (e: any) {
      setLastResult({ scenario_id: id, error: e?.message || "failed" });
    } finally {
      setRunning(null);
    }
  }

  return (
    <div className="space-y-5">
      <header>
        <div className="text-[12px] uppercase tracking-[1px] text-muted">Phase 16 — Demo Mode</div>
        <h1 className="text-2xl font-bold">SENTINEL Live Demonstration</h1>
        <p className="text-muted text-sm mt-1">
          8 predefined scenarios execute the full A1 → A2 → A3 + A4 → A5 → A7 → A8 pipeline.
          Click a scenario to fire real transactions into the orchestrator.
        </p>
      </header>

      <Card title="System Health" right={<span className="text-[12px] text-muted">{health?.overall_status || "—"}</span>}>
        {!health ? (
          <div className="flex items-center gap-2 text-muted text-sm"><Spinner /> Loading…</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {Object.entries(health.components || {}).map(([k, v]: any) => (
              <div key={k} className="card text-[12px] flex items-center gap-2">
                {v.status === "HEALTHY" ? <CheckCircle2 size={14} className="text-ok" /> :
                 v.status === "DEGRADED" ? <AlertTriangle size={14} className="text-warn" /> :
                 <AlertTriangle size={14} className="text-bad" />}
                <span className="flex-1">{k}</span>
                <span className={`badge ${v.status === "HEALTHY" ? "bg-[#0f3326] text-ok" : v.status === "DEGRADED" ? "bg-[#3a2f1d] text-warn" : "bg-[#3a0f1a] text-bad"}`}>{v.status}</span>
              </div>
            ))}
          </div>
        )}
      </Card>

      <Card title="Available Scenarios">
        {loading ? (
          <div className="flex items-center gap-2 text-muted text-sm"><Spinner /> Loading scenarios…</div>
        ) : scenarios.length === 0 ? (
          <Empty message="Start the backend to load scenarios (uvicorn app.main:app --reload)." />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
            {scenarios.map((s) => (
              <div key={s.scenario_id} className="card flex flex-col">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="font-semibold text-[14px]">{s.title}</h3>
                  <FlaskConical size={14} className="text-accent" />
                </div>
                <p className="text-[12px] text-muted mb-2 flex-1">{s.description}</p>
                <div className="text-[11px] text-muted mb-2">
                  Expected: <span className="badge bg-panel2 text-accent">{s.expected_outcome?.risk_level || "—"}</span>{" "}
                  <span className="badge bg-panel2 text-muted">{s.expected_outcome?.status || "—"}</span>
                </div>
                <button
                  className="btn-primary !py-1.5 mt-auto"
                  disabled={running === s.scenario_id}
                  onClick={() => run(s.scenario_id)}
                >
                  <Play size={12} /> {running === s.scenario_id ? "Running…" : "Run"}
                </button>
              </div>
            ))}
          </div>
        )}
      </Card>

      {lastResult && (
        <Card title={`Last run — ${lastResult.scenario_id}`} right={
          <button className="btn-secondary !py-1" onClick={() => setLastResult(null)}><RefreshCcw size={12} /> Clear</button>
        }>
          {lastResult.error ? (
            <div className="text-bad text-sm">{lastResult.error}</div>
          ) : (
            <div className="space-y-2 text-[13px]">
              <div className="text-muted">
                Scenario: <span className="text-ink">{lastResult.scenario?.title}</span>
              </div>
              <div className="text-muted">
                {lastResult.investigations?.length || 0} investigations created:
              </div>
              <div className="space-y-1.5">
                {(lastResult.investigations || []).map((inv: any, i: number) => (
                  <div key={i} className="card flex items-center justify-between">
                    <div>
                      {inv.investigation_id ? (
                        <Link href={`/investigations/${inv.investigation_id}`} className="text-accent hover:underline font-mono">
                          {inv.investigation_id}
                        </Link>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                      <div className="text-[11px] text-muted">{lastResult.transaction_ids?.[i]}</div>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="badge bg-panel2 text-accent">{inv.risk_level || "—"}</span>
                      <span className="font-semibold">{inv.risk_score ?? "—"}/100</span>
                      <span className="badge bg-panel2 text-muted">{inv.status || "—"}</span>
                    </div>
                  </div>
                ))}
              </div>
              <Link href="/investigations" className="btn-secondary !py-1 inline-flex">
                View all investigations →
              </Link>
            </div>
          )}
        </Card>
      )}
    </div>
  );
}