"""A4 graph analysis SQLite tables."""
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
        p = Path("database/sentinel.db")
    if not p.is_absolute():
        p = REPO_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path()))
    c.row_factory = sqlite3.Row
    return c


def init_graph_tables() -> None:
    try:
        with _conn() as c:
            c.executescript("""
            CREATE TABLE IF NOT EXISTS graph_analysis(
              investigation_id TEXT PRIMARY KEY, analysis_mode TEXT NOT NULL,
              status TEXT NOT NULL, node_count INTEGER NOT NULL, edge_count INTEGER NOT NULL,
              graph_risk_score REAL NOT NULL, risk_level TEXT NOT NULL,
              result TEXT NOT NULL, updated TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS graph_patterns(
              investigation_id TEXT NOT NULL, pattern TEXT NOT NULL,
              detected INTEGER NOT NULL, score REAL NOT NULL,
              detail TEXT NOT NULL, PRIMARY KEY(investigation_id, pattern));
            """)
        log.info("graph_analysis tables ready")
    except Exception:
        log.exception("init_graph_tables failed")
        raise


def save_analysis(result: dict) -> None:
    try:
        inv = str(result.get("investigation_id", ""))
        now = datetime.now(timezone.utc).isoformat()
        with _conn() as c:
            try:
                c.execute("INSERT OR REPLACE INTO graph_analysis VALUES(?,?,?,?,?,?,?, ?,?)",
                          (inv, str(result.get("analysis_mode", "FULL")), str(result.get("status", "COMPLETE")),
                           int(result.get("node_count", 0)), int(result.get("edge_count", 0)),
                           float(result.get("graph_risk_score", 0) or 0), str(result.get("risk_level", "LOW")),
                           json.dumps(result, default=str), now))
            except Exception:
                log.exception("graph_analysis save failed for %s", inv)
            try:
                for k, v in (result.get("patterns") or {}).items():
                    try:
                        c.execute("INSERT OR REPLACE INTO graph_patterns VALUES(?,?,?,?,?)",
                                  (inv, str(k), 1 if (v or {}).get("pattern_detected") else 0,
                                   float((v or {}).get("score", 0) or 0), json.dumps(v, default=str)))
                    except Exception:
                        log.exception("pattern save failed %s", k)
                        continue
            except Exception:
                log.exception("patterns save failed")
    except Exception:
        log.exception("save_analysis failed")


def get_analysis(inv_id: str) -> dict | None:
    try:
        with _conn() as c:
            r = c.execute("SELECT * FROM graph_analysis WHERE investigation_id=?", (inv_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["result"] = json.loads(d.get("result") or "{}")
        except Exception:
            d["result"] = {}
        return d
    except Exception:
        log.exception("get_analysis failed for %s", inv_id)
        return None


def get_txn_by_inv(inv_id: str) -> dict | None:
    try:
        with _conn() as c:
            r = c.execute("SELECT * FROM transactions WHERE inv_id=?", (inv_id,)).fetchone()
        if not r:
            return None
        d = dict(r)
        try:
            d["payload"] = json.loads(d.get("payload") or "{}")
        except Exception:
            pass
        return d
    except Exception:
        log.exception("get_txn_by_inv failed")
        return None
