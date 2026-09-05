"""A1 ingestion agent: validate -> normalize -> dedup -> triage -> (A2) -> store. Only A1 creates IDs."""
import logging
import uuid
from datetime import datetime
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LABELED_CSV = REPO_ROOT / "labeled_transactions.csv"

from app.preprocessing.validator import validate_raw
from app.preprocessing.normalizer import normalize
from app.preprocessing.deduplication import fingerprint
from app.triage.prefilter import score, decision
from app.services.store import (init_db, save_transaction, get_by_fingerprint,
                                save_investigation, get_investigation, log_event)
from app.schemas.transaction import InvestigationResponse, TriageResult


def _ids(ts: datetime) -> tuple[str, str]:
    y = ts.year if isinstance(ts, datetime) else datetime.now().year
    return f"TXN_{y}_{uuid.uuid4().hex[:8].upper()}", f"INV_{y}_{uuid.uuid4().hex[:8].upper()}"


def _velocity(canonical: dict) -> dict:
    """Count prior-24h txns for account + new-beneficiary check from labeled_transactions.csv."""
    acct = str(canonical.get("source_account", ""))
    dest = str(canonical.get("destination_account", ""))
    ts = canonical.get("timestamp")
    ts_dt = ts if isinstance(ts, datetime) else datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    if not LABELED_CSV.exists():
        return {"day_count": 0, "is_new_beneficiary": bool(canonical.get("is_new_beneficiary", False))}
    try:
        import pandas as pd
        df = pd.read_csv(LABELED_CSV, usecols=["account_id", "counterparty_name", "date"], low_memory=True)
        df = df[df["account_id"] == acct].copy()
        if df.empty:
            return {"day_count": 0, "is_new_beneficiary": True}
        df["_d"] = pd.to_datetime(df["date"], errors="coerce", utc=False)
        ts_cmp = pd.Timestamp(ts_dt)
        if ts_cmp.tzinfo is not None:
            ts_cmp = ts_cmp.tz_convert(None)
        prior = df[df["_d"] < ts_cmp]
        day_ago = ts_cmp - pd.Timedelta(days=1)
        day_count = int(((prior["_d"] >= day_ago)).sum())
        seen = set(prior["counterparty_name"].astype(str).str.strip())
        return {"day_count": day_count, "is_new_beneficiary": dest.strip() not in seen}
    except Exception:
        log.exception("velocity lookup failed")
        return {"day_count": 0, "is_new_beneficiary": bool(canonical.get("is_new_beneficiary", False))}


class A1Agent:
    def __init__(self) -> None:
        init_db()

    def ingest(self, raw: dict, source_system: str = "UNKNOWN") -> InvestigationResponse:
        ok, errors = validate_raw(raw)
        if not ok:
            raise ValueError("validation failed: " + "; ".join(errors))
        can = normalize(raw, source_system or "UNKNOWN")
        ts_dt = can["timestamp"]
        ts_iso = ts_dt.isoformat() if isinstance(ts_dt, datetime) else str(ts_dt)
        fp = fingerprint(can["source_account"], can["destination_account"],
                         can["amount"], ts_iso, can["transaction_type"])

        dup = get_by_fingerprint(fp)
        if dup:
            log_event(dup["inv_id"], "A1", "DUPLICATE_HIT")
            payload = dup.get("payload") or {}
            tri = payload.get("triage", {}) if isinstance(payload, dict) else {}
            inv = get_investigation(dup["inv_id"]) or {}
            return InvestigationResponse(
                transaction_id=dup["txn_id"], investigation_id=dup["inv_id"],
                triage=TriageResult(transaction_id=dup["txn_id"],
                                    triage_score=float(tri.get("score", 0.0)),
                                    decision=dup.get("triage", "LOG_ONLY"),
                                    reasons=list(tri.get("reasons", ["duplicate hit"]))),
                duplicate=True, detection=(inv.get("result") or None) or None)

        txn_id, inv_id = _ids(ts_dt if isinstance(ts_dt, datetime) else datetime.now())
        can.update({"transaction_id": txn_id, "investigation_id": inv_id,
                    "fingerprint": fp, "timestamp": ts_iso})
        vel = _velocity({**can, "timestamp": ts_dt})
        tri_score, reasons = score({**can, "timestamp": ts_dt}, vel)
        dec = decision(tri_score)
        payload = {"canonical": can, "velocity": vel,
                   "triage": {"score": tri_score, "decision": dec, "reasons": reasons}}
        save_transaction(fp, txn_id, inv_id, payload, dec)
        log_event(inv_id, "A1", "INGESTED")
        log_event(inv_id, "A1", f"TRIAGED:{dec}:{tri_score}")

        detection = None
        if dec == "FULL_INVESTIGATION":
            from app.agents import a2_detection
            detection = a2_detection.run({**can, "timestamp": ts_dt})
            risk = float(detection.get("risk_score", 0) or 0)
            save_investigation(inv_id, txn_id, "OPEN" if risk >= 60 else "AUTO_CLOSED", detection)
            log_event(inv_id, "A2", "A2_COMPLETED")
        else:
            save_investigation(inv_id, txn_id, "CLOSED", {"triage": payload["triage"]})
        log.info("ingest %s -> %s (%.3f) dup=False", txn_id, dec, tri_score)
        return InvestigationResponse(
            transaction_id=txn_id, investigation_id=inv_id,
            triage=TriageResult(transaction_id=txn_id, triage_score=tri_score,
                                decision=dec, reasons=reasons),
            duplicate=False, detection=detection)
