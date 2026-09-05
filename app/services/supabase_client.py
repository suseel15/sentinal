"""Supabase adapter (activates when SUPABASE_URL + SUPABASE_KEY are set).

Without credentials the platform runs on the local SQLite store
(app/services/store.py + evidence_store.py) with identical table shapes.
To enable: pip install supabase, set env vars, create tables per
spec (transactions, customers, accounts, investigations, audit_events,
evidence_items, evidence_sources, evidence_summary, dataset_registry),
then point repositories at get_client().
"""
import logging
import os

log = logging.getLogger(__name__)


def configured() -> bool:
    return bool(os.getenv("SUPABASE_URL") and os.getenv("SUPABASE_KEY"))


def get_client():
    if not configured():
        raise RuntimeError("SUPABASE_URL/SUPABASE_KEY not set; using SQLite store")
    try:
        from supabase import create_client
    except ImportError as e:
        raise RuntimeError("pip install supabase to enable") from e
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])
