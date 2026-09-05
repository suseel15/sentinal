"""Similar-investigation retrieval.

For every new investigation we generate a compact fingerprint and
search past investigations stored in SQLite (`investigations` table).
If sentence-transformers + pgvector are unavailable we fall back to a
deterministic fingerprint cosine over a small set of engineered features,
which is enough to demonstrate the pipeline end-to-end.
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _store_db_path() -> Path:
    try:
        from app.services.store import _db_path
        return _db_path()
    except Exception:
        return REPO_ROOT / "sentinel.db"


def _fingerprint(canonical: dict, a2: dict) -> list[float]:
    """Build a small numerical fingerprint of the investigation."""
    amt = float(canonical.get("amount") or 0.0)
    log_amt = math.log10(abs(amt) + 1.0)
    a2_models = (a2 or {}).get("model_outputs") or {}
    return [
        log_amt / 7.0,
        float(a2_models.get("xgboost") or 0.0),
        float(a2_models.get("isolation_forest") or 0.0),
        float(a2_models.get("behavioral") or 0.0),
        float(a2_models.get("rules") or 0.0),
        min(1.0, float((a2.get("rules") or {}).get("rule_count") or 0) / 8.0),
        min(1.0, len(a2.get("detected_typologies") or []) / 5.0),
    ]


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def find_similar(canonical: dict, a2: dict, top_k: int = 5, exclude_self: str | None = None) -> list[dict[str, Any]]:
    """Return up to `top_k` similar past investigations.

    Reads from Phase 7's `investigation_state` + `agent_sections` tables.
    """
    fp = _fingerprint(canonical, a2)
    db = _store_db_path()
    if not db.exists():
        return []
    rows: list[dict[str, Any]] = []
    try:
        with sqlite3.connect(str(db)) as conn:
            conn.row_factory = sqlite3.Row
            # Read state + per-investigation A2 section from agent_sections.
            cur = conn.execute(
                "SELECT inv_id, txn_id, status, risk_score, risk_level, payload "
                "FROM investigation_state ORDER BY updated DESC LIMIT 500"
            )
            state_rows = [dict(r) for r in cur.fetchall()]
            cur2 = conn.execute(
                "SELECT inv_id, payload FROM agent_sections WHERE agent='A2' AND section='detection'"
            )
            a2_by_inv = {str(r["inv_id"]): (json.loads(r["payload"]) if r["payload"] else {}) for r in cur2.fetchall()}
            for r in state_rows:
                inv_id = str(r["inv_id"])
                if exclude_self and inv_id == exclude_self:
                    continue
                other_a2 = a2_by_inv.get(inv_id) or {}
                # canonical for fingerprint
                try:
                    payload = json.loads(r.get("payload") or "{}") or {}
                except Exception:
                    payload = {}
                other_canon = payload.get("canonical") or {}
                other_fp = _fingerprint(other_canon, other_a2)
                sim = _cosine(fp, other_fp)
                rows.append({
                    "investigation_id": inv_id,
                    "txn_id": r["txn_id"],
                    "status": r["status"],
                    "risk_score": r["risk_score"],
                    "risk_level": r["risk_level"],
                    "similarity_score": round(sim, 3),
                    "matching_typology": (other_a2.get("detected_typologies") or
                                           other_a2.get("possible_typologies") or
                                           [None])[0],
                })
    except Exception:
        log.exception("similar case query failed")
        return []
    rows.sort(key=lambda x: x.get("similarity_score") or 0.0, reverse=True)
    return rows[:top_k]