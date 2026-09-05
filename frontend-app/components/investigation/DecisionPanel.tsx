"use client";
import { useState } from "react";
import { Check, X, MessageSquare, ShieldAlert } from "lucide-react";
import { Card, Empty } from "@/components/ui/Primitives";
import { api } from "@/lib/api";

const ACTIONS = [
  { v: "ACCEPT", label: "Accept Recommendation", icon: Check, color: "btn-ok" },
  { v: "OVERRIDE", label: "Override", icon: X, color: "btn-warn" },
  { v: "REQUEST_MORE_EVIDENCE", label: "Request More Evidence", icon: MessageSquare, color: "btn-secondary" },
  { v: "ESCALATE", label: "Escalate", icon: ShieldAlert, color: "btn-bad" }
];

export default function DecisionPanel({ investigationId, onSubmitted }: { investigationId: string; onSubmitted?: () => void }) {
  const [decision, setDecision] = useState("ACCEPT");
  const [justification, setJustification] = useState("");
  const [outcome, setOutcome] = useState("");
  const [investigator, setInvestigator] = useState("INV-001");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState<any>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setSubmitting(true);
    setErr(null);
    try {
      const r = await api.submitDecision(investigationId, {
        investigator_id: investigator,
        decision,
        justification,
        confirmed_outcome: outcome || undefined
      });
      setSubmitted(r);
      onSubmitted?.();
    } catch (e: any) {
      setErr(e?.message || "Could not submit");
    } finally {
      setSubmitting(false);
    }
  }

  if (submitted) {
    return (
      <Card title="Decision Submitted">
        <div className="text-[12px] text-muted">Investigator feedback has been recorded and forwarded to the continuous learning layer.</div>
        <pre className="mt-3 p-3 rounded bg-[#070b1c] border border-border text-[11px] overflow-auto max-h-56">{JSON.stringify(submitted, null, 2)}</pre>
      </Card>
    );
  }

  return (
    <Card title="Human Investigator Decision">
      <div className="text-[12px] text-muted mb-3">
        The AI provides a recommendation. The human investigator makes the final decision.
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {ACTIONS.map((a) => {
          const Icon = a.icon;
          const active = decision === a.v;
          return (
            <button
              key={a.v}
              onClick={() => setDecision(a.v)}
              className={`${a.color} ${active ? "ring-2 ring-accent" : "opacity-80"}`}
            >
              <Icon size={14} /> {a.label}
            </button>
          );
        })}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4">
        <div>
          <label className="text-[11px] text-muted">Investigator ID</label>
          <input className="input" value={investigator} onChange={(e) => setInvestigator(e.target.value)} />
        </div>
        <div>
          <label className="text-[11px] text-muted">Final outcome (optional, for feedback loop)</label>
          <select className="input" value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="">—</option>
            <option value="TRUE_POSITIVE">True positive</option>
            <option value="FALSE_POSITIVE">False positive</option>
            <option value="NEEDS_MORE_REVIEW">Needs more review</option>
          </select>
        </div>
      </div>

      <div className="mt-3">
        <label className="text-[11px] text-muted">Justification (required for OVERRIDE / ESCALATE)</label>
        <textarea
          className="input"
          rows={3}
          placeholder="Document the reason for your decision."
          value={justification}
          onChange={(e) => setJustification(e.target.value)}
        />
      </div>

      {err && <div className="mt-3 text-bad text-[12px]">{err}</div>}

      <div className="mt-4 flex items-center justify-between">
        <div className="text-[11px] text-muted">
          Decision will be stored in <code>human_decisions</code> and used for continuous learning.
        </div>
        <button className="btn-primary" onClick={submit} disabled={submitting}>
          {submitting ? "Submitting…" : "Submit Decision"}
        </button>
      </div>
    </Card>
  );
}