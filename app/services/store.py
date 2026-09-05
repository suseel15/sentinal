"""SQLite store for A1 transactions, investigations, audit events."""
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


def init_db() -> None:
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS transactions(
          fingerprint TEXT PRIMARY KEY, txn_id TEXT NOT NULL, inv_id TEXT NOT NULL,
          payload TEXT NOT NULL, triage TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS investigations(
          inv_id TEXT PRIMARY KEY, txn_id TEXT NOT NULL, status TEXT NOT NULL,
          result TEXT, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit_events(
          id INTEGER PRIMARY KEY AUTOINCREMENT, inv_id TEXT NOT NULL,
          actor TEXT NOT NULL, event TEXT NOT NULL, at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS stream_progress(
          key TEXT PRIMARY KEY, offset INT NOT NULL);
        """)
    init_phase7_tables()
    log.info("init_db ok at %s", _db_path())


def save_transaction(fingerprint: str, txn_id: str, inv_id: str, payload: dict, triage: str) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO transactions VALUES(?,?,?,?,?,?)",
                  (fingerprint, txn_id, inv_id, json.dumps(payload, default=str), triage, _now()))


def get_by_fingerprint(fingerprint: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM transactions WHERE fingerprint=?", (fingerprint,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["payload"] = json.loads(d["payload"])
    except (TypeError, json.JSONDecodeError):
        pass
    return d


def save_investigation(inv_id: str, txn_id: str, status: str, result: dict | None = None) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO investigations VALUES(?,?,?, ?,?)",
                  (inv_id, txn_id, status, json.dumps(result or {}, default=str), _now()))


def get_investigation(inv_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM investigations WHERE inv_id=?", (inv_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["result"] = json.loads(d["result"]) if d.get("result") else {}
    except (TypeError, json.JSONDecodeError):
        d["result"] = {}
    return d


def log_event(inv_id: str, actor: str, event: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO audit_events(inv_id, actor, event, at) VALUES(?,?,?,?)",
                  (inv_id, actor, event, _now()))


def list_investigations(status: str | None = None, limit: int = 200) -> list:
    with _conn() as c:
        if status:
            rows = c.execute("SELECT * FROM investigations WHERE status=? ORDER BY updated DESC LIMIT ?",
                             (status, limit)).fetchall()
        else:
            rows = c.execute("SELECT * FROM investigations ORDER BY updated DESC LIMIT ?",
                             (limit,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        try:
            d["result"] = json.loads(d["result"]) if d.get("result") else {}
        except (TypeError, json.JSONDecodeError):
            d["result"] = {}
        out.append(d)
    return out


def init_phase7_tables() -> None:
    """Phase 7 canonical investigation state + agent sections + human decisions + feedback."""
    with _conn() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS investigation_state(
          inv_id TEXT PRIMARY KEY, txn_id TEXT NOT NULL, status TEXT NOT NULL,
          risk_score REAL, risk_level TEXT,
          payload TEXT NOT NULL, updated TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS agent_sections(
          inv_id TEXT NOT NULL, agent TEXT NOT NULL, section TEXT NOT NULL,
          payload TEXT NOT NULL, updated TEXT NOT NULL,
          PRIMARY KEY(inv_id, agent, section));
        CREATE TABLE IF NOT EXISTS human_decisions(
          inv_id TEXT PRIMARY KEY, investigator_id TEXT NOT NULL,
          decision TEXT NOT NULL, original_recommendation TEXT,
          justification TEXT, decided_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS feedback_dataset(
          inv_id TEXT PRIMARY KEY, txn_id TEXT NOT NULL,
          features TEXT, original_risk REAL, ml_predictions TEXT,
          rules_triggered TEXT, graph_features TEXT,
          recommendation TEXT, human_decision TEXT,
          confirmed_outcome TEXT, stored_at TEXT NOT NULL);
        """)
    log.info("phase7 tables ready")


def save_state(inv_id: str, txn_id: str, status: str, risk_score: float | None,
               risk_level: str | None, payload: dict | None = None) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO investigation_state VALUES(?,?,?,?,?, ?,?)",
                  (inv_id, txn_id, status, risk_score, risk_level,
                   json.dumps(payload or {}, default=str), _now()))


def update_status(inv_id: str, status: str, risk_score: float | None = None,
                  risk_level: str | None = None) -> None:
    with _conn() as c:
        if risk_score is not None and risk_level is not None:
            c.execute("UPDATE investigation_state SET status=?, risk_score=?, risk_level=?, updated=? WHERE inv_id=?",
                      (status, risk_score, risk_level, _now(), inv_id))
        else:
            c.execute("UPDATE investigation_state SET status=?, updated=? WHERE inv_id=?",
                      (status, _now(), inv_id))
        try:
            cur = c.execute("SELECT result FROM investigations WHERE inv_id=?", (inv_id,)).fetchone()
            res = json.loads(cur[0]) if cur and cur[0] else {}
            if not isinstance(res, dict):
                res = {}
            if risk_score is not None:
                res["risk_score"] = risk_score
            if risk_level is not None:
                res["risk_level"] = risk_level
            c.execute("UPDATE investigations SET status=?, result=?, updated=? WHERE inv_id=?",
                      (status, json.dumps(res, default=str), _now(), inv_id))
        except Exception:
            log.exception("investigations mirror update failed")
    try:
        from app.services import supabase_realtime
        supabase_realtime.publish_status(inv_id, status, risk_score, risk_level)
    except Exception:
        log.exception("realtime publish failed")


def save_section(inv_id: str, agent: str, section: str, payload: dict) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO agent_sections VALUES(?,?,?,?,?)",
                  (inv_id, agent, section, json.dumps(payload or {}, default=str), _now()))


def get_section(inv_id: str, agent: str, section: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT payload FROM agent_sections WHERE inv_id=? AND agent=? AND section=?",
                      (inv_id, agent, section)).fetchone()
    if not r:
        return None
    try:
        return json.loads(r["payload"])
    except Exception:
        return None


def get_state(inv_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM investigation_state WHERE inv_id=?", (inv_id,)).fetchone()
    if not r:
        return None
    d = dict(r)
    try:
        d["payload"] = json.loads(d.get("payload") or "{}")
    except Exception:
        d["payload"] = {}
    return d


def list_all_sections(inv_id: str) -> dict:
    with _conn() as c:
        rows = c.execute("SELECT agent, section, payload FROM agent_sections WHERE inv_id=?", (inv_id,)).fetchall()
    out: dict = {}
    for r in rows:
        out.setdefault(r["agent"], {})[r["section"]] = _safe_json(r["payload"])
    return out


def _safe_json(s: str):
    try:
        return json.loads(s)
    except Exception:
        return {}


def save_human_decision(inv_id: str, investigator_id: str, decision: str,
                        original_recommendation: str | None, justification: str | None) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO human_decisions VALUES(?,?,?,?,?,?)",
                  (inv_id, investigator_id, decision, original_recommendation or "",
                   justification or "", _now()))


def get_human_decision(inv_id: str) -> dict | None:
    with _conn() as c:
        r = c.execute("SELECT * FROM human_decisions WHERE inv_id=?", (inv_id,)).fetchone()
    return dict(r) if r else None


def save_feedback(inv_id: str, txn_id: str, features: dict | None,
                  original_risk: float | None, ml_predictions: dict | None,
                  rules_triggered: dict | None, graph_features: dict | None,
                  recommendation: str | None, human_decision: str | None,
                  confirmed_outcome: str | None) -> None:
    with _conn() as c:
        c.execute("INSERT OR REPLACE INTO feedback_dataset VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                  (inv_id, txn_id,
                   json.dumps(features or {}, default=str),
                   float(original_risk or 0),
                   json.dumps(ml_predictions or {}, default=str),
                   json.dumps(rules_triggered or {}, default=str),
                   json.dumps(graph_features or {}, default=str),
                   str(recommendation or ""),
                   str(human_decision or ""),
                   str(confirmed_outcome or ""),
                   _now()))


def _ensure_stream_table(c) -> None:
    c.execute("CREATE TABLE IF NOT EXISTS stream_progress(key TEXT PRIMARY KEY, offset INT NOT NULL)")


def get_stream_offset(key: str = "default") -> int:
    with _conn() as c:
        _ensure_stream_table(c)
        r = c.execute("SELECT offset FROM stream_progress WHERE key=?", (key,)).fetchone()
    try:
        return int(r["offset"]) if r else 0
    except (TypeError, ValueError):
        return 0


def set_stream_offset(offset: int, key: str = "default") -> None:
    with _conn() as c:
        _ensure_stream_table(c)
        c.execute("INSERT OR REPLACE INTO stream_progress VALUES(?,?)", (key, int(offset)))
