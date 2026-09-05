"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  AlertTriangle,
  Network,
  Search,
  FileText,
  Brain,
  Shield,
  Settings,
  Activity,
  FlaskConical
} from "lucide-react";
import { cx } from "@/lib/utils";

const NAV = [
  { href: "/dashboard", label: "Overview", icon: LayoutDashboard },
  { href: "/investigations", label: "Investigations", icon: AlertTriangle },
  { href: "/demo", label: "Demo Mode", icon: FlaskConical },
  { href: "/entities", label: "Network", icon: Network, soon: true },
  { href: "/reports", label: "Reports", icon: FileText, soon: true },
  { href: "/models", label: "Model Intel", icon: Brain },
  { href: "/settings", label: "Settings", icon: Settings }
];

export default function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="w-60 shrink-0 border-r border-border bg-panel/60 min-h-screen flex flex-col">
      <div className="px-5 py-4 border-b border-border flex items-center gap-2">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-accent to-hi grid place-items-center font-bold text-[#06122a]">
          S
        </div>
        <div>
          <div className="font-bold tracking-wide">SENTINEL</div>
          <div className="text-[10px] uppercase tracking-[1px] text-muted">Command Center</div>
        </div>
      </div>
      <nav className="flex-1 p-2 space-y-0.5">
        {NAV.map((item) => {
          const Icon = item.icon;
          const active = pathname === item.href || (item.href === "/investigations" && pathname?.startsWith("/investigations"));
          const isAnchor = item.href.includes("#");
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cx(
                "flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm",
                active
                  ? "bg-accent/15 text-accent border border-accent/30"
                  : "text-ink hover:bg-panel2 border border-transparent",
                item.soon && "opacity-60"
              )}
            >
              <Icon size={16} />
              <span className="flex-1">{item.label}</span>
              {item.soon && <span className="text-[9px] uppercase tracking-wider text-muted">soon</span>}
            </Link>
          );
        })}
      </nav>
      <div className="p-3 border-t border-border">
        <div className="flex items-center gap-2 text-[12px] text-muted">
          <Activity size={14} className="text-ok" />
          <span className="flex-1">Backend</span>
          <span className="badge bg-[#0f3326] text-ok">live</span>
        </div>
        <div className="mt-2 text-[10px] text-muted leading-snug">
          SENTINEL Financial Crime Investigation Platform — investigator dashboard.
        </div>
      </div>
    </aside>
  );
}