"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { Activity, Radio } from "lucide-react";
import { api } from "@/lib/api";
import { RiskDot, Spinner, Empty } from "@/components/ui/Primitives";
import { fmtCurrency } from "@/lib/utils";

interface StreamItem {
  investigation_id?: string;
  transaction_id?: string;
  status?: string;
  risk_score?: number;
  risk_level?: string;
  amount?: number;
  sender?: string;
  receiver?: string;
  channel?: string;
  created_at?: string;
}

export default function LiveTransactionFeed({ limit = 12 }: { limit?: number }) {
  const [items, setItems] = useState<StreamItem[]>([]);
  const [running, setRunning] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    async function poll() {
      try {
        const s: any = await api.streamStatus();
        if (!mounted) return;
        setRunning(Boolean(s?.running));
        const recents = Array.isArray(s?.recent) ? s.recent.slice(0, limit) : [];
        setItems(recents);
      } catch {
        /* fall back silently */
      } finally {
        if (mounted) setLoading(false);
      }
    }
    poll();
    const id = setInterval(poll, 3000);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [limit]);

  async function start() {
    const r: any = await api.streamStart({ rps: 1.0, limit: 30 });
    if (r && (r.started || r.running)) setRunning(true);
  }
  async function stop() {
    // The Phase 7 backend does not expose stop-stream; we just refresh.
    setRunning(false);
  }

  return (
    <div className="card-glow">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Radio size={14} className={running ? "text-ok" : "text-muted"} />
          <h2 className="section-title">Live Transaction Feed</h2>
          {running && <span className="badge bg-[#0f3326] text-ok live-dot">streaming</span>}
        </div>
        <div className="flex items-center gap-2">
          {running ? (
            <button className="btn-secondary !py-1" onClick={stop}>Stop</button>
          ) : (
            <button className="btn-primary !py-1" onClick={start}>Start Stream</button>
          )}
        </div>
      </div>
      {loading ? (
        <div className="flex items-center gap-2 text-muted text-sm"><Spinner /> Loading…</div>
      ) : items.length === 0 ? (
        <Empty message="No live transactions yet. Start the stream to see real-time risk flow." />
      ) : (
        <div className="space-y-1.5 max-h-[420px] overflow-auto">
          {items.map((it, i) => (
            <div key={(it.investigation_id || it.transaction_id || i) + "-" + i} className="flex items-center justify-between text-[13px] border-b border-border py-1.5 hover:bg-panel2 px-2 rounded">
              <div className="flex items-center gap-3 min-w-0">
                <RiskDot level={it.risk_level} />
                <span className="font-mono text-accent truncate w-32">
                  {it.investigation_id ? (
                    <Link href={`/investigations/${it.investigation_id}`}>{it.investigation_id}</Link>
                  ) : (
                    <span>{it.transaction_id || "—"}</span>
                  )}
                </span>
                <span className="text-muted truncate w-56">{it.sender} → {it.receiver}</span>
                <span className="font-mono">{fmtCurrency(it.amount)}</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="badge bg-panel2 text-muted">{it.risk_level || "—"}</span>
                <span className="font-semibold w-12 text-right">{it.risk_score ?? "—"}</span>
                <Activity size={12} className="text-muted" />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}