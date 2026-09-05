import logging
import numpy as np
import pandas as pd
import networkx as nx
from . import config

log = logging.getLogger(__name__)
C = config.COLS
EPS = 1e-9


def build_graph(df: pd.DataFrame, train_end: str | None = None):
    try:
        te = pd.to_datetime(train_end or config.SPLIT["train_end"])
        d = df.copy()
        if C["timestamp"] in d.columns:
            d[C["timestamp"]] = pd.to_datetime(d[C["timestamp"]], format="mixed")
            d = d[d[C["timestamp"]] <= te]
        s = d[C["account_id"]].astype(str).to_numpy()
        t = d[C["counterparty"]].astype(str).to_numpy()
        w = pd.to_numeric(d[C["amount"]], errors="coerce").fillna(0.0).abs().to_numpy(dtype=float)
        agg: dict = {}
        for a, b, v in zip(s, t, w):
            k = (a, b)
            agg[k] = agg.get(k, 0.0) + float(v)
        G = nx.DiGraph()
        G.add_nodes_from(set(s.tolist()) | set(t.tolist()))
        G.add_weighted_edges_from([(a, b, v) for (a, b), v in agg.items()])
        log.info("graph nodes=%d edges=%d train_end=%s", G.number_of_nodes(), G.number_of_edges(), te.date())
        return G
    except Exception:
        log.exception("build_graph failed")
        raise


def _globals(G: nx.DiGraph, label_df=None):
    in_deg = dict(G.in_degree()) if len(G) else {}
    out_deg = dict(G.out_degree()) if len(G) else {}
    w_in = dict(G.in_degree(weight="weight")) if len(G) else {}
    w_out = dict(G.out_degree(weight="weight")) if len(G) else {}
    try:
        pr = nx.pagerank(G, weight="weight") if len(G) else {}
    except Exception:
        pr = {}
    try:
        hubs, auths = nx.hits(G, max_iter=100, tol=1e-04, normalized=True) if len(G) else ({}, {})
    except Exception:
        hubs, auths = {}, {}
    try:
        core = nx.core_number(G.to_undirected()) if len(G) else {}
    except Exception:
        core = {}
    two, cyc = {}, {}
    for n in list(G.nodes()):
        try:
            s1 = list(G.successors(n))[:50]
        except Exception:
            s1 = []
        c = 1 if G.has_edge(n, n) else 0
        if not c:
            for x in s1:
                if G.has_edge(x, n):
                    c = 1
                    break
        cyc[n] = c
        seen = set()
        for x in s1:
            try:
                for y in G.successors(x):
                    seen.add(y)
                    if len(seen) >= 200:
                        break
            except Exception:
                continue
            if len(seen) >= 200:
                break
        seen.discard(n)
        two[n] = float(len(seen))
    try:
        from networkx.algorithms.community import greedy_modularity_communities
        cs: dict = {}
        if len(G):
            for com in greedy_modularity_communities(G.to_undirected()):
                for n in com:
                    cs[n] = float(len(com))
    except Exception:
        cs = {}
    nr: dict = {}
    if label_df is not None and len(label_df) and len(G):
        try:
            ld = label_df.copy()
            lab = C["label"] if C["label"] in ld.columns else ("is_suspicious" if "is_suspicious" in ld.columns else None)
            if lab and C["account_id"] in ld.columns:
                risk = ld.assign(_a=ld[C["account_id"]].astype(str)).groupby("_a")[lab].mean().to_dict()
                for n in list(G.nodes()):
                    try:
                        ss = list(G.successors(n))
                    except Exception:
                        ss = []
                    v = [risk[q] for q in ss if q in risk]
                    nr[n] = float(np.mean(v)) if v else 0.0
        except Exception:
            nr = {}
    return in_deg, out_deg, w_in, w_out, pr, hubs, auths, core, two, cyc, cs, nr


def graph_features(df: pd.DataFrame, G: nx.DiGraph, label_df=None) -> pd.DataFrame:
    try:
        d = df.copy()
        d[C["timestamp"]] = pd.to_datetime(d[C["timestamp"]], format="mixed")
        d["_a"] = d[C["account_id"]].astype(str)
        in_deg, out_deg, w_in, w_out, pr, hubs, auths, core, two, cyc, cs, nr = _globals(G, label_df)
        a = d["_a"]
        d["in_degree"] = a.map(in_deg).fillna(0).astype(float)
        d["out_degree"] = a.map(out_deg).fillna(0).astype(float)
        d["w_in"] = a.map(w_in).fillna(0).astype(float)
        d["w_out"] = a.map(w_out).fillna(0).astype(float)
        d["flow_ratio"] = (d["w_in"] / (d["w_out"] + EPS)).astype(float)
        d["log_in"] = np.log1p(d["w_in"].clip(lower=0)).astype(float)
        d["pagerank"] = a.map(pr).fillna(0).astype(float)
        d["hits_hub"] = a.map(hubs).fillna(0).astype(float)
        d["hits_auth"] = a.map(auths).fillna(0).astype(float)
        d["kcore"] = a.map(core).fillna(0).astype(float)
        d["two_hop_reach"] = a.map(two).fillna(0).astype(float)
        d["cycle_flag"] = a.map(cyc).fillna(0).astype(float)
        d["community_size"] = a.map(cs).fillna(1).astype(float)
        d["neighbor_risk"] = a.map(nr).fillna(0).astype(float) if nr else 0.0
        d = d.sort_values(C["timestamp"]).reset_index(drop=True)
        ts = d[C["timestamp"]].values.astype("datetime64[ns]").astype("int64")
        cps = d[C["counterparty"]].astype(str).to_numpy()
        ty = d[C["type"]].astype(str).str.upper().to_numpy() if C["type"] in d.columns else np.array([""] * len(d))
        NS = np.int64(1_000_000_000)
        DAY = np.int64(86400) * NS
        fan_in = np.zeros(len(d))
        fan_out = np.zeros(len(d))
        burst = np.zeros(len(d))
        for _, idx in d.groupby("_a", sort=False).groups.items():
            ii = np.asarray(list(idx), dtype=int)
            o = ii[np.argsort(ts[ii], kind="stable")]
            t = ts[o]
            left7 = np.searchsorted(t, t - np.int64(7) * DAY)
            left1 = np.searchsorted(t, t - DAY)
            tx1 = (np.arange(len(o)) - left1).astype(float)
            for k in range(len(o)):
                s0 = left7[k]
                if k > s0:
                    wc = cps[o[s0:k]]
                    wy = ty[o[s0:k]]
                    mc = wy == "CREDIT"
                    md = wy == "DEBIT"
                    if mc.any():
                        fan_in[o[k]] = float(len(set(wc[mc])))
                    if md.any():
                        fan_out[o[k]] = float(len(set(wc[md])))
                    if not mc.any() and not md.any():
                        v = float(len(set(wc))) if len(wc) else 0.0
                        fan_in[o[k]] = v
                        fan_out[o[k]] = v
            mean, m2, cnt = 0.0, 0.0, 0
            for k in range(len(o)):
                x = float(tx1[k])
                if cnt == 0:
                    burst[o[k]] = 0.0
                else:
                    std = float(np.sqrt(m2 / (cnt - 1))) if cnt > 1 else 0.0
                    burst[o[k]] = (x - mean) / (std + 1.0)
                cnt += 1
                dl = x - mean
                mean += dl / cnt
                m2 += dl * (x - mean)
        d["fan_in_7d"] = fan_in
        d["fan_out_7d"] = fan_out
        d["burst_score"] = burst
        d["gather_scatter_score"] = np.maximum((d["fan_in_7d"] + 1) / (d["fan_out_7d"] + 1), (d["fan_out_7d"] + 1) / (d["fan_in_7d"] + 1)).astype(float)
        for col in ["in_degree", "out_degree", "w_in", "w_out", "flow_ratio", "log_in", "pagerank", "hits_hub", "hits_auth", "kcore", "fan_in_7d", "fan_out_7d", "two_hop_reach", "neighbor_risk", "burst_score", "gather_scatter_score", "cycle_flag", "community_size"]:
            d[col] = d[col].fillna(0).astype(float)
        d = d.drop(columns=["_a"], errors="ignore")
        log.info("graph_features n=%s", len(d))
        return d
    except Exception:
        log.exception("graph_features failed")
        raise


def scc_map(G: nx.DiGraph) -> dict:
    try:
        out = {}
        for i, comp in enumerate(nx.strongly_connected_components(G)):
            for n in comp:
                out[n] = (i, len(comp))
        return out
    except Exception:
        return {}


def build_node_table(G: nx.DiGraph, df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["_a"] = d[C["account_id"]].astype(str)
    d["_cp"] = d[C["counterparty"]].astype(str)
    d["_abs"] = pd.to_numeric(d[C["amount"]], errors="coerce").fillna(0).abs()
    d["_is_db"] = (d[C["type"]] == "DEBIT").astype(int) if C["type"] in d.columns else 0
    scc = scc_map(G)
    rows = []
    for node in G.nodes():
        sub = d[d["_a"] == node]
        win = float(sub["_abs"].sum())
        in_deg = G.in_degree(node)
        out_deg = G.out_degree(node)
        wout = float(G.out_degree(node, weight="weight"))
        sent = sub[sub["_is_db"] == 1]
        flow_ratio = float(wout / (win + EPS))
        pt = float(min(win, wout) / max(win, wout, 1.0)) if (in_deg and out_deg) else 0.0
        sid, ssize = scc.get(node, (-1, 1))
        rows.append({
            "node_id": node, "in_degree": in_deg, "out_degree": out_deg,
            "total_incoming_amount": win, "total_outgoing_amount": wout,
            "net_flow": win - wout, "flow_ratio": flow_ratio,
            "pass_through_score": pt, "n_txns": len(sub),
            "avg_rule_score": float(sub["rule_score"].mean()) if "rule_score" in sub else 0.0,
            "max_rule_score": float(sub["rule_score"].max()) if "rule_score" in sub else 0.0,
            "avg_anomaly_score": float(sub["anomaly_score"].mean()) if "anomaly_score" in sub else 0.0,
            "max_anomaly_score": float(sub["anomaly_score"].max()) if "anomaly_score" in sub else 0.0,
            "suspicious_txn_count": int((sub["is_suspicious"] == 1).sum()) if "is_suspicious" in sub else 0,
            "scc_id": sid, "scc_size": ssize,
        })
    nt = pd.DataFrame(rows)
    log.info("node_table nodes=%s", len(nt))
    return nt


def export_graphsage_ready(G: nx.DiGraph, node_table: pd.DataFrame, out_dir) -> dict:
    from pathlib import Path
    import joblib
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    nodes = list(G.nodes())
    idx = {n: i for i, n in enumerate(nodes)}
    feat_cols = [c for c in ["in_degree", "out_degree", "total_incoming_amount",
                             "total_outgoing_amount", "net_flow", "flow_ratio",
                             "pass_through_score", "n_txns", "avg_rule_score",
                             "max_rule_score", "avg_anomaly_score",
                             "max_anomaly_score", "suspicious_txn_count",
                             "scc_size"] if c in node_table.columns]
    mat = node_table.set_index("node_id").reindex(nodes)[feat_cols].fillna(0).values.astype(float)
    edges = [(idx[a], idx[b]) for a, b in G.edges() if a in idx and b in idx]
    edge_index = np.array(edges, dtype=int).T if edges else np.zeros((2, 0), dtype=int)
    joblib.dump({"node_features": mat, "feature_names": feat_cols}, out / "node_features.joblib")
    np.save(out / "edge_index.npy", edge_index)
    (out / "node_mapping.json").write_text(__import__("json").dumps(idx))
    log.info("graphsage_ready nodes=%s edges=%s feats=%s", len(nodes), len(edges), len(feat_cols))
    return {"nodes": len(nodes), "edges": len(edges), "features": feat_cols}
