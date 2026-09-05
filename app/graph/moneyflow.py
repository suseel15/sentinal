"""A4 money-flow reconstruction from seed."""
import logging
from datetime import datetime

log = logging.getLogger(__name__)


def _ts(v):
    try:
        if v is None or v == "":
            return None
        if isinstance(v, datetime):
            return v
        return datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except Exception:
        return None


def reconstruct(sub, seed: str) -> dict:
    try:
        seed = str(seed)
        out = {"seed": seed, "hop_count": 0, "inflow": 0.0, "outflow": 0.0,
               "pass_through_ratio": 0.0, "avg_time_between_hops_hours": 0.0,
               "split_ratio": 0.0, "concentration": 0.0, "retention": 0.0,
               "node_count": 0, "edge_count": 0}
        try:
            out["node_count"] = int(sub.number_of_nodes())
            out["edge_count"] = int(sub.number_of_edges())
        except Exception:
            log.exception("count failed")
        try:
            import networkx as nx
            lengths = nx.single_source_shortest_path_length(sub.to_undirected() if hasattr(sub, "to_undirected") else sub, seed) if seed in sub else {}
            non_hub_depths = []
            for n, d in (lengths or {}).items():
                try:
                    if n == seed:
                        continue
                    if sub.nodes[n].get("is_hub"):
                        continue
                    non_hub_depths.append(int(d))
                except Exception:
                    continue
            out["hop_count"] = int(max(non_hub_depths)) if non_hub_depths else 0
        except Exception:
            log.exception("hop count failed")
        try:
            inflow = float(sum(float(d.get("amount", 0) or 0) for _, _, d in sub.in_edges(seed, data=True))) if seed in sub else 0.0
        except Exception:
            inflow = 0.0
        try:
            outflow = float(sum(float(d.get("amount", 0) or 0) for _, _, d in sub.out_edges(seed, data=True))) if seed in sub else 0.0
        except Exception:
            outflow = 0.0
        out["inflow"], out["outflow"] = inflow, outflow
        try:
            denom = max(inflow, outflow, 1.0)
            out["pass_through_ratio"] = float(min(inflow, outflow) / denom) if (inflow and outflow) else 0.0
            out["retention"] = float(max(0.0, min(1.0, (inflow - outflow) / inflow))) if inflow else 0.0
        except Exception:
            log.exception("ratio failed")
        try:
            times = sorted([_ts(d.get("timestamp")) for _, _, d in sub.edges(data=True)])
            times = [t for t in times if t is not None]
            if len(times) >= 2:
                gaps = [(times[i] - times[i - 1]).total_seconds() / 3600.0 for i in range(1, len(times))]
                gaps = [abs(g) for g in gaps]
                out["avg_time_between_hops_hours"] = float(sum(gaps) / len(gaps))
        except Exception:
            log.exception("time gap failed")
        try:
            outs = sorted([float(d.get("amount", 0) or 0) for _, _, d in sub.out_edges(seed, data=True)], reverse=True) if seed in sub else []
            tot = sum(outs) or 1.0
            out["split_ratio"] = float(len(outs))
            out["concentration"] = float(outs[0] / tot) if outs else 0.0
        except Exception:
            log.exception("split failed")
        return out
    except Exception:
        log.exception("reconstruct failed")
        return {"seed": str(seed), "hop_count": 0, "inflow": 0.0, "outflow": 0.0,
                "pass_through_ratio": 0.0, "avg_time_between_hops_hours": 0.0,
                "split_ratio": 0.0, "concentration": 0.0, "retention": 0.0,
                "node_count": 0, "edge_count": 0}
