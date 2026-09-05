"use client";
import { useEffect, useState } from "react";
import { api, supabaseConfigured } from "@/lib/api";
import { getSupabase } from "@/lib/supabase";
import { Activity, Radio, Cpu } from "lucide-react";

export default function Topbar() {
  const [streamRunning, setStreamRunning] = useState(false);
  const [llm, setLlm] = useState<{ available: boolean; model: string }>({ available: false, model: "" });

  useEffect(() => {
    let mounted = true;
    api.streamStatus().then((s: any) => {
      if (mounted && s) setStreamRunning(Boolean(s.running));
    });
    api.llmStatus().then((s: any) => {
      if (mounted && s) setLlm({ available: Boolean(s.available), model: String(s.model || "") });
    });
    return () => {
      mounted = false;
    };
  }, []);

  // Optional Supabase Realtime presence
  useEffect(() => {
    if (!supabaseConfigured) return;
    let ch: any;
    getSupabase().then((sb) => {
      if (!sb) return;
      ch = sb.channel("sentinel-top");
      ch.subscribe();
    });
    return () => {
      if (ch) ch.unsubscribe();
    };
  }, []);

  return (
    <div className="h-12 border-b border-border bg-panel/60 flex items-center px-4 gap-4">
      <div className="text-[12px] text-muted">
        SENTINEL • Phase 14 — Investigation Command Center
      </div>
      <div className="flex-1" />
      <div className="flex items-center gap-3 text-[12px]">
        <div className="flex items-center gap-1.5">
          <Radio size={14} className={streamRunning ? "text-ok" : "text-muted"} />
          <span className={streamRunning ? "text-ok" : "text-muted"}>
            {streamRunning ? "Stream: live" : "Stream: idle"}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Cpu size={14} className={llm.available ? "text-hi" : "text-muted"} />
          <span className={llm.available ? "text-hi" : "text-muted"}>
            {llm.available ? `LLM: ${llm.model}` : "LLM: template"}
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <Activity size={14} className="text-accent" />
          <span className="text-accent">Investigator mode</span>
        </div>
      </div>
    </div>
  );
}