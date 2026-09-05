"""A2 bridge: map canonical -> SENTINEL inference row, then run A2DetectionAgent.

The new agent (`a2_detection_fusion.py`) is the single owner of risk_score.
This file remains a thin façade for backwards compatibility with the
existing orchestrator and notebooks.
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LABELED_CSV = REPO_ROOT / "labeled_transactions.csv"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CREDIT_TYPES = {"CREDIT", "INCOMING", "DEPOSIT", "SALARY", "REFUND", "CASHBACK"}


def _ts(v) -> datetime:
    if isinstance(v, datetime):
        return v
    return datetime.fromisoformat(str(v).replace("Z", "+00:00"))


_HIST_CACHE: dict = {}


def _db_history(account_id: str):
    """Previously-ingested live transactions for this account (DB > CSV recency)."""
    try:
        import json as _j
        from app.services import store as _st
        import sqlite3
        rows = []
        with sqlite3.connect(str(_st._db_path())) as c:
            c.row_factory = sqlite3.Row
            for r in c.execute("SELECT payload FROM transactions").fetchall():
                try:
                    can = (_j.loads(r[0]) or {}).get("canonical") or {}
                    if str(can.get("source_account", "")) != str(account_id):
                        continue
                    rows.append({"account_id": can.get("source_account"),
                                 "counterparty_name": can.get("destination_account", "UNK"),
                                 "transaction_id": can.get("transaction_id", ""),
                                 "date": can.get("timestamp"), "amount": can.get("amount", 0),
                                 "type": "DEBIT", "category": "TRANSFER"})
                except Exception:
                    continue
        return rows
    except Exception:
        log.exception("db history failed")
        return []


def _history(account_id: str, ts: datetime, n: int = 20):
    try:
        import pandas as pd
        frames = []
        if LABELED_CSV.exists():
            df = _HIST_CACHE.get("df")
            if df is None:
                df = pd.read_csv(LABELED_CSV, usecols=["account_id", "counterparty_name", "transaction_id",
                                                       "date", "amount", "type", "category"],
                                 low_memory=True)
                df["_d"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
                _HIST_CACHE["df"] = df
            sub = df[df["account_id"] == account_id]
            if not sub.empty:
                frames.append(sub)
        try:
            db_rows = _db_history(str(account_id))
            if db_rows:
                db = pd.DataFrame(db_rows)
                db["_d"] = pd.to_datetime(db["date"], errors="coerce", format="mixed")
                frames.append(db)
        except Exception:
            log.exception("db history merge failed")
        if not frames:
            return None
        sub = pd.concat(frames, ignore_index=True)
        ts_cmp = pd.Timestamp(ts)
        if ts_cmp.tzinfo is not None:
            ts_cmp = ts_cmp.tz_convert(None)
        sub = sub[sub["_d"] < ts_cmp].sort_values("_d").tail(n).drop(columns=["_d"])
        return sub if len(sub) else None
    except Exception:
        log.exception("history lookup failed for %s", account_id)
        return None


def run(canonical: dict) -> dict:
    """Run the multi-layer A2 detection agent on a canonical transaction."""
    from app.agents.a2_detection_fusion import A2DetectionAgent

    ttype_raw = str(canonical.get("transaction_type", "DEBIT") or "DEBIT").upper()
    is_credit = ttype_raw in CREDIT_TYPES
    a2_type = "CREDIT" if is_credit else "DEBIT"
    amt = abs(float(canonical.get("amount", 0) or 0))
    ts_raw = canonical.get("timestamp")
    ts_dt = _ts(ts_raw) if ts_raw is not None else datetime.now()
    canon = {
        **canonical,
        "transaction_type": a2_type,
        "amount": amt,
        "timestamp": ts_dt.isoformat(),
    }
    hist = _history(str(canonical.get("source_account", "UNK")), ts_dt)
    agent = A2DetectionAgent()
    result = agent.run(canon, history_df=hist)
    log.info(
        "A2 run %s risk=%s level=%s rules=%s ml=%s",
        result.get("transaction_id"),
        result.get("risk_score"),
        result.get("risk_level"),
        (result.get("rules") or {}).get("rule_count"),
        not result.get("ml_unavailable", False),
    )
    return result