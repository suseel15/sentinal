"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Card, Empty } from "@/components/ui/Primitives";
import { DEMO_INVESTIGATIONS } from "@/lib/demo";
import ClientTime from "@/components/ui/ClientTime";
import { api } from "@/lib/api";

export default function ReportsPage() {
  const [live, setLive] = useState<any[] | null>(null);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const r: any = await api.getReports();
        if (mounted && r && (r.reports || []).length) setLive(r.reports);
      } catch {
        /* demo fallback */
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const demo = !live;
  const rows = live || DEMO_INVESTIGATIONS;

  return (
    <div className="space-y-5">
      <header>
        <div className="text-[12px] uppercase tracking-[1px] text-muted">Reports</div>
        <h1 className="text-2xl font-bold">Investigation Reports</h1>
        <div className="text-muted text-sm mt-1">
          {demo
            ? "Backend unreachable — showing demo cases. High-risk investigations persist here automatically."
            : "Persisted high-risk cases. Open any case to view its 11-section AI investigation report."}
        </div>
      </header>
      <Card title="Available reports">
        {rows.length === 0 ? (
          <Empty message="No persisted high-risk cases yet. Stream or Simulate to create some." />
        ) : (
          <ul className="divide-y divide-border">
            {rows.map((i: any) => (
              <li key={i.investigation_id} className="py-3 flex items-center justify-between">
                <div>
                  <Link href={`/investigations/${i.investigation_id}`} className="font-mono text-accent hover:underline">
                    {i.investigation_id}
                  </Link>
                  <div className="text-[12px] text-muted">
                    {i.status} · risk {i.risk_score ?? "—"}
                    {i.recommendation ? ` · ${i.recommendation}` : ""}
                    {i.report_ready === false ? " · report pending" : ""} ·{" "}
                    <ClientTime value={i.updated || i.created_at} />
                  </div>
                </div>
                <Link href={`/investigations/${i.investigation_id}`} className="btn-secondary">
                  Open report
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
