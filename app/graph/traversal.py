"""A4 bounded hub-aware BFS traversal."""
import logging
from collections import deque
from datetime import datetime, timedelta

log = logging.getLogger(__name__)


def _parse_ts(v):
    try:
        if v is None or v == "":
            return None
        if isinstance(v, datetime):
            return v
        return datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
    except Exception:
        return None


def bounded_bfs(graph, seed: str, seed_ts=None, max_hops: int = 4, max_nodes: int = 2000,
                window_hours: int = 72, is_hub_fn=None):
    try:
        seed = str(seed)
        try:
            sts = _parse_ts(seed_ts)
        except Exception:
            log.exception("seed ts parse failed")
            sts = None
        try:
            lo = sts - timedelta(hours=window_hours) if sts else None
            hi = sts + timedelta(hours=window_hours) if sts else None
        except Exception:
            log.exception("window compute failed")
            lo, hi = None, None
        if seed not in graph:
            log.warning("seed %s not in graph", seed)
            return ([seed], [], "FULL", False)
        try:
            def _edge_in_window(d):
                try:
                    if lo is None or hi is None:
                        return True
                    t = _parse_ts(d.get("timestamp"))
                    if t is None:
                        return True
                    tc = t.replace(tzinfo=None) if t.tzinfo else t
                    loc = lo.replace(tzinfo=None) if getattr(lo, "tzinfo", None) else lo
                    hic = hi.replace(tzinfo=None) if getattr(hi, "tzinfo", None) else hi
                    return loc <= tc <= hic
                except Exception:
                    return True
        except Exception:
            log.exception("window fn failed")
            def _edge_in_window(d):
                return True
        visited = {seed: 0}
        post_hub = {seed: 0}
        via_hub_seen = False
        edges = []
        seen_edge_keys = set()
        q = deque([seed])
        truncated = False
        try:
            while q:
                cur = q.popleft()
                try:
                    depth = visited[cur]
                except Exception:
                    depth = 0
                try:
                    cur_is_hub = bool(is_hub_fn(cur)) if is_hub_fn else False
                except Exception:
                    log.exception("is_hub check failed for %s", cur)
                    cur_is_hub = False
                try:
                    ph = post_hub.get(cur, 0)
                except Exception:
                    ph = 0
                if depth >= max_hops:
                    continue
                if cur_is_hub and ph >= 1 and cur != seed:
                    continue
                try:
                    nbrs = set()
                    try:
                        nbrs.update(graph.successors(cur))
                    except Exception:
                        pass
                    try:
                        nbrs.update(graph.predecessors(cur))
                    except Exception:
                        pass
                except Exception:
                    log.exception("neighbor fetch failed for %s", cur)
                    continue
                for nb in list(nbrs):
                    try:
                        nb = str(nb)
                        edata = None
                        direction = "out"
                        try:
                            if graph.has_edge(cur, nb):
                                edata = graph.get_edge_data(cur, nb) or {}
                                direction = "out"
                            elif graph.has_edge(nb, cur):
                                edata = graph.get_edge_data(nb, cur) or {}
                                direction = "in"
                            else:
                                continue
                        except Exception:
                            continue
                        if not _edge_in_window(edata or {}):
                            continue
                        try:
                            hub_touch = cur_is_hub or (bool(is_hub_fn(nb)) if is_hub_fn else False)
                        except Exception:
                            hub_touch = cur_is_hub
                        if hub_touch:
                            via_hub_seen = True
                        ekey = (str(cur), str(nb), str((edata or {}).get("txn", "")))
                        if ekey not in seen_edge_keys:
                            seen_edge_keys.add(ekey)
                            try:
                                edges.append({"source": str(cur if direction == "out" else nb),
                                              "target": str(nb if direction == "out" else cur),
                                              "txn": str((edata or {}).get("txn", "")),
                                              "amount": float((edata or {}).get("amount", 0) or 0),
                                              "timestamp": str((edata or {}).get("timestamp", "")),
                                              "risk": float((edata or {}).get("risk", 0) or 0),
                                              "via_hub": bool(hub_touch),
                                              "hub_edge": bool(hub_touch)})
                            except Exception:
                                log.exception("edge record failed")
                        if nb not in visited:
                            if len(visited) >= max_nodes:
                                truncated = True
                                break
                            visited[nb] = depth + 1
                            try:
                                if cur_is_hub:
                                    post_hub[nb] = ph + 1
                                elif ph > 0:
                                    post_hub[nb] = ph
                                else:
                                    post_hub[nb] = 0
                            except Exception:
                                post_hub[nb] = 0
                            if not (cur_is_hub and post_hub.get(nb, 0) > 1):
                                q.append(nb)
                        if len(visited) >= max_nodes:
                            truncated = True
                            break
                    except Exception:
                        log.exception("bfs neighbor loop failed")
                        continue
                if truncated or len(visited) >= max_nodes:
                    truncated = len(visited) >= max_nodes
                    break
        except Exception:
            log.exception("bfs loop failed")
        mode = "SIZE_FALLBACK" if truncated else "FULL"
        nodes = list(visited.keys())
        log.info("bfs seed=%s nodes=%d edges=%d mode=%s via_hub=%s", seed, len(nodes), len(edges), mode, via_hub_seen)
        return (nodes, edges, mode, bool(truncated))
    except Exception:
        log.exception("bounded_bfs failed")
        return ([str(seed)], [], "FULL", False)


def build_subgraph(graph, nodes, edges):
    try:
        import networkx as nx
        sub = nx.DiGraph()
        try:
            for n in nodes:
                try:
                    sub.add_node(str(n), **dict(graph.nodes[n] if n in graph.nodes else {}))
                except Exception:
                    sub.add_node(str(n))
        except Exception:
            log.exception("subgraph nodes failed")
        try:
            for e in edges:
                try:
                    sub.add_edge(str(e["source"]), str(e["target"]),
                                 txn=e.get("txn", ""), amount=float(e.get("amount", 0) or 0),
                                 timestamp=e.get("timestamp", ""), risk=float(e.get("risk", 0) or 0),
                                 via_hub=bool(e.get("via_hub", False)), hub_edge=bool(e.get("hub_edge", False)))
                except Exception:
                    log.exception("subgraph edge failed, skipping")
                    continue
        except Exception:
            log.exception("subgraph edges failed")
        return sub
    except Exception:
        log.exception("build_subgraph failed")
        import networkx as nx
        return nx.DiGraph()
