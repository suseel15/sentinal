"use client";
import Link from "next/link";
import { Card } from "@/components/ui/Primitives";
import { DEMO_INVESTIGATIONS } from "@/lib/demo";
import { fmtNumber } from "@/lib/utils";
import ClientTime from "@/components/ui/ClientTime";

export default function EntitiesIndexPage() {
  return (
    <div className="space-y-5">
      <header>
        <div className="text-[12px] uppercase tracking-[1px] text-muted">Network</div>
        <h1 className="text-2xl font-bold">Entities</h1>
        <div className="text-muted text-sm mt-1">Drill into accounts, devices, phones and IPs involved in investigations.</div>
      </header>
      <Card title={`Entities (${DEMO_INVESTIGATIONS.length})`}>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {DEMO_INVESTIGATIONS.map((i) => (
            <Link key={i.investigation_id} href={`/entities/${i.investigation_id}`} className="card hover:bg-panel2">
              <div className="flex items-center justify-between">
                <span className="font-mono text-accent">{i.investigation_id}</span>
                <span className="badge bg-panel2 text-muted">{i.risk_level}</span>
              </div>
              <div className="mt-1 text-[13px]">{i.sender} → {i.receiver}</div>
              <div className="text-[12px] text-muted mt-1">{fmtNumber(Math.abs(i.amount || 0))} · <ClientTime value={i.created_at} /></div>
            </Link>
          ))}
        </div>
      </Card>
    </div>
  );
}