"""A4 supernode registry service."""
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _db_path() -> Path:
    try:
        cfg = json.loads((REPO_ROOT / "config" / "a1.json").read_text())
        p = Path(str(cfg.get("db_path", "database/sentinel.db")))
    except Exception:
        log.exception("a1 config read failed, default db")
        p = Path("database/sentinel.db")
    if not p.is_absolute():
        p = REPO_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path()))
    c.row_factory = sqlite3.Row
    return c


def load_a4_config() -> dict:
    try:
        return json.loads((REPO_ROOT / "config" / "a4.json").read_text())
    except Exception:
        log.exception("a4 config read failed, defaults")
        return {"HUB_WHITELIST": [], "SUPERNODE_ABS_DEGREE": 500, "SUPERNODE_P95": 95, "SUPERNODE_P99": 99}


def init_supernode_table() -> None:
    try:
        with _conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS super_node_registry(
              entity_id TEXT PRIMARY KEY, entity_type TEXT NOT NULL,
              degree INTEGER NOT NULL, in_degree INTEGER NOT NULL, out_degree INTEGER NOT NULL,
              volume REAL NOT NULL, unique_counterparties INTEGER NOT NULL,
              percentile REAL NOT NULL, classification TEXT NOT NULL,
              is_whitelisted INTEGER NOT NULL, reason TEXT NOT NULL, updated TEXT NOT NULL);
            """)
        log.info("super_node_registry ready")
    except Exception:
        log.exception("init_supernode_table failed")
        raise


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def compute_supernodes(backend=None, config: dict | None = None) -> dict:
    try:
        cfg = config or load_a4_config()
        whitelist = set(str(x) for x in (cfg.get("HUB_WHITELIST") or []))
        abs_deg = int(cfg.get("SUPERNODE_ABS_DEGREE", 500))
        p95_cfg = float(cfg.get("SUPERNODE_P95", 95))
        p99_cfg = float(cfg.get("SUPERNODE_P99", 99))
        try:
            if backend is None:
                from app.graph.backend import get_backend
                backend = get_backend()
            g = backend.get_graph()
        except Exception:
            log.exception("compute_supernodes graph load failed")
            return {"nodes": 0, "super_nodes": []}
        try:
            import numpy as np
            degs = []
            info = {}
            for n in list(g.nodes()):
                try:
                    d = int(g.degree(n))
                except Exception:
                    d = 0
                degs.append(d)
                try:
                    ideg = int(g.in_degree(n))
                except Exception:
                    ideg = 0
                try:
                    odeg = int(g.out_degree(n))
                except Exception:
                    odeg = 0
                try:
                    vol = float(sum(float(dd.get("amount", 0) or 0) for _, _, dd in list(g.in_edges(n, data=True)) + list(g.out_edges(n, data=True))))
                except Exception:
                    vol = 0.0
                try:
                    cps = set([str(a) for a, _ in g.in_edges(n)] + [str(b) for _, b in g.out_edges(n)])
                    cps.discard(str(n))
                except Exception:
                    cps = set()
                info[str(n)] = (d, ideg, odeg, vol, len(cps))
            arr = np.array(degs, dtype=float) if degs else np.array([0.0])
            try:
                t95 = float(np.percentile(arr, p95_cfg)) if len(arr) else 0.0
            except Exception:
                t95 = 0.0
            try:
                t99 = float(np.percentile(arr, p99_cfg)) if len(arr) else 0.0
            except Exception:
                t99 = 0.0
        except Exception:
            log.exception("degree percentile failed")
            return {"nodes": 0, "super_nodes": []}
        supers = []
        try:
            with _conn() as c:
                for nid, (d, ideg, odeg, vol, ucp) in info.items():
                    try:
                        pct = float((float((arr <= d).sum()) / max(len(arr), 1)) * 100.0)
                    except Exception:
                        pct = 0.0
                    wl = 1 if nid in whitelist else 0
                    if wl:
                        cls, reason = "SUPER_NODE", "manual whitelist"
                    elif d >= abs_deg or d >= t99:
                        cls, reason = "SUPER_NODE", f"degree {d}>=abs {abs_deg} or p99 {t99:.1f}"
                    elif d >= t95:
                        cls, reason = "HIGH_DEGREE", f"degree {d}>=p95 {t95:.1f}"
                    else:
                        cls, reason = "NORMAL", "within normal degree"
                    try:
                        c.execute("INSERT OR REPLACE INTO super_node_registry VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                                  (nid, "ACCOUNT", d, ideg, odeg, vol, ucp, pct, cls, wl, reason, _now()))
                    except Exception:
                        log.exception("registry upsert failed for %s", nid)
                        continue
                    if cls == "SUPER_NODE":
                        supers.append(nid)
        except Exception:
            log.exception("registry write failed")
        log.info("supernodes=%d p95=%.1f p99=%.1f abs=%d", len(supers), t95, t99, abs_deg)
        return {"nodes": len(info), "super_nodes": supers, "p95": t95, "p99": t99}
    except Exception:
        log.exception("compute_supernodes failed")
        return {"nodes": 0, "super_nodes": []}


def is_hub(node: str, config: dict | None = None) -> bool:
    try:
        cfg = config or load_a4_config()
        wl = set(str(x) for x in (cfg.get("HUB_WHITELIST") or []))
        if str(node) in wl:
            return True
    except Exception:
        log.exception("whitelist check failed")
    try:
        with _conn() as c:
            r = c.execute("SELECT classification, is_whitelisted FROM super_node_registry WHERE entity_id=?", (str(node),)).fetchone()
        if not r:
            return False
        d = dict(r)
        return bool(d.get("is_whitelisted")) or str(d.get("classification")) == "SUPER_NODE"
    except Exception:
        log.exception("is_hub lookup failed for %s", node)
        return False


def get_super_nodes() -> list[dict]:
    try:
        with _conn() as c:
            rows = c.execute("SELECT * FROM super_node_registry WHERE classification='SUPER_NODE' ORDER BY degree DESC LIMIT 500").fetchall()
        return [dict(r) for r in rows]
    except Exception:
        log.exception("get_super_nodes failed")
        return []
