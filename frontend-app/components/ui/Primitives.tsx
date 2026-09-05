"use client";
import { ReactNode } from "react";
import { cx } from "@/lib/utils";

export function Card({
  title,
  hint,
  children,
  className,
  right
}: {
  title?: string;
  hint?: string;
  children: ReactNode;
  className?: string;
  right?: ReactNode;
}) {
  return (
    <section className={cx("card-glow", className)}>
      {(title || right) && (
        <div className="flex items-center justify-between mb-3">
          {title && <h2 className="section-title">{title}</h2>}
          {right}
        </div>
      )}
      {children}
    </section>
  );
}

export function Kpi({
  label,
  value,
  hint,
  tone = "default"
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: "default" | "ok" | "warn" | "bad" | "accent" | "hi";
}) {
  const tones: Record<string, string> = {
    default: "text-ink",
    ok: "text-ok",
    warn: "text-warn",
    bad: "text-bad",
    accent: "text-accent",
    hi: "text-hi"
  };
  return (
    <div className="card flex flex-col gap-1.5 min-w-[140px]">
      <div className="kpi-label">{label}</div>
      <div className={cx("kpi-value", tones[tone])}>{value}</div>
      {hint && <div className="text-[11px] text-muted">{hint}</div>}
    </div>
  );
}

export function StatusBadge({ status }: { status?: string }) {
  if (!status) return <span className="badge bg-panel2 text-muted">—</span>;
  const s = status.toUpperCase();
  const tone =
    s.includes("FAIL") || s.includes("ESCAL") || s.includes("REQUEST")
      ? "bg-[#4a1d2a] text-[#ffb1c0]"
      : s.includes("PROGRESS") || s.includes("WAIT") || s.includes("PROCESSING") || s.includes("GENERAT")
      ? "bg-[#1f2c5c] text-[#9ec0ff]"
      : s.includes("COMPLETED") || s.includes("READY") || s.includes("AUTO") || s.includes("CLOSED") || s.includes("LOG") || s.includes("DUPLIC")
      ? "bg-[#1d3a30] text-[#7ff0b3]"
      : "bg-[#1c2350] text-ink";
  return <span className={cx("badge", tone)}>{s.replace(/_/g, " ")}</span>;
}

export function RiskDot({ level }: { level?: string }) {
  const u = (level || "").toUpperCase();
  const c =
    u === "CRITICAL" ? "bg-bad" : u === "HIGH" ? "bg-warn" : u === "MEDIUM" || u === "MED" ? "bg-accent" : "bg-ok";
  return <span className={cx("inline-block w-2.5 h-2.5 rounded-full", c)} />;
}

export function ProgressBar({ value, max = 100, tone = "accent" }: { value: number; max?: number; tone?: "accent" | "ok" | "warn" | "bad" }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const colors: Record<string, string> = {
    accent: "from-accent to-hi",
    ok: "from-ok to-[#7ff0b3]",
    warn: "from-warn to-[#ffd47f]",
    bad: "from-bad to-[#ff8aa3]"
  };
  return (
    <div className="w-full h-1.5 rounded-full bg-[#0a1024] overflow-hidden">
      <div
        className={cx("h-full bg-gradient-to-r", colors[tone])}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

export function Empty({ message }: { message: string }) {
  return <div className="text-muted italic p-3 text-center text-sm">{message}</div>;
}

export function Spinner() {
  return (
    <div className="inline-block w-4 h-4 border-2 border-border border-t-accent rounded-full animate-spin" />
  );
}