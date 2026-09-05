"use client";
import { useEffect, useRef, useState } from "react";
import cytoscape from "cytoscape";
import { GraphVisualization } from "@/types/investigation";
import { Maximize2, Minimize2, RotateCcw } from "lucide-react";

const NODE_COLORS: Record<string, string> = {
  ACCOUNT: "#5aa8ff",
  CUSTOMER: "#a78bfa",
  COMPANY: "#a78bfa",
  DEVICE: "#f0b400",
  PHONE: "#ff5c7c",
  IP: "#ff5c7c",
  TRANSACTION: "#29c48a"
};

export default function GraphView({ data }: { data: GraphVisualization }) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const cyRef = useRef<any>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !data?.nodes?.length) return;
    // Sanitize: unique node ids, drop edges pointing at missing nodes.
    const seen = new Set<string>();
    const nodes = (data.nodes || []).filter((n) => {
      if (!n || !n.id || seen.has(String(n.id))) return false;
      seen.add(String(n.id));
      return true;
    });
    if (!nodes.length) return;
    const edges = (data.edges || []).filter(
      (e) => e && seen.has(String(e.source)) && seen.has(String(e.target))
    );
    const elements = [
      ...nodes.map((n) => ({
        data: {
          id: String(n.id),
          label: String(n.id),
          degree: n.degree || 0,
          volume: n.volume || 0,
          is_hub: n.is_hub,
          type: n.type || "ACCOUNT",
          color: NODE_COLORS[n.type || "ACCOUNT"] || "#5aa8ff"
        }
      })),
      ...edges.map((e, i) => ({
        data: {
          id: `e${i}`,
          source: String(e.source),
          target: String(e.target),
          amount: e.amount || 0,
          via_hub: e.via_hub
        }
      }))
    ];

    cyRef.current?.destroy();
    cyRef.current = null;
    const cy = cytoscape({
      container,
      elements,
      style: [
        {
          selector: "node",
          style: {
            "background-color": "data(color)",
            label: "data(label)",
            color: "#e6ecff",
            "font-size": 10,
            "text-valign": "bottom",
            "text-halign": "center",
            "text-margin-y": 4,
            width: 26,
            height: 26,
            "border-color": "#0e1430",
            "border-width": 2
          }
        },
        {
          selector: "node[?is_hub]",
          style: {
            "border-color": "#a78bfa",
            "border-width": 4,
            width: 34,
            height: 34
          }
        },
        {
          selector: "node:selected",
          style: {
            "border-color": "#ff5c7c",
            "border-width": 4,
            "background-blacken": -0.2
          }
        },
        {
          selector: "edge",
          style: {
            width: 1.5,
            "line-color": "#3a447a",
            "target-arrow-color": "#3a447a",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            opacity: 0.7,
            label: "data(amount)",
            "font-size": 9,
            color: "#93a0c8",
            "text-rotation": "autorotate"
          }
        },
        {
          selector: "edge[?via_hub]",
          style: {
            "line-color": "#f0b400",
            "target-arrow-color": "#f0b400",
            "line-style": "dashed"
          }
        }
      ],
      // Static (non-animated) layout: the cose animation loop keeps firing
      // rAF callbacks after unmount/destroy, crashing on a null renderer.
      layout: { name: "cose", animate: false, randomize: false, idealEdgeLength: 110, padding: 20 },
      wheelSensitivity: 0.2
    });
    cyRef.current = cy;

    cy.on("tap", "node", (evt: any) => {
      const id = evt.target.id();
      setSelected(id);
    });
    cy.on("tap", (evt: any) => {
      if (evt.target === cy) setSelected(null);
    });

    return () => {
      try {
        cy.removeAllListeners();
        cy.stop();
      } catch {
        /* already torn down */
      }
      try {
        cy.destroy();
      } catch {
        /* already torn down */
      }
      if (cyRef.current === cy) cyRef.current = null;
    };
  }, [data]);

  function expandNode() {
    if (!selected || !cyRef.current) return;
    const next = new Set(expanded);
    next.add(selected);
    setExpanded(next);
    const node = cyRef.current.getElementById(selected);
    if (!node || node.empty()) return;
    const neighborhood = node.closedNeighborhood();
    try {
      neighborhood.animate({ style: { opacity: 1 } } as any, { duration: 250 });
    } catch {
      /* animation unsupported in current state */
    }
  }

  function collapseAll() {
    setExpanded(new Set());
    setSelected(null);
  }

  function fit() {
    if (cyRef.current) cyRef.current.fit(undefined, 30);
  }

  const sizeLimited = (data.analysis_mode || "").toUpperCase() === "SIZE_FALLBACK";
  const nodeCount = data.nodes?.length || 0;
  const edgeCount = data.edges?.length || 0;

  return (
    <div className="card p-0 overflow-hidden">
      <div className="px-4 py-2 border-b border-border flex items-center justify-between gap-2">
        <div>
          <div className="section-title">Network Intelligence</div>
          <div className="text-[12px] text-muted">
            {nodeCount} nodes · {edgeCount} edges · mode {data.analysis_mode || "FULL"}
            {expanded.size > 0 && ` · ${expanded.size} expanded`}
          </div>
        </div>
        <div className="flex items-center gap-2 text-[12px]">
          {(data.nodes || []).some((n) => n.is_hub) && (
            <span className="badge bg-[#2a1f4a] text-hi">HUB-AWARE</span>
          )}
          {sizeLimited && (
            <span className="badge bg-[#4a1d2a] text-bad">SIZE FALLBACK</span>
          )}
          {selected && (
            <button className="btn-secondary !py-1" onClick={expandNode}>
              <Maximize2 size={12} /> Expand {selected}
            </button>
          )}
          {expanded.size > 0 && (
            <button className="btn-secondary !py-1" onClick={collapseAll}>
              <Minimize2 size={12} /> Collapse
            </button>
          )}
          <button className="btn-secondary !py-1" onClick={fit}>
            <RotateCcw size={12} /> Fit
          </button>
        </div>
      </div>
      <div ref={containerRef} style={{ height: 460, background: "#0a1024" }} />
      {sizeLimited && (
        <div className="px-4 py-2 text-[12px] text-muted border-t border-border">
          Automated graph analysis was limited because the connected network exceeded the configured investigation boundary.
          Aggregate network statistics are shown. Manual graph investigation is recommended.
        </div>
      )}
      <div className="px-4 py-2 text-[11px] text-muted border-t border-border flex items-center gap-2">
        💡 Click a node to select · Click <span className="font-mono">Expand</span> to load its neighborhood. Backend enforces 4-hop / 2,000-node bounds.
      </div>
    </div>
  );
}