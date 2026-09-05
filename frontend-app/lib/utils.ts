import { RiskLevel } from "@/types/investigation";

export function riskColor(level?: RiskLevel | string | null): {
  bg: string;
  border: string;
  text: string;
  dot: string;
} {
  switch ((level || "").toUpperCase()) {
    case "CRITICAL":
      return { bg: "bg-[#3a0f1a]", border: "border-bad", text: "text-bad", dot: "bg-bad" };
    case "HIGH":
      return { bg: "bg-[#3a1f12]", border: "border-warn", text: "text-warn", dot: "bg-warn" };
    case "MEDIUM":
    case "MED":
      return { bg: "bg-[#1f2c5c]", border: "border-accent", text: "text-accent", dot: "bg-accent" };
    case "LOW":
    default:
      return { bg: "bg-[#0f3326]", border: "border-ok", text: "text-ok", dot: "bg-ok" };
  }
}

export function fmtNumber(n?: number | null, digits = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (Math.abs(n) >= 1e7) return (n / 1e7).toFixed(2) + " Cr";
  if (Math.abs(n) >= 1e5) return (n / 1e5).toFixed(2) + " L";
  // Fixed locale: server (Node ICU) and browsers must format identically (hydration-safe).
  if (Math.abs(n) >= 1e3) return n.toLocaleString("en-IN", { maximumFractionDigits: digits });
  return n.toFixed(digits);
}

export function fmtCurrency(n?: number | null, currency = "₹"): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `${currency}${fmtNumber(n)}`;
}

export function fmtPct(n?: number | null, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const v = Math.abs(n) <= 1 ? n * 100 : n;
  return `${v.toFixed(digits)}%`;
}

export function fmtDate(s?: string | null): string {
  if (!s) return "—";
  try {
    // Fixed locale + timezone: identical output on server and client (hydration-safe).
    return new Date(s).toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: true,
    });
  } catch {
    return s;
  }
}

export function cx(...parts: (string | false | undefined | null)[]): string {
  return parts.filter(Boolean).join(" ");
}