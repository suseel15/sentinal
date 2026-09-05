"""A4 graph intelligence agent: analyze(investigation_id) -> GraphAnalysisResult."""
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _a4_config(overrides: dict | None = None) -> dict:
    try:
        cfg = json.loads((REPO_ROOT / "config" / "a4.json").read_text())
    except Exception:
        log.exception("a4 config read failed, defaults")
        cfg = {"MAX_HOPS": 4, "MAX_NODES": 2000, "TIME_WINDOW_HOURS": 72,
               "RISK_WEIGHTS": {}, "RISK_BANDS": {"LOW": 30, "MED": 60, "HIGH": 80}, "HUB_WHITELIST": []}
    if overrides:
        try:
            cfg.update(overrides)
        except Exception:
            log.exception("config override failed")
    return cfg


def analyze(investigation_id: str, config_overrides: dict | None = None):
    from app.schemas.graph import GraphAnalysisResult
    from app.services.store import get_investigation, log_event
    from app.graph import agent_store as gs
    cfg = _a4_config(config_overrides)
    max_hops = int(cfg.get("MAX_HOPS", 4))
    max_nodes = int(cfg.get("MAX_NODES", 2000))
    window_h = int(cfg.get("TIME_WINDOW_HOURS", 72))
    limitations: list[str] = []
    try:
        inv = get_investigation(investigation_id)
    except Exception:
        log.exception("get_investigation failed")
        inv = None
    if not inv:
        raise ValueError(f"investigation {investigation_id} not found")
    try:
        trow = gs.get_txn_by_inv(investigation_id)
    except Exception:
        log.exception("txn lookup failed")
        trow = None
    seed, seed_ts, seed_txn = "UNKNOWN", None, ""
    try:
        payload = (trow or {}).get("payload") or {}
        can = payload.get("canonical") or {}
        seed = str(can.get("source_account") or (inv.get("result") or {}).get("account_id") or "UNKNOWN")
        seed_ts = can.get("timestamp")
        seed_txn = str(can.get("transaction_id") or "")
    except Exception:
        log.exception("seed extract failed")
    if seed in ("", "UNKNOWN", "None"):
        try:
            res = inv.get("result") or {}
            seed = str(res.get("account_id") or res.get("source_account") or "UNKNOWN")
        except Exception:
            pass
    backend = None
    graph = None
    try:
        from app.graph.backend import get_backend
        from app.graph.backend import ServiceUnavailable
        try:
            backend = get_backend()
        except Exception:
            log.exception("get_backend failed")
            from app.graph.backend import NetworkXBackend
            backend = NetworkXBackend()
        try:
            graph = backend.get_graph()
        except ServiceUnavailable:
            log.warning("primary backend unavailable, NetworkX fallback")
            from app.graph.backend import NetworkXBackend
            backend = NetworkXBackend()
            graph = backend.get_graph()
    except Exception:
        log.exception("backend load failed")
        import networkx as nx
        graph = nx.DiGraph()
        limitations.append("graph backend unavailable; empty subgraph")
    if seed not in graph and seed_txn:
        try:
            dest = None
            try:
                dest = str(((trow or {}).get("payload") or {}).get("canonical", {}).get("destination_account", ""))
            except Exception:
                pass
            if dest:
                import networkx as nx
                if seed not in graph:
                    graph.add_node(seed, kind="ACCOUNT")
                if dest not in graph:
                    graph.add_node(dest, kind="ACCOUNT")
                if not graph.has_edge(seed, dest):
                    graph.add_edge(seed, dest, txn=seed_txn, amount=0.0, timestamp=str(seed_ts or ""), risk=0.0)
                limitations.append("seed edge injected from investigation payload for connectivity")
        except Exception:
            log.exception("seed inject failed")
    try:
        from app.graph import supernode_service as sns
        try:
            sns.init_supernode_table()
        except Exception:
            log.exception("supernode init failed")
        try:
            sns.compute_supernodes(backend if backend is not None else None, cfg)
        except Exception:
            log.exception("supernode compute failed")
        def _is_hub(n):
            try:
                return sns.is_hub(n, cfg)
            except Exception:
                return False
    except Exception:
        log.exception("supernode wiring failed")
        def _is_hub(n):
            return False
    nodes, edges, trav_mode, truncated = [seed], [], "FULL", False
    try:
        from app.graph.traversal import bounded_bfs, build_subgraph
        try:
            nodes, edges, trav_mode, truncated = bounded_bfs(graph, seed, seed_ts, max_hops, max_nodes, window_h, _is_hub)
        except Exception:
            log.exception("bounded_bfs failed")
        try:
            sub = build_subgraph(graph, nodes, edges)
        except Exception:
            log.exception("build_subgraph failed")
            import networkx as nx
            sub = nx.DiGraph()
            sub.add_node(seed)
    except Exception:
        log.exception("traversal import failed")
        import networkx as nx
        sub = nx.DiGraph()
        sub.add_node(seed)
    super_hit = []
    try:
        for n in nodes:
            try:
                if _is_hub(n):
                    super_hit.append(str(n))
            except Exception:
                continue
    except Exception:
        log.exception("super hit scan failed")
    try:
        for n in super_hit:
            try:
                if n in sub.nodes:
                    sub.nodes[n]["is_hub"] = True
            except Exception:
                continue
    except Exception:
        pass
    via_hub = False
    try:
        via_hub = any(bool(e.get("via_hub")) for e in edges)
    except Exception:
        pass
    if truncated or trav_mode == "SIZE_FALLBACK":
        mode = "SIZE_FALLBACK"
    elif via_hub or super_hit:
        mode = "HUB_AWARE"
    else:
        mode = "FULL"
    patterns: dict = {}
    try:
        from app.graph import patterns as pat
        try:
            try:
                sub.graph["seed"] = seed
            except Exception:
                pass
            patterns = pat.run_all(sub, fallback=(mode == "SIZE_FALLBACK"))
        except Exception:
            log.exception("run_all failed")
            patterns = {}
        for k in ("mule_chain", "fan_in", "fan_out", "circular_flow", "rapid_layering", "shared_identity"):
            if k not in patterns:
                patterns[k] = {"pattern_detected": False, "score": 0.0, "confidence": "LOW",
                               "evidence": [], "metrics": {}, "status": "UNAVAILABLE", "reason": "not computed"}
    except Exception:
        log.exception("patterns import failed")
    mf = {}
    try:
        from app.graph import moneyflow as mfl
        try:
            mf = mfl.reconstruct(sub, seed)
        except Exception:
            log.exception("moneyflow failed")
            mf = {"seed": seed}
    except Exception:
        mf = {"seed": seed}
    comms = {}
    try:
        from app.graph import community as com
        try:
            com.init_community_table()
        except Exception:
            log.exception("community init failed")
        try:
            comms = com.lookup(nodes[:500])
        except Exception:
            log.exception("community lookup failed")
    except Exception:
        pass
    score, level = 0.0, "LOW"
    try:
        from app.graph import risk_fusion as rf
        try:
            score, level = rf.fuse(patterns, cfg)
        except Exception:
            log.exception("fusion failed")
    except Exception:
        pass
    status = "COMPLETE"
    try:
        avail_n = sum(1 for v in patterns.values() if isinstance(v, dict) and v.get("status") in ("AVAILABLE", "SIZE_FALLBACK"))
        unav_n = sum(1 for v in patterns.values() if isinstance(v, dict) and v.get("status") == "UNAVAILABLE")
        if mode == "SIZE_FALLBACK":
            status = "PARTIAL"
        elif unav_n >= 3:
            status = "INCOMPLETE"
        elif unav_n >= 1:
            status = "COMPLETE"
        if not nodes or (len(nodes) <= 1 and not edges):
            status = "INCOMPLETE" if unav_n >= 2 else "PARTIAL"
    except Exception:
        log.exception("status derive failed")
    manual = False
    try:
        manual = bool(mode == "SIZE_FALLBACK" or status in ("PARTIAL", "INCOMPLETE") or score >= 60 or any((v or {}).get("pattern_detected") for v in patterns.values() if isinstance(v, dict)))
    except Exception:
        manual = True
    if mode == "SIZE_FALLBACK":
        limitations.append("subgraph truncated at node cap; aggregate-only view; requires manual review")
    if mode == "HUB_AWARE":
        limitations.append("hub-aware traversal: expansion limited beyond hub nodes; hub edges excluded from mule scoring")
    limitations.append("graph indicators are indicative only and require manual review; no fraud verdict asserted")
    try:
        limitations.append("identity linkage unavailable (no device/phone/ip in source CSVs)")
    except Exception:
        pass
    sup_txns: list[str] = []
    try:
        for e in edges[:200]:
            try:
                if e.get("txn"):
                    sup_txns.append(str(e["txn"]))
            except Exception:
                continue
        if seed_txn and seed_txn not in sup_txns:
            sup_txns = [seed_txn] + sup_txns
    except Exception:
        log.exception("sup txns failed")
    result = {"investigation_id": investigation_id, "analysis_mode": mode, "status": status,
              "node_count": len(nodes), "edge_count": len(edges), "patterns": patterns,
              "graph_risk_score": float(score), "risk_level": level, "communities": comms,
              "super_nodes_detected": super_hit, "money_flow": mf, "limitations": limitations,
              "supporting_entities": [str(n) for n in nodes[:200]], "supporting_transactions": sup_txns[:200],
              "manual_review_required": bool(manual)}
    try:
        gs.init_graph_tables()
    except Exception:
        log.exception("graph tables init failed")
    try:
        gs.save_analysis(result)
    except Exception:
        log.exception("save analysis failed")
    try:
        log_event(investigation_id, "A4", f"GRAPH_ANALYSIS:{mode}:{status}")
    except Exception:
        log.exception("audit log failed")
    try:
        return GraphAnalysisResult(**result)
    except Exception:
        log.exception("schema validate failed, returning raw")
        return result
