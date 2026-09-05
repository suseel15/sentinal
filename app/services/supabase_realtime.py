"""Supabase realtime bridge for Phase 7 investigation status updates.

When SUPABASE_URL and SUPABASE_KEY are set, status updates are published
to a `investigation_events` channel so a frontend can subscribe via Supabase
Realtime. Without credentials this module is a no-op; the local SQLite
store remains the source of truth and the frontend can poll
GET /investigations/{id}/state.
"""
import json
import logging
import os
import threading
from datetime import datetime, timezone

log = logging.getLogger(__name__)


def configured() -> bool:
    return bool(os.getenv("SUPABASE_URL")) and bool(os.getenv("SUPABASE_KEY"))


def _publish(channel: str, event: str, payload: dict) -> None:
    """Best-effort realtime publish. Failures are logged, never raised."""
    if not configured():
        return
    try:
        from supabase import create_client
        client = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
        # 1) insert into a log table (durable record)
        try:
            client.table("investigation_events").insert({
                "channel": channel,
                "event": event,
                "payload": payload,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.debug("event insert failed (table may not exist): %s", e)
        # 2) broadcast via realtime channel
        try:
            client.channel(channel).send({
                "type": "broadcast",
                "event": event,
                "payload": payload,
            })
        except Exception:
            log.debug("realtime broadcast failed (channel not subscribed)")
    except Exception as e:
        log.warning("supabase publish failed: %s", e)


def publish_status(investigation_id: str, status: str,
                   risk_score: float | None = None,
                   risk_level: str | None = None,
                   extra: dict | None = None) -> None:
    payload = {
        "investigation_id": investigation_id,
        "status": status,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "extra": extra or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    # Fire-and-forget so it never blocks the orchestrator.
    threading.Thread(target = _publish,
                    args = ("investigations", "status_change", payload),
                    daemon = True).start()