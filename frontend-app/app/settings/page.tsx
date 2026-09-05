"use client";
import { useEffect, useState } from "react";
import { Card } from "@/components/ui/Primitives";
import { api, supabaseConfigured } from "@/lib/api";

export default function SettingsPage() {
  const [apiUrl, setApiUrl] = useState(process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000");
  const [llm, setLlm] = useState<{ available: boolean; model: string }>({ available: false, model: "" });
  const [health, setHealth] = useState<{ status: string }>({ status: "—" });

  useEffect(() => {
    api.llmStatus().then((s: any) => setLlm({ available: Boolean(s?.available), model: String(s?.model || "") }));
    api.health().then((h: any) => setHealth({ status: h?.status || "—" }));
  }, []);

  return (
    <div className="space-y-5">
      <header>
        <div className="text-[12px] uppercase tracking-[1px] text-muted">Settings</div>
        <h1 className="text-2xl font-bold">Dashboard Configuration</h1>
      </header>

      <Card title="Backend Connection">
        <ul className="text-sm space-y-2">
          <li className="flex items-center justify-between"><span className="text-muted">API URL</span><span className="font-mono">{apiUrl}</span></li>
          <li className="flex items-center justify-between"><span className="text-muted">Health</span><span className="badge bg-[#0f3326] text-ok">{health.status}</span></li>
          <li className="flex items-center justify-between"><span className="text-muted">Demo mode</span><span>{api.demoMode ? "enabled" : "disabled"}</span></li>
          <li className="flex items-center justify-between"><span className="text-muted">LLM backend</span><span className="badge bg-[#2a1f4a] text-hi">{llm.available ? llm.model : "template"}</span></li>
          <li className="flex items-center justify-between"><span className="text-muted">Supabase Realtime</span><span className="badge bg-panel2 text-muted">{supabaseConfigured ? "configured" : "off"}</span></li>
        </ul>
      </Card>

      <Card title="Human Decision Defaults">
        <p className="text-[12px] text-muted">
          The investigator decision panel uses INVESTIGATOR ID <code>INV-001</code> by default. Override per case on the
          investigation detail page.
        </p>
      </Card>

      <Card title="Privacy & Limits">
        <ul className="text-[12px] text-muted space-y-1 list-disc pl-4">
          <li>Frontend never computes ML scores or runs inference.</li>
          <li>External sanctions, IP and device intelligence are UNAVAILABLE in this demo.</li>
          <li>Graph traversal is bounded (4 hops, 2,000 nodes, 72h window).</li>
          <li>AI recommendations are advisory — humans always decide.</li>
        </ul>
      </Card>
    </div>
  );
}