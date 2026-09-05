"""A4 offline community compute + lookup (lazy, 60s cap)."""
import json
import logging
import sqlite3
import threading
from pathlib import Path

log = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _db_path() -> Path:
    try:
        cfg = json.loads((REPO_ROOT / "config" / "a1.json").read_text())
        p = Path(str(cfg.get("db_path", "database/sentinel.db")))
    except Exception:
        p = Path("database/sentinel.db")
    if not p.is_absolute():
        p = REPO_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path()))
    c.row_factory = sqlite3.Row
    return c


def init_community_table() -> None:
    try:
        with _conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS graph_communities(
              node_id TEXT PRIMARY KEY, community_id INTEGER NOT NULL, pagerank REAL NOT NULL);
            """)
        log.info("graph_communities ready")
    except Exception:
        log.exception("init_community_table failed")
        raise


def _compute(graph) -> dict:
    comm, pr = {}, {}
    try:
        from networkx.algorithms.community import greedy_modularity_communities
        try:
            ug = graph.to_undirected()
            for i, c in enumerate(greedy_modularity_communities(ug)):
                for n in c:
                    comm[str(n)] = int(i)
        except Exception:
            log.exception("modularity failed")
    except Exception:
        log.exception("community import failed")
    try:
        import networkx as nx
        try:
            pr = {str(k): float(v) for k, v in nx.pagerank(graph, weight="amount").items()}
        except Exception:
            try:
                pr = {str(k): float(v) for k, v in nx.pagerank(graph).items()}
            except Exception:
                log.exception("pagerank failed")
    except Exception:
        log.exception("pagerank import failed")
    return comm, pr


def ensure_communities(graph=None, timeout_s: int = 60) -> dict:
    try:
        with _conn() as c:
            n = c.execute("SELECT COUNT(*) AS n FROM graph_communities").fetchone()
            if n and dict(n)["n"] > 0:
                return {"cached": True, "rows": dict(n)["n"]}
    except Exception:
        log.exception("community count failed")
    try:
        if graph is None:
            from app.graph.backend import get_backend
            try:
                graph = get_backend().get_graph()
            except Exception:
                log.exception("backend graph load failed")
                return {"cached": False, "rows": 0}
    except Exception:
        return {"cached": False, "rows": 0}
    result: dict = {}
    def _work():
        try:
            comm, pr = _compute(graph)
            nodes = list(graph.nodes())
            with _conn() as c:
                for nd in nodes:
                    try:
                        c.execute("INSERT OR REPLACE INTO graph_communities VALUES(?,?,?)",
                                  (str(nd), int(comm.get(str(nd), -1)), float(pr.get(str(nd), 0.0))))
                    except Exception:
                        continue
            result.update({"rows": len(nodes)})
        except Exception:
            log.exception("community work failed")
    try:
        t = threading.Thread(target=_work, daemon=True)
        t.start()
        t.join(timeout=timeout_s)
        if t.is_alive():
            log.warning("community compute capped at %ss", timeout_s)
            return {"cached": False, "rows": 0, "capped": True}
    except Exception:
        log.exception("community thread failed")
        return {"cached": False, "rows": 0}
    return {"cached": False, "rows": result.get("rows", 0)}


def lookup(node_ids: list) -> dict:
    try:
        if not node_ids:
            return {}
        out = {}
        try:
            with _conn() as c:
                for nid in node_ids:
                    try:
                        r = c.execute("SELECT community_id, pagerank FROM graph_communities WHERE node_id=?", (str(nid),)).fetchone()
                        if r:
                            d = dict(r)
                            out[str(nid)] = {"community_id": d["community_id"], "pagerank": d["pagerank"]}
                    except Exception:
                        continue
        except Exception:
            log.exception("community lookup failed")
            return {}
        if not out:
            try:
                ensure_communities(timeout_s=60)
            except Exception:
                log.exception("lazy community compute failed")
            try:
                with _conn() as c:
                    for nid in node_ids:
                        try:
                            r = c.execute("SELECT community_id, pagerank FROM graph_communities WHERE node_id=?", (str(nid),)).fetchone()
                            if r:
                                d = dict(r)
                                out[str(nid)] = {"community_id": d["community_id"], "pagerank": d["pagerank"]}
                        except Exception:
                            continue
            except Exception:
                pass
        return out
    except Exception:
        log.exception("lookup failed")
        return {}
