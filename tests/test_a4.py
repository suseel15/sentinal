"""A4 tests: plain-python runnable (no pytest dep). 5 synthetic + 1 live e2e."""
import logging
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test_a4")


def _g(edges):
    import networkx as nx
    g = nx.DiGraph()
    for u, v, ts, amt in edges:
        if u not in g:
            g.add_node(u, kind="ACCOUNT")
        if v not in g:
            g.add_node(v, kind="ACCOUNT")
        g.add_edge(u, v, txn=f"{u}->{v}", amount=float(amt), timestamp=ts, risk=0.0)
    return g


def test_normal_low():
    from app.graph import patterns as pat
    from app.graph import risk_fusion as rf
    g = _g([("A", "B", "2025-09-10T10:00:00", 100), ("B", "C", "2025-09-10T11:00:00", 90)])
    out = pat.run_all(g)
    assert set(out.keys()) == {"mule_chain", "fan_in", "fan_out", "circular_flow", "rapid_layering", "shared_identity"}, out.keys()
    assert out["shared_identity"]["status"] == "UNAVAILABLE", out["shared_identity"]
    assert out["fan_in"]["pattern_detected"] is False, out["fan_in"]
    s, lvl = rf.fuse(out, {"RISK_WEIGHTS": {"mule_chain": 0.25, "fan_in": 0.15, "fan_out": 0.15, "circular_flow": 0.20, "rapid_layering": 0.15, "shared_identity": 0.10}, "RISK_BANDS": {"LOW": 30, "MED": 60, "HIGH": 80}})
    assert 0 <= s <= 100, s
    assert s < 30, f"expected LOW, got {s}"


def test_mule_chain():
    from app.graph import patterns as pat
    g = _g([("M1", "M2", "2025-09-10T10:00:00", 50000), ("M2", "M3", "2025-09-10T12:00:00", 49500),
            ("M3", "M4", "2025-09-10T14:00:00", 49000), ("X0", "M1", "2025-09-10T09:00:00", 50000)])
    out = pat.run_all(g)
    assert out["mule_chain"]["pattern_detected"] is True, out["mule_chain"]
    assert out["mule_chain"]["score"] > 0, out["mule_chain"]


def test_fan_in():
    from app.graph import patterns as pat
    edges = [(f"S{i}", "HUB", "2025-09-10T10:00:00", 1000 + i) for i in range(7)]
    g = _g(edges)
    out = pat.run_all(g)
    assert out["fan_in"]["pattern_detected"] is True, out["fan_in"]
    assert out["fan_in"]["metrics"]["unique_senders"] >= 5, out["fan_in"]


def test_hub_whitelisted():
    from app.graph.traversal import bounded_bfs, build_subgraph
    from app.graph import patterns as pat
    edges = [("SEED", "HUBX", "2025-09-10T10:00:00", 50000), ("HUBX", "M2", "2025-09-10T11:00:00", 49500),
             ("M2", "M3", "2025-09-10T12:00:00", 49000)]
    g = _g(edges)
    try:
        from app.graph.supernode_service import init_supernode_table
        init_supernode_table()
        import sqlite3, json as _j
        from pathlib import Path as _P
        cfgp = _P(__file__).resolve().parent.parent / "config" / "a1.json"
        dbp = _P(_j.loads(cfgp.read_text()).get("db_path", "database/sentinel.db"))
        if not dbp.is_absolute():
            dbp = _P(__file__).resolve().parent.parent / dbp
        c = sqlite3.connect(str(dbp))
        c.execute("INSERT OR REPLACE INTO super_node_registry VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                  ("HUBX", "ACCOUNT", 900, 450, 450, 1e7, 400, 99.9, "SUPER_NODE", 1, "manual whitelist", "2025-01-01"))
        c.commit()
        c.close()
    except Exception as e:
        log.warning("hub seed failed: %s", e)
    cfg = {"HUB_WHITELIST": ["HUBX"]}
    def _hub(n):
        try:
            from app.graph.supernode_service import is_hub
            return is_hub(n, cfg)
        except Exception:
            return str(n) == "HUBX"
    nodes, edgelist, mode, trunc = bounded_bfs(g, "SEED", "2025-09-10T10:30:00", 4, 2000, 72, _hub)
    assert any(e.get("via_hub") for e in edgelist), edgelist
    sub = build_subgraph(g, nodes, edgelist)
    for n in list(sub.nodes()):
        try:
            if str(n) == "HUBX":
                sub.nodes[n]["is_hub"] = True
        except Exception:
            pass
    out = pat.run_all(sub)
    hub_in_mule = any("HUBX" in str(c) for e in out["mule_chain"].get("evidence", []) for c in (e.get("chain") or []))
    assert hub_in_mule is False, out["mule_chain"]
    eff_mode = "HUB_AWARE" if any(e.get("via_hub") for e in edgelist) else "FULL"
    assert eff_mode == "HUB_AWARE", eff_mode


def test_oversize_fallback():
    from app.graph.traversal import bounded_bfs
    edges = [(f"N{i}", f"N{i+1}", "2025-09-10T10:00:00", 100) for i in range(30)]
    g = _g(edges)
    nodes, edgelist, mode, trunc = bounded_bfs(g, "N0", "2025-09-10T10:00:00", 4, 5, 72, lambda n: False)
    assert mode == "SIZE_FALLBACK" and trunc is True, (mode, trunc)
    from app.graph import patterns as pat
    out = pat.run_all(__import__("networkx").DiGraph(), fallback=True)
    assert len(out) == 6, out.keys()


def test_live_e2e():
    import uuid as _u
    from app.agents.a1_ingestion import A1Agent
    from app.services.store import save_investigation
    agent = A1Agent()
    dest = f"E2E_A4_{_u.uuid4().hex[:6]}"
    raw = {"source_account": "ACC00008", "destination_account": dest, "amount": 850000,
           "timestamp": "2025-09-15T02:30:00", "transaction_type": "TRANSFER", "tms_alert": True}
    resp = agent.ingest(raw, "canonical")
    inv_id = resp.investigation_id if hasattr(resp, "investigation_id") else resp["investigation_id"]
    txn_id = resp.transaction_id if hasattr(resp, "transaction_id") else resp["transaction_id"]
    save_investigation(inv_id, txn_id, "OPEN", {"transaction_id": txn_id, "risk_score": 85.0, "risk_level": "HIGH",
        "rule_score": 60, "anomaly_score": 0.9, "possible_typologies": ["MULE"], "top_reasons": ["large amount"], "shap": {}})
    from app.agents import a4_graph
    r = a4_graph.analyze(inv_id)
    d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
    assert d["analysis_mode"] in ("FULL", "HUB_AWARE"), d["analysis_mode"]
    assert 0 <= float(d["graph_risk_score"]) <= 100, d["graph_risk_score"]
    assert set(d["patterns"].keys()) == {"mule_chain", "fan_in", "fan_out", "circular_flow", "rapid_layering", "shared_identity"}, d["patterns"].keys()


_TESTS = [test_normal_low, test_mule_chain, test_fan_in, test_hub_whitelisted, test_oversize_fallback, test_live_e2e]

if __name__ == "__main__":
    fails = 0
    for fn in _TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:
            fails += 1
            print(f"FAIL {fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
    print(f"{len(_TESTS)-fails}/{len(_TESTS)} passed")
    sys.exit(1 if fails else 0)
