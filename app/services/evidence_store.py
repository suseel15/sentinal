"""SQLite store for A3 evidence items, sources, summaries."""
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
    except (FileNotFoundError, json.JSONDecodeError):
        p = Path("database/sentinel.db")
    if not p.is_absolute():
        p = REPO_ROOT / p
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(str(_db_path()))
    c.row_factory = sqlite3.Row
    return c


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_SEED_SOURCES = [
    ("INTERNAL_TXN_HISTORY", "T1", "AVAILABLE"),
    ("ACCOUNT_PROFILE", "T1", "AVAILABLE"),
    ("A2_RESULT", "T1", "AVAILABLE"),
    ("INVESTIGATION_DB", "T1", "AVAILABLE"),
    ("DEVICE_DATA", "T4", "UNAVAILABLE"),
    ("LOCATION_DATA", "T4", "UNAVAILABLE"),
]


def init() -> None:
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS evidence_items(
          evidence_id TEXT PRIMARY KEY, investigation_id TEXT NOT NULL,
          transaction_id TEXT NOT NULL, type TEXT NOT NULL, direction TEXT NOT NULL,
          title TEXT NOT NULL, description TEXT NOT NULL, actual TEXT, comparison TEXT,
          confidence REAL NOT NULL, source TEXT NOT NULL, tier TEXT NOT NULL,
          status TEXT NOT NULL, created TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_evidence_inv ON evidence_items(investigation_id);
        CREATE TABLE IF NOT EXISTS evidence_sources(
          source_name TEXT PRIMARY KEY, tier TEXT NOT NULL,
          last_updated TEXT NOT NULL, availability TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence_summary(
          inv_id TEXT PRIMARY KEY, total INTEGER NOT NULL, supporting INTEGER NOT NULL,
          contradicting INTEGER NOT NULL, avg_confidence REAL NOT NULL,
          completeness REAL NOT NULL, status TEXT NOT NULL, generated_at TEXT NOT NULL);
        """)
        for name, tier, avail in _SEED_SOURCES:
            try:
                c.execute(
                    "INSERT OR IGNORE INTO evidence_sources VALUES(?,?,?,?)",
                    (name, tier, _now(), avail),
                )
            except Exception:
                log.exception("seed source failed: %s", name)
    log.info("init evidence tables ok at %s", _db_path())


def init_evidence_db() -> None:
    init()


def _ser(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v
    try:
        return json.dumps(v, default=str)
    except Exception:
        return str(v)


def save_evidence_pack(pack) -> None:
    try:
        d = pack.model_dump() if hasattr(pack, "model_dump") else dict(pack)
    except Exception:
        log.exception("save_evidence_pack: bad pack")
        raise ValueError("invalid evidence pack")
    inv_id = d.get("investigation_id", "")
    txn_id = d.get("transaction_id", "") or ""
    status = d.get("status", "PARTIAL")
    items = d.get("evidence") or []
    summary = d.get("evidence_summary") or {}
    total = int(summary.get("total", len(items)))
    supporting = int(summary.get("supporting", 0))
    contradicting = int(summary.get("contradicting", 0))
    avg_conf = float(summary.get("avg_confidence", 0.0) or 0.0)
    completeness = float(summary.get("completeness", 0.0) or 0.0)
    with _conn() as c:
        c.execute("DELETE FROM evidence_items WHERE investigation_id=?", (inv_id,))
        for it in items:
            try:
                r = it.model_dump() if hasattr(it, "model_dump") else dict(it)
            except Exception:
                continue
            try:
                c.execute(
                    "INSERT OR REPLACE INTO evidence_items VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        str(r.get("evidence_id", "")),
                        inv_id,
                        txn_id,
                        str(r.get("type", "")),
                        str(r.get("direction", "NEUTRAL")),
                        str(r.get("title", "")),
                        str(r.get("description", "")),
                        _ser(r.get("actual_value")),
                        _ser(r.get("comparison_value")),
                        float(r.get("confidence", 0.0) or 0.0),
                        str(r.get("source", "")),
                        str(r.get("source_tier", "T1")),
                        str(r.get("status", "AVAILABLE")),
                        _now(),
                    ),
                )
            except Exception:
                log.exception("save evidence item failed")
        try:
            c.execute(
                "INSERT OR REPLACE INTO evidence_summary VALUES(?,?,?,?,?,?,?,?)",
                (inv_id, total, supporting, contradicting, avg_conf, completeness, status, _now()),
            )
        except Exception:
            log.exception("save evidence summary failed")
            raise
    log.info("saved evidence pack %s items=%d status=%s", inv_id, len(items), status)


def _row_to_item(r: dict) -> dict:
    def _deser(v):
        if v is None:
            return None
        try:
            return json.loads(v)
        except (TypeError, json.JSONDecodeError):
            return v
    return {
        "evidence_id": r.get("evidence_id", ""),
        "type": r.get("type", ""),
        "direction": r.get("direction", "NEUTRAL"),
        "title": r.get("title", ""),
        "description": r.get("description", ""),
        "actual_value": _deser(r.get("actual")),
        "comparison_value": _deser(r.get("comparison")),
        "confidence": float(r.get("confidence", 0.0) or 0.0),
        "source": r.get("source", ""),
        "source_tier": r.get("tier", "T1"),
        "status": r.get("status", "AVAILABLE"),
    }


def get_timeline(inv_id: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM evidence_items WHERE investigation_id=? ORDER BY created ASC",
            (inv_id,),
        ).fetchall()
    return [_row_to_item(dict(r)) for r in rows]


def get_summary(inv_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM evidence_summary WHERE inv_id=?", (inv_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    return {
        "investigation_id": inv_id,
        "total": int(d.get("total", 0)),
        "supporting": int(d.get("supporting", 0)),
        "contradicting": int(d.get("contradicting", 0)),
        "avg_confidence": float(d.get("avg_confidence", 0.0) or 0.0),
        "completeness": float(d.get("completeness", 0.0) or 0.0),
        "status": str(d.get("status", "PARTIAL")),
        "generated_at": str(d.get("generated_at", "")),
    }


def get_pack(inv_id: str) -> dict | None:
    summary = get_summary(inv_id)
    if not summary:
        return None
    items = get_timeline(inv_id)
    txn_id = ""
    try:
        with _conn() as c:
            r = c.execute(
                "SELECT transaction_id FROM evidence_items WHERE investigation_id=? LIMIT 1",
                (inv_id,),
            ).fetchone()
            if r:
                txn_id = str(dict(r).get("transaction_id", ""))
    except Exception:
        log.exception("get_pack txn lookup failed")
    limitations: list[str] = []
    for it in items:
        if it.get("status") == "UNAVAILABLE":
            limitations.append(f"{it.get('type')}: unavailable ({it.get('description','')[:160]})")
    limitations.append("Risk scores referenced from stored A2 result only; never recalculated.")
    limitations.append("Findings are indicative only and do not assert fraud.")
    return {
        "investigation_id": inv_id,
        "agent": "A3",
        "status": summary.get("status", "PARTIAL"),
        "evidence_summary": {
            "total": summary["total"],
            "supporting": summary["supporting"],
            "contradicting": summary["contradicting"],
            "avg_confidence": summary["avg_confidence"],
            "completeness": summary["completeness"],
            "status": summary["status"],
        },
        "evidence": items,
        "limitations": limitations,
        "transaction_id": txn_id,
    }


def get_transaction_by_inv(inv_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM transactions WHERE inv_id=?", (inv_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["payload"] = json.loads(d["payload"]) if isinstance(d.get("payload"), str) else d.get("payload")
    except (TypeError, json.JSONDecodeError):
        pass
    return d


def find_account_investigations(account_id: str) -> list[dict]:
    out: list[dict] = []
    try:
        with _conn() as c:
            txns = c.execute("SELECT txn_id, inv_id, payload FROM transactions").fetchall()
            invs = {dict(r)["inv_id"]: dict(r) for r in c.execute("SELECT * FROM investigations").fetchall()}
    except Exception:
        log.exception("find_account_investigations query failed")
        return out
    for t in txns:
        try:
            td = dict(t)
            payload = json.loads(td["payload"]) if isinstance(td.get("payload"), str) else (td.get("payload") or {})
            canon = (payload.get("canonical") or {}) if isinstance(payload, dict) else {}
            if str(canon.get("source_account", "")) != str(account_id):
                continue
            inv = invs.get(td["inv_id"], {})
            result = {}
            try:
                result = json.loads(inv.get("result")) if isinstance(inv.get("result"), str) else (inv.get("result") or {})
            except (TypeError, json.JSONDecodeError):
                result = {}
            out.append({
                "inv_id": td["inv_id"],
                "txn_id": td["txn_id"],
                "status": str(inv.get("status", "UNKNOWN")),
                "risk_score": result.get("risk_score"),
                "risk_level": result.get("risk_level"),
            })
        except Exception:
            log.exception("find_account row parse failed")
            continue
    return out
