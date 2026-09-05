"""A4 six pattern detectors (pure functions, indicative language only)."""
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


def _base():
    return {"pattern_detected": False, "score": 0.0, "confidence": "LOW",
            "evidence": [], "metrics": {}, "status": "AVAILABLE", "reason": None}


def _non_hub_nodes(sub):
    try:
        return [n for n in sub.nodes() if not sub.nodes[n].get("is_hub")]
    except Exception:
        return list(sub.nodes())


def detect_mule_chain(sub, min_len: int = 3, pt_thresh: float = 0.8, max_gap_days: float = 1.0) -> dict:
    out = _base()
    try:
        try:
            hub_edges = set((u, v) for u, v, d in sub.edges(data=True) if d.get("hub_edge") or d.get("via_hub"))
        except Exception:
            hub_edges = set()
        pt_nodes = []
        try:
            for n in sub.nodes():
                try:
                    if sub.nodes[n].get("is_hub"):
                        continue
                    vin = float(sum(float(d.get("amount", 0) or 0) for _, _, d in sub.in_edges(n, data=True) if (d.get("hub_edge") or d.get("via_hub")) is not True or True))
                    vout = float(sum(float(d.get("amount", 0) or 0) for _, _, d in sub.out_edges(n, data=True)))
                    vin_nh = 0.0
                    vout_nh = 0.0
                    for u, v, d in list(sub.in_edges(n, data=True)) + list(sub.out_edges(n, data=True)):
                        try:
                            if d.get("hub_edge"):
                                continue
                            if (u, v) == (u, n):
                                vin_nh += float(d.get("amount", 0) or 0)
                            else:
                                vout_nh += float(d.get("amount", 0) or 0)
                        except Exception:
                            continue
                    denom = max(vin_nh, vout_nh, 1.0)
                    pt = min(vin_nh, vout_nh) / denom if (vin_nh and vout_nh) else 0.0
                    if pt >= pt_thresh and sub.in_degree(n) >= 1 and sub.out_degree(n) >= 1:
                        pt_nodes.append((n, pt))
                except Exception:
                    continue
        except Exception:
            log.exception("mule pt scan failed")
        chains = []
        try:
            pt_set = set(n for n, _ in pt_nodes)
            adj = {}
            for u, v, d in sub.edges(data=True):
                try:
                    if d.get("hub_edge"):
                        continue
                    adj.setdefault(u, []).append((v, _ts(d.get("timestamp")), float(d.get("amount", 0) or 0)))
                except Exception:
                    continue
            def _dfs(path, tpath):
                try:
                    if len(path) >= min_len:
                        ok = True
                        for i in range(1, len(tpath)):
                            try:
                                if tpath[i] is None or tpath[i - 1] is None:
                                    continue
                                gap = abs((tpath[i] - tpath[i - 1]).total_seconds()) / 86400.0
                                if gap > max_gap_days:
                                    ok = False
                                    break
                            except Exception:
                                continue
                        mid = path[1:-1] if len(path) > 2 else []
                        if ok and all(m in pt_set or True for m in mid):
                            chains.append(list(path))
                            return
                    if len(path) >= 5:
                        return
                    last = path[-1]
                    for nb, t, _a in adj.get(last, [])[:20]:
                        if nb in path:
                            continue
                        if len(chains) >= 10:
                            return
                        _dfs(path + [nb], tpath + [t])
                except Exception:
                    return
            for n, _ in pt_nodes[:30]:
                try:
                    preds = [u for u, _ in sub.in_edges(n) if not sub.get_edge_data(u, n, {}).get("hub_edge")]
                    if preds:
                        _dfs([preds[0], n], [None, None])
                    else:
                        _dfs([n], [None])
                except Exception:
                    continue
                if len(chains) >= 10:
                    break
        except Exception:
            log.exception("mule chain dfs failed")
        n_chains = len(chains)
        out["metrics"] = {"chains_found": n_chains, "passthrough_nodes": len(pt_nodes),
                          "min_len": min_len, "hub_edges_excluded": len(hub_edges)}
        if n_chains > 0:
            out["pattern_detected"] = True
            out["score"] = float(min(1.0, 0.5 + 0.15 * n_chains))
            out["confidence"] = "HIGH" if n_chains >= 3 else "MEDIUM"
            out["evidence"] = [{"note": "chain of accounts consistent with pass-through movement; requires review", "chain": c} for c in chains[:5]]
            out["reason"] = "indicators consistent with possible mule-chain movement; requires review"
        else:
            out["reason"] = "no pass-through chain meeting thresholds observed"
        return out
    except Exception:
        log.exception("detect_mule_chain failed")
        out.update({"status": "UNAVAILABLE", "reason": "detector error"})
        return out


def detect_fan_in(sub, thresh: int = 5) -> dict:
    out = _base()
    try:
        best, bev, bmet = None, [], {}
        for n in sub.nodes():
            try:
                if sub.nodes[n].get("is_hub"):
                    continue
                senders = [u for u, _ in sub.in_edges(n) if not sub.get_edge_data(u, n, {}).get("hub_edge")]
                uniq = sorted(set(str(s) for s in senders))
                if len(uniq) >= thresh:
                    amts = sorted([float(sub.get_edge_data(u, n, {}).get("amount", 0) or 0) for u in senders], reverse=True)
                    tot = sum(amts) or 1.0
                    conc = float(amts[0] / tot) if amts else 0.0
                    score = float(min(1.0, (len(uniq) / 10.0) * 0.7 + conc * 0.3))
                    if best is None or score > best:
                        best, bev = score, [{"note": "multiple distinct senders to one account observed; requires review", "account": str(n), "senders": uniq[:20]}]
                        bmet = {"account": str(n), "unique_senders": len(uniq), "concentration": conc}
            except Exception:
                continue
        if best is not None:
            out.update({"pattern_detected": True, "score": best, "confidence": "HIGH" if best >= 0.6 else "MEDIUM",
                        "evidence": bev, "metrics": bmet,
                        "reason": "fan-in pattern indicators observed; requires review"})
        else:
            out["reason"] = "no account with >=5 distinct senders observed"
            try:
                out["metrics"] = {"max_unique_senders": max([len(set(u for u, _ in sub.in_edges(n))) for n in sub.nodes()] or [0])}
            except Exception:
                pass
        return out
    except Exception:
        log.exception("detect_fan_in failed")
        out.update({"status": "UNAVAILABLE", "reason": "detector error"})
        return out


def detect_fan_out(sub, thresh: int = 5) -> dict:
    out = _base()
    try:
        best, bev, bmet = None, [], {}
        for n in sub.nodes():
            try:
                if sub.nodes[n].get("is_hub"):
                    continue
                rcvs = [v for _, v in sub.out_edges(n) if not sub.get_edge_data(n, v, {}).get("hub_edge")]
                uniq = sorted(set(str(s) for s in rcvs))
                if len(uniq) >= thresh:
                    amts = sorted([float(sub.get_edge_data(n, v, {}).get("amount", 0) or 0) for v in rcvs], reverse=True)
                    tot = sum(amts) or 1.0
                    conc = float(amts[0] / tot) if amts else 0.0
                    score = float(min(1.0, (len(uniq) / 10.0) * 0.7 + conc * 0.3))
                    if best is None or score > best:
                        best, bev = score, [{"note": "one account distributing to many distinct receivers; requires review", "account": str(n), "receivers": uniq[:20]}]
                        bmet = {"account": str(n), "unique_receivers": len(uniq), "concentration": conc}
            except Exception:
                continue
        if best is not None:
            out.update({"pattern_detected": True, "score": best, "confidence": "HIGH" if best >= 0.6 else "MEDIUM",
                        "evidence": bev, "metrics": bmet,
                        "reason": "fan-out pattern indicators observed; requires review"})
        else:
            out["reason"] = "no account with >=5 distinct receivers observed"
        return out
    except Exception:
        log.exception("detect_fan_out failed")
        out.update({"status": "UNAVAILABLE", "reason": "detector error"})
        return out


def detect_circular_flow(sub, max_len: int = 5) -> dict:
    out = _base()
    try:
        import networkx as nx
        cycles = []
        try:
            if sub.number_of_nodes() <= 500:
                for cyc in nx.simple_cycles(sub):
                    try:
                        if 2 <= len(cyc) <= max_len:
                            if any(sub.get_edge_data(cyc[i], cyc[(i + 1) % len(cyc)], {}).get("hub_edge") for i in range(len(cyc))):
                                continue
                            cycles.append([str(x) for x in cyc])
                            if len(cycles) >= 10:
                                break
                    except Exception:
                        continue
            else:
                out["metrics"] = {"skipped": "subgraph too large for cycle enumeration"}
        except Exception:
            log.exception("cycle enum failed")
        out["metrics"] = {"cycles_found": len(cycles), "max_len": max_len}
        if cycles:
            out.update({"pattern_detected": True, "score": float(min(1.0, 0.55 + 0.1 * len(cycles))),
                        "confidence": "MEDIUM", "evidence": [{"note": "circular movement indicators; requires review", "cycle": c} for c in cycles[:5]],
                        "reason": "circular flow indicators observed; requires review"})
        else:
            out["reason"] = "no short cycles observed"
        return out
    except Exception:
        log.exception("detect_circular_flow failed")
        out.update({"status": "UNAVAILABLE", "reason": "detector error"})
        return out


def detect_rapid_layering(sub, min_hops: int = 3, window_h: int = 72) -> dict:
    out = _base()
    try:
        best = None
        bev = []
        try:
            adj = {}
            for u, v, d in sub.edges(data=True):
                try:
                    if d.get("hub_edge"):
                        continue
                    adj.setdefault(u, []).append((v, _ts(d.get("timestamp")), float(d.get("amount", 0) or 0)))
                except Exception:
                    continue
            found = []
            def _dfs(path, ts):
                try:
                    if len(path) - 1 >= min_hops:
                        valid = [t for t in ts if t is not None]
                        if len(valid) >= 2:
                            span_h = abs((max(valid) - min(valid)).total_seconds()) / 3600.0
                        else:
                            span_h = 0.0
                        if span_h <= window_h:
                            inflow = sum(float(sub.get_edge_data(u, path[1], {}).get("amount", 0) or 0) for u, _ in sub.in_edges(path[1])) or 1.0
                            outflow = sum(float(sub.get_edge_data(path[-2], v, {}).get("amount", 0) or 0) for _, v in sub.out_edges(path[-2])) or 0.0
                            retention = max(0.0, min(1.0, (inflow - outflow) / inflow))
                            found.append((list(path), span_h, retention))
                            return
                    if len(path) >= 6:
                        return
                    for nb, t, _a in adj.get(path[-1], [])[:20]:
                        if nb in path or len(found) >= 10:
                            continue
                        _dfs(path + [nb], ts + [t])
                except Exception:
                    return
            for s in list(sub.nodes())[:40]:
                try:
                    if sub.nodes[s].get("is_hub"):
                        continue
                    _dfs([s], [None])
                    if len(found) >= 10:
                        break
                except Exception:
                    continue
        except Exception:
            log.exception("rapid dfs failed")
            found = []
        out["metrics"] = {"layered_paths": len(found), "min_hops": min_hops, "window_h": window_h}
        if found:
            p, span, ret = found[0]
            score = float(min(1.0, 0.5 + 0.1 * len(found) + (0.2 if ret < 0.3 else 0.0)))
            out.update({"pattern_detected": True, "score": score, "confidence": "MEDIUM",
                        "evidence": [{"note": "rapid multi-hop movement indicators; requires review", "path": p, "span_hours": span, "retention": ret}],
                        "metrics": {"layered_paths": len(found), "span_hours": span, "retention": ret},
                        "reason": "rapid layering indicators observed; requires review"})
        else:
            out["reason"] = "no rapid multi-hop path within window observed"
        return out
    except Exception:
        log.exception("detect_rapid_layering failed")
        out.update({"status": "UNAVAILABLE", "reason": "detector error"})
        return out


def detect_shared_identity(sub) -> dict:
    """REAL shared-identity via identity_device.csv (device/phone/ip/email hashes)."""
    out = _base()
    try:
        seed = None
        try:
            seed = sub.graph.get("seed")
        except Exception:
            seed = None
        nodes = [str(n) for n in sub.nodes()]
        if seed in (None, "", "UNKNOWN"):
            seed = nodes[0] if nodes else None
        if not seed:
            out.update({"status": "UNAVAILABLE", "reason": "no seed account"})
            return out
        try:
            from app.services import datasets as _ds
            from pathlib import Path as _P
            import json as _j
            if not _ds.CSVS["identity"].exists():
                out.update({"status": "UNAVAILABLE",
                            "reason": "identity_device.csv absent; identity linkage unavailable"})
                return out
            weights = {"device": 0.30, "phone": 0.40, "ip": 0.15, "email": 0.20}
            try:
                cfg = _j.loads((_P(__file__).resolve().parent.parent.parent
                                / "config" / "a4.json").read_text())
                weights.update(cfg.get("identity_weights", {}))
            except Exception:
                pass
            seed_links = _ds.identity_links(str(seed))
            if not any(seed_links.values()):
                out.update({"reason": f"no registered device/phone/ip for {seed}; no linkage"})
                return out
            others = [n for n in nodes if n != str(seed)][:80]
            hits = []
            for kind, vals in (("device", seed_links["devices"]), ("phone", seed_links["phones"]),
                               ("ip", seed_links["ips"]), ("email", seed_links["emails"])):
                for v in vals[:5]:
                    try:
                        sharers = [a for a in _ds.accounts_sharing(kind, v, exclude=str(seed))
                                   if a in set(others)]
                    except Exception:
                        sharers = []
                    if sharers:
                        hits.append({"kind": kind, "value": v, "accounts": sharers[:10],
                                     "weight": weights.get(kind, 0.2)})
            if not hits:
                out.update({"reason": "no shared device/phone/ip/email with subgraph neighbors"})
                return out
            score = round(min(0.95, sum(h["weight"] for h in hits)), 2)
            out.update({"pattern_detected": True, "score": score,
                        "confidence": "HIGH" if score >= 0.5 else "MEDIUM",
                        "evidence": [{"note": f"shared {h['kind']} links {len(h['accounts'])} account(s); requires review",
                                      "kind": h["kind"], "accounts": h["accounts"]} for h in hits],
                        "metrics": {"link_types": len(hits), "linked_accounts": len({a for h in hits for a in h["accounts"]})},
                        "reason": "shared identity indicators observed; requires review"})
            return out
        except Exception:
            log.exception("shared identity lookup failed")
            out.update({"status": "UNAVAILABLE", "reason": "identity lookup error"})
            return out
    except Exception:
        log.exception("detect_shared_identity failed")
        out.update({"status": "UNAVAILABLE", "reason": "detector error"})
        return out


def run_all(sub, fallback: bool = False) -> dict:
    out = {}
    try:
        fns = {"mule_chain": detect_mule_chain, "fan_in": detect_fan_in, "fan_out": detect_fan_out,
               "circular_flow": detect_circular_flow, "rapid_layering": detect_rapid_layering,
               "shared_identity": detect_shared_identity}
        for k, fn in fns.items():
            try:
                out[k] = fn(sub)
            except Exception:
                log.exception("pattern %s failed", k)
                out[k] = {"pattern_detected": False, "score": 0.0, "confidence": "LOW",
                          "evidence": [], "metrics": {}, "status": "UNAVAILABLE", "reason": "detector error"}
        if fallback:
            for k in out:
                try:
                    if out[k].get("status") == "AVAILABLE":
                        out[k]["status"] = "SIZE_FALLBACK"
                        out[k]["reason"] = (out[k].get("reason") or "") + " [aggregate-only fallback; requires review]"
                except Exception:
                    continue
        return out
    except Exception:
        log.exception("run_all failed")
        return out
