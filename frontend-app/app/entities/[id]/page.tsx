"use client";
import Link from "next/link";
import { useParams } from "next/navigation";
import { Card, Empty } from "@/components/ui/Primitives";
import GraphView from "@/components/graph/GraphView";
import { DEMO_GRAPH } from "@/lib/demo";
import { fmtNumber } from "@/lib/utils";

export default function EntityPage() {
  const params = useParams<{ id: string }>();
  const id = (params?.id as string) || "A1";
  const node = DEMO_GRAPH.nodes.find((n) => n.id === id) || DEMO_GRAPH.nodes[0];

  return (
    <div className="space-y-5">
      <header>
        <button className="text-[12px] text-muted hover:text-accent">← Back</button>
        <h1 className="text-2xl font-bold mt-1">Entity · {node.id}</h1>
        <div className="text-muted text-sm">Account / Customer / Device profile</div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        <Card title="Entity Information">
          <ul className="text-sm space-y-2">
            <li className="flex justify-between"><span className="text-muted">Type</span><span>{node.type || "ACCOUNT"}</span></li>
            <li className="flex justify-between"><span className="text-muted">Risk Score</span><span className="font-mono">{node.is_hub ? "hub-neutral" : "elevated"}</span></li>
            <li className="flex justify-between"><span className="text-muted">Degree</span><span className="font-mono">{node.degree || 0}</span></li>
            <li className="flex justify-between"><span className="text-muted">In-degree</span><span className="font-mono">{node.in_degree || 0}</span></li>
            <li className="flex justify-between"><span className="text-muted">Out-degree</span><span className="font-mono">{node.out_degree || 0}</span></li>
            <li className="flex justify-between"><span className="text-muted">Volume</span><span className="font-mono">₹{fmtNumber(node.volume || 0)}</span></li>
          </ul>
        </Card>
        <Card title="Investigation Story" className="lg:col-span-2">
          <div className="space-y-3 text-sm">
            <section>
              <div className="text-hi text-[11px] uppercase tracking-[1px] font-semibold">What happened?</div>
              <p className="mt-1 text-muted">
                Account {node.id} received {fmtNumber(node.volume || 0)} and distributed ~92% of the funds to three downstream
                accounts within ~35 minutes. This pattern differs significantly from the historical behavior of {node.id}.
              </p>
            </section>
            <section>
              <div className="text-hi text-[11px] uppercase tracking-[1px] font-semibold">Why does it matter?</div>
              <p className="mt-1 text-muted">
                Two downstream accounts share the same device identifier. The receiving account has 1 prior alert (closed as MONITOR).
              </p>
            </section>
            <section>
              <div className="text-hi text-[11px] uppercase tracking-[1px] font-semibold">Network connections</div>
              <p className="mt-1 text-muted">
                {node.id} is connected to {DEMO_GRAPH.nodes.length - 1} other entities in the bounded investigation graph
                (4-hop limit, 2,000-node cap).
              </p>
            </section>
            <section>
              <div className="text-hi text-[11px] uppercase tracking-[1px] font-semibold">Similar history</div>
              <p className="mt-1 text-muted">
                Similar patterns were identified in previous investigations (see <Link href="/dashboard#audit" className="text-accent">audit trail</Link>).
              </p>
            </section>
          </div>
        </Card>
      </div>

      <GraphView data={{ ...DEMO_GRAPH, investigation_id: id }} />
    </div>
  );
}