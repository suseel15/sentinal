"""Live transaction streamer.

Reads transactions from labeled_transactions.csv (or any source CSV with the
required columns) and pushes them into the orchestrator one at a time. Used
for end-to-end demos. The frontend dashboard polls /stream/status to display
progress; each pushed transaction is also exposed via /stream/recent.

Usage:
    python -m app.streamer --rps 0.5 --limit 20
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
os.chdir(REPO_ROOT)
sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("streamer")


class StreamState:
    def __init__(self):
        self._lock = threading.Lock()
        self.running = False
        self.processed = 0
        self.last_inv_id: str | None = None
        self.last_status: str | None = None
        self.last_risk_score: float | None = None
        self.recent: list[dict] = []
        self.started_at: str | None = None
        self.stop_requested = False

    def push(self, event: dict, update: bool = False) -> None:
        with self._lock:
            self.last_inv_id = event.get("investigation_id", self.last_inv_id)
            self.last_status = event.get("status")
            self.last_risk_score = event.get("risk_score")
            if update:
                for i, ev in enumerate(self.recent):
                    if ev.get("transaction_id") == event.get("transaction_id"):
                        self.recent[i] = event
                        return
            self.processed += 1
            self.recent.insert(0, event)
            del self.recent[50:]


def request_stop() -> dict:
    STATE.stop_requested = True
    STATE.running = False
    return {"stopped": True}


STATE = StreamState()


def _row_to_payload(row: dict) -> dict:
    amt = float(row.get("amount") or 0)
    return {
        "transaction_id": str(row.get("transaction_id", "")),
        "account_id": str(row.get("account_id") or row.get("sender_account_id", "UNK")),
        "counterparty_name": str(row.get("counterparty_name") or row.get("receiver_account_id", "UNK")),
        "amount": abs(amt),
        "date": str(row.get("date") or row.get("timestamp", datetime.now(timezone.utc).isoformat())),
        "type": str(row.get("type") or row.get("transaction_type", "DEBIT")),
        "category": str(row.get("category") or row.get("merchant_category") or "TRANSFER"),
        "channel": str(row.get("channel", "ONLINE")),
        "device_id": row.get("device_id"),
        "ip_address": row.get("ip_address"),
    }


def _source_csv(csv_path: str | None = None):
    if csv_path:
        return Path(csv_path)
    try:
        from app.services import datasets as _ds
        return _ds.preferred_txn_csv()
    except Exception:
        return REPO_ROOT / "labeled_transactions.csv"


def stream(csv_path: str | None = None, rps: float = 0.5, limit: int | None = None,
           start_index: int = 0, resume: bool = True, key: str = "default") -> dict:
    """Synchronous streaming loop. Resumes from saved offset unless start_index given."""
    import pandas as pd
    from app.agents import orchestrator
    from app.services import store as _st
    p = _source_csv(csv_path)
    if not p.exists():
        return {"error": f"csv not found: {p}"}
    base = 0
    if resume and not start_index and not csv_path:
        try:
            base = _st.get_stream_offset(key)
        except Exception:
            base = 0
    start_index = start_index or base
    STATE.running = True
    STATE.started_at = datetime.now(timezone.utc).isoformat()
    STATE.processed = 0
    STATE.recent.clear()
    STATE.stop_requested = False
    try:
        df = pd.read_csv(p, low_memory=True)
        if start_index:
            df = df.iloc[start_index:]
        if limit:
            df = df.head(limit)
        delay = max(0.0, 1.0 / max(rps, 0.01))
        log.info("streaming %d txns at rps=%.2f delay=%.2fs", len(df), rps, delay)
        for i, row in df.iterrows():
            if STATE.stop_requested:
                log.info("stream stop requested at %d", STATE.processed)
                break
            payload = _row_to_payload(row.to_dict())
            payload["date"] = (
                datetime.now(timezone.utc) + timedelta_safe(int(time.time()*1000) % 1_000_000)
            ).replace(tzinfo=None).isoformat()
            payload["transaction_id"] = f"TXN-STREAM-{int(time.time()*1000)}-{STATE.processed}"
            STATE.push({"transaction_id": payload["transaction_id"], "status": "PROCESSING"})
            try:
                out = orchestrator.start_from_payload(payload, run_async=False)
                event = {
                    "investigation_id": out.get("investigation_id", ""),
                    "transaction_id": payload["transaction_id"],
                    "status": out.get("status"),
                    "risk_score": out.get("risk_score"),
                    "risk_level": out.get("risk_level"),
                    "recommendation": out.get("recommendation"),
                    # Real txn facts so list/detail pages never fall back to demo data.
                    "amount": payload.get("amount"),
                    "sender": payload.get("account_id"),
                    "receiver": payload.get("counterparty_name"),
                    "channel": payload.get("channel"),
                    "created_at": payload.get("date"),
                    "ts": datetime.now(timezone.utc).isoformat(),
                }
                STATE.push(event, update=True)
                log.info("[%d] inv=%s status=%s risk=%s",
                         STATE.processed, event["investigation_id"], event["status"], event["risk_score"])
            except Exception as e:
                log.exception("push failed")
                STATE.push({"transaction_id": payload["transaction_id"], "status": "FAILED", "error": str(e)}, update=True)
            time.sleep(delay)
            try:
                _st.set_stream_offset(start_index + STATE.processed, key)
            except Exception:
                pass
    except Exception as e:
        log.exception("stream aborted")
        STATE.push({"transaction_id": "-", "status": "FAILED", "error": str(e)})
    finally:
        STATE.running = False
    return {"processed": STATE.processed}


def timedelta_safe(us: int):
    from datetime import timedelta
    return timedelta(microseconds=us)


def get_status() -> dict:
    return {
        "running": STATE.running,
        "processed": STATE.processed,
        "last_investigation_id": STATE.last_inv_id,
        "last_status": STATE.last_status,
        "last_risk_score": STATE.last_risk_score,
        "started_at": STATE.started_at,
        "recent": list(STATE.recent),
    }


def start_async(csv_path: str | None, rps: float, limit: int | None, start_index: int,
                resume: bool = True) -> dict:
    if STATE.running:
        return {"error": "already running"}
    t = threading.Thread(target=stream, args=(csv_path, rps, limit, start_index, resume),
                         daemon=True)
    t.start()
    return {"started": True, "thread": t.name}


def reset_offset(key: str = "default") -> dict:
    try:
        from app.services import store as _st
        _st.set_stream_offset(0, key)
    except Exception as e:
        return {"reset": False, "error": str(e)}
    return {"reset": True}


def main():
    ap = argparse.ArgumentParser(description="SENTINEL live transaction streamer")
    ap.add_argument("--csv", default=None, help="Path to source CSV (default: labeled_transactions.csv)")
    ap.add_argument("--rps", type=float, default=0.5, help="Transactions per second")
    ap.add_argument("--limit", type=int, default=10, help="Max transactions to stream")
    ap.add_argument("--start-index", type=int, default=0, help="Skip first N rows")
    args = ap.parse_args()
    out = stream(args.csv, args.rps, args.limit, args.start_index)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()