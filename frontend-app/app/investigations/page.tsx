"use client";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Search, Filter, RefreshCcw } from "lucide-react";
import { Card, StatusBadge, RiskDot, Empty, Spinner } from "@/components/ui/Primitives";
import { fmtNumber } from "@/lib/utils";
import ClientTime from "@/components/ui/ClientTime";
import { useUI } from "@/lib/store";
import { DEMO_INVESTIGATIONS } from "@/lib/demo";
import { api } from "@/lib/api";
import { RiskLevel } from "@/types/investigation";

export default function InvestigationsPage() {
  const setRecent = useUI((s) => s.setRecent);
  const recent = useUI((s) => s.recent);
  const [q, setQ] = useState("");
  const [risk, setRisk] = useState<"ALL" | RiskLevel>("ALL");
  const [status, setStatus] = useState<string>("ALL");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      setLoading(true);
      try {
        // Persisted investigations first (real risk/status per case),
        // then live stream recent, then demo fallback.
        const persisted = await api.listInvestigations().catch(() => []);
        const s = await api.streamStatus();
        const streamed = ((s as any)?.recent || []).filter(
          (x: any) => x.investigation_id && !persisted.some((p: any) => p.investigation_id === x.investigation_id)
        );
        if (mounted) {
          const all = [...persisted, ...streamed];
          setRecent(all.length ? all : DEMO_INVESTIGATIONS);
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

  const list = recent.length ? recent : DEMO_INVESTIGATIONS;

  const filtered = useMemo(() => {
    return list.filter((i) => {
      if (risk !== "ALL" && (i.risk_level || "").toUpperCase() !== risk) return false;
      if (status !== "ALL" && i.status !== status) return false;
      if (q) {
        const ql = q.toLowerCase();
        const hay = `${i.investigation_id} ${i.transaction_id} ${i.sender} ${i.receiver} ${(i.typologies || []).join(" ")}`.toLowerCase();
        if (!hay.includes(ql)) return false;
      }
      return true;
    });
  }, [list, q, risk, status]);

  return (
    <div className="space-y-5">
      <header className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <div className="text-[12px] uppercase tracking-[1px] text-muted">Phase 14</div>
          <h1 className="text-2xl font-bold">Investigation Queue</h1>
          <div className="text-muted text-sm mt-1">
            All investigations created by the live stream or by investigators.
          </div>
        </div>
        <button
          className="btn-secondary"
          onClick={async () => {
            setLoading(true);
            const persisted = await api.listInvestigations().catch(() => []);
            const s = await api.streamStatus();
            const streamed = ((s as any)?.recent || []).filter(
              (x: any) => x.investigation_id && !persisted.some((p: any) => p.investigation_id === x.investigation_id)
            );
            const all = [...persisted, ...streamed];
            setRecent(all.length ? all : DEMO_INVESTIGATIONS);
            setLoading(false);
          }}
        >
          <RefreshCcw size={14} /> Refresh
        </button>
      </header>

      <Card>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
          <div>
            <label className="text-[11px] text-muted">Search</label>
            <div className="relative">
              <Search size={14} className="absolute left-2 top-1/2 -translate-y-1/2 text-muted" />
              <input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="ID, account, typology…"
                className="input pl-7"
              />
            </div>
          </div>
          <div>
            <label className="text-[11px] text-muted">Risk level</label>
            <select value={risk} onChange={(e) => setRisk(e.target.value as any)} className="input">
              <option value="ALL">All</option>
              <option value="LOW">LOW</option>
              <option value="MEDIUM">MEDIUM</option>
              <option value="HIGH">HIGH</option>
              <option value="CRITICAL">CRITICAL</option>
            </select>
          </div>
          <div>
            <label className="text-[11px] text-muted">Status</label>
            <select value={status} onChange={(e) => setStatus(e.target.value)} className="input">
              <option value="ALL">All</option>
              <option value="NEW">NEW</option>
              <option value="IN_PROGRESS">IN_PROGRESS</option>
              <option value="WAITING_FOR_HUMAN">WAITING_FOR_HUMAN</option>
              <option value="AUTO_CLOSED">AUTO_CLOSED</option>
              <option value="ESCALATED">ESCALATED</option>
              <option value="COMPLETED">COMPLETED</option>
            </select>
          </div>
          <div className="flex items-end">
            <button
              className="btn-secondary w-full"
              onClick={() => {
                setQ("");
                setRisk("ALL");
                setStatus("ALL");
              }}
            >
              <Filter size={14} /> Clear filters
            </button>
          </div>
        </div>
      </Card>

      <Card title={`Investigations (${filtered.length})`}>
        {loading ? (
          <div className="flex items-center gap-2 text-muted text-sm">
            <Spinner /> Loading…
          </div>
        ) : filtered.length === 0 ? (
          <Empty message="No investigations match the filters." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-muted text-[11px] uppercase tracking-[1px]">
                  <th className="py-2 pr-3">ID</th>
                  <th className="py-2 pr-3">Tx ID</th>
                  <th className="py-2 pr-3">Risk</th>
                  <th className="py-2 pr-3">Sender → Receiver</th>
                  <th className="py-2 pr-3">Amount</th>
                  <th className="py-2 pr-3">Channel</th>
                  <th className="py-2 pr-3">Typology</th>
                  <th className="py-2 pr-3">Status</th>
                  <th className="py-2 pr-3">Created</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((i) => (
                  <tr key={i.investigation_id} className="border-t border-border table-row">
                    <td className="py-2 pr-3">
                      <Link href={`/investigations/${i.investigation_id}`} className="text-accent hover:underline font-mono">
                        {i.investigation_id}
                      </Link>
                    </td>
                    <td className="py-2 pr-3 font-mono text-muted">{i.transaction_id}</td>
                    <td className="py-2 pr-3">
                      <div className="flex items-center gap-2">
                        <RiskDot level={i.risk_level || undefined} />
                        <span className="font-semibold">{i.risk_score ?? "—"}</span>
                        <span className="badge bg-panel2 text-muted">{i.risk_level || "—"}</span>
                      </div>
                    </td>
                    <td className="py-2 pr-3">
                      <div className="text-ink">{i.sender}</div>
                      <div className="text-[11px] text-muted">→ {i.receiver}</div>
                    </td>
                    <td className="py-2 pr-3 font-mono">₹{fmtNumber(Math.abs(i.amount || 0))}</td>
                    <td className="py-2 pr-3 text-muted">{i.channel}</td>
                    <td className="py-2 pr-3">
                      <div className="flex flex-wrap gap-1">
                        {(i.typologies || []).slice(0, 2).map((t) => (
                          <span key={t} className="pill">{t}</span>
                        ))}
                      </div>
                    </td>
                    <td className="py-2 pr-3"><StatusBadge status={i.status} /></td>
                    <td className="py-2 pr-3 text-muted"><ClientTime value={i.created_at} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}