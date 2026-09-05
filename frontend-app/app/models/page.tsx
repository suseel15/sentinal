"use client";
import { useEffect, useState } from "react";
import { RefreshCcw, FlaskConical } from "lucide-react";
import { api } from "@/lib/api";
import { Card, Kpi, Spinner, Empty } from "@/components/ui/Primitives";
import { fmtPct, fmtDate } from "@/lib/utils";

export default function ModelsPage() {
  const [metrics, setMetrics] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const m: any = await api.getModelEvaluation();
      setMetrics(m);
    } catch (e: any) {
      setError(e?.message || "failed");
    } finally {
      setLoading(false);
    }
  }

  async function refresh() {
    setRunning(true);
    setError(null);
    try {
      const m: any = await api.runModelEvaluation();
      setMetrics(m);
    } catch (e: any) {
      setError(e?.message || "failed");
    } finally {
      setRunning(false);
    }
  }

  useEffect(() => { load(); }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-muted text-sm"><Spinner /> Loading model evaluation…</div>
    );
  }
  if (error || !metrics) {
    return (
      <div className="space-y-3">
        <div className="text-bad">{error || "No data"}</div>
        <button className="btn-primary" onClick={refresh} disabled={running}>
          <RefreshCcw size={14} /> Run evaluation
        </button>
      </div>
    );
  }

  const m = metrics.models || {};
  const dataset = metrics.dataset || {};
  const thr = metrics.threshold_analysis || [];

  const ordered = ["xgboost", "isolation_forest", "rules_engine", "fusion"];
  const present = ordered.filter((k) => m[k] && m[k].precision !== undefined);

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[12px] uppercase tracking-[1px] text-muted">Model Intelligence</div>
          <h1 className="text-2xl font-bold">Detection Engine Evaluation</h1>
          <p className="text-muted text-sm mt-1">
            All metrics computed from the actual dataset via the production
            inference pipeline (chronological 70/15/15 split, newest 15% test).
          </p>
        </div>
        <button className="btn-secondary" onClick={refresh} disabled={running}>
          <RefreshCcw size={14} /> {running ? "Running…" : "Re-run"}
        </button>
      </header>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Kpi label="Dataset rows" value={fmtPct(dataset.rows || 0, 0).replace("%", "")} hint="total" tone="accent" />
        <Kpi label="Fraud / Normal" value={`${dataset.fraud || 0} / ${dataset.normal || 0}`} hint={`imbalance ${dataset.imbalance_ratio}:1`} tone="warn" />
        <Kpi label="Split" value={`${dataset.split?.train}/${dataset.split?.valid}/${dataset.split?.test}`} hint="train/valid/test" />
        <Kpi label="Generated" value={metrics.generated_at ? fmtDate(metrics.generated_at) : "—"} hint="IST" />
      </div>

      <Card title="Model Comparison">
        {present.length === 0 ? (
          <Empty message="Models unavailable — start the backend or run /models/evaluation/run." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted text-[11px] uppercase tracking-[1px]">
                  <th className="py-2 pr-3">Model</th>
                  <th className="py-2 pr-3">Precision</th>
                  <th className="py-2 pr-3">Recall</th>
                  <th className="py-2 pr-3">F1</th>
                  <th className="py-2 pr-3">ROC-AUC</th>
                  <th className="py-2 pr-3">PR-AUC ⭐</th>
                  <th className="py-2 pr-3">Confusion</th>
                </tr>
              </thead>
              <tbody>
                {present.map((k) => (
                  <tr key={k} className="border-t border-border">
                    <td className="py-2 pr-3 font-semibold">{k === "isolation_forest" ? "Isolation Forest" : k === "xgboost" ? "XGBoost" : k === "rules_engine" ? "Rules Engine" : "SENTINEL Fusion"}</td>
                    <td className="py-2 pr-3">{fmtPct((m[k].precision || 0) * 100, 1)}</td>
                    <td className="py-2 pr-3">{fmtPct((m[k].recall || 0) * 100, 1)}</td>
                    <td className="py-2 pr-3">{fmtPct((m[k].f1 || 0) * 100, 1)}</td>
                    <td className="py-2 pr-3">{m[k].roc_auc != null ? Number(m[k].roc_auc).toFixed(3) : "—"}</td>
                    <td className="py-2 pr-3 font-mono text-accent">{m[k].pr_auc != null ? Number(m[k].pr_auc).toFixed(3) : "—"}</td>
                    <td className="py-2 pr-3 font-mono text-[11px] text-muted">
                      TN={m[k].confusion_matrix?.tn} FP={m[k].confusion_matrix?.fp}<br/>
                      FN={m[k].confusion_matrix?.fn} TP={m[k].confusion_matrix?.tp}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {thr.length > 0 && (
        <Card title="Fusion Threshold Analysis">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted text-[11px] uppercase tracking-[1px]">
                  <th className="py-2 pr-3">Threshold</th>
                  <th className="py-2 pr-3">Precision</th>
                  <th className="py-2 pr-3">Recall</th>
                  <th className="py-2 pr-3">F1</th>
                  <th className="py-2 pr-3">False positives</th>
                </tr>
              </thead>
              <tbody>
                {thr.map((row: any) => (
                  <tr key={row.threshold} className="border-t border-border">
                    <td className="py-2 pr-3 font-mono">{row.threshold.toFixed ? row.threshold.toFixed(2) : row.threshold}</td>
                    <td className="py-2 pr-3">{fmtPct((row.precision || 0) * 100, 1)}</td>
                    <td className="py-2 pr-3">{fmtPct((row.recall || 0) * 100, 1)}</td>
                    <td className="py-2 pr-3">{fmtPct((row.f1 || 0) * 100, 1)}</td>
                    <td className="py-2 pr-3">{row.false_positives}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <Card title="Why these metrics?">
        <div className="text-[13px] text-muted space-y-2 leading-relaxed">
          <p><strong className="text-ink">PR-AUC ⭐</strong> is the primary metric for fraud detection because the dataset is heavily imbalanced (typically &lt;5% fraud). Accuracy can be misleading — a "predict-everything-normal" model can score &gt;95% while detecting zero fraud.</p>
          <p><strong className="text-ink">Precision</strong> tells us how many flagged cases are truly suspicious. <strong className="text-ink">Recall</strong> tells us how much real fraud we caught. <strong className="text-ink">F1</strong> balances both.</p>
          <p><strong className="text-ink">ROC-AUC</strong> measures general classifier separation. We include it for completeness but PR-AUC is the recommended metric for imbalanced data.</p>
        </div>
      </Card>
    </div>
  );
}