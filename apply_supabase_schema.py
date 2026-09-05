"""Apply supabase_schema.sql to the live Supabase project.

The Supabase REST API does not support DDL directly. To apply the
schema we offer three strategies:

  1. Try the `exec_sql(text)` RPC if the user has created it.
  2. Try issuing CREATE TABLE via PostgREST's introspection.
  3. Print the exact SQL the user should paste into the Supabase SQL
     editor (Dashboard → SQL → New query → Run).

The script also auto-creates a helper `exec_sql(text)` RPC if the
service-role key has the `postgres` extension permissions, then falls
back to printing the SQL on failure.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.services import supabase_client

log = logging.getLogger(__name__)
REPO = Path(__file__).resolve().parent


def main() -> int:
    schema_path = REPO / "supabase_schema.sql"
    sql = schema_path.read_text(encoding="utf-8")

    if not supabase_client.configured():
        print("Supabase not configured. Set SUPABASE_URL + SUPABASE_KEY in .env")
        return 2

    client = supabase_client.get_client()
    print(f"Connected to: {supabase_client.os.environ['SUPABASE_URL']}")

    # Strategy 1 — try exec_sql RPC
    try:
        client.rpc("exec_sql", {"sql": sql}).execute()
        print("[OK] schema applied via exec_sql RPC")
        return 0
    except Exception as e:
        print(f"[INFO] exec_sql RPC unavailable: {str(e)[:120]}")

    # Strategy 2 — try to create the exec_sql function via RPC first
    helper_sql = """
    CREATE OR REPLACE FUNCTION public.exec_sql(sql text) RETURNS void
    LANGUAGE plpgsql SECURITY DEFINER AS $$
    BEGIN
      EXECUTE sql;
    END;
    $$;
    """
    try:
        client.rpc("exec_sql", {"sql": helper_sql}).execute()
        client.rpc("exec_sql", {"sql": sql}).execute()
        print("[OK] created exec_sql RPC and applied schema")
        return 0
    except Exception as e:
        print(f"[INFO] could not bootstrap exec_sql: {str(e)[:120]}")

    # Strategy 3 — probe which tables already exist and print guidance
    print("\nProbing existing tables...")
    target_tables = [
        "investigations", "agent_sections", "evidence_items",
        "graph_results", "regulatory_findings", "investigation_reports",
        "action_recommendations", "human_decisions", "feedback_dataset",
        "audit_events", "live_transactions", "model_versions",
    ]
    missing = []
    for t in target_tables:
        try:
            client.table(t).select("*", count="exact").limit(1).execute()
            print(f"  [OK]  {t}")
        except Exception:
            print(f"  [..]  {t} (missing)")
            missing.append(t)

    if not missing:
        print("\nAll SENTINEL tables already exist in Supabase.")
        return 0

    print(f"\nMissing tables: {missing}")
    print("\nApply the schema with one of these two methods:")
    print("  1) Open supabase_schema.sql and paste it into the Supabase SQL editor (Dashboard -> SQL -> New query -> Run).")
    print("  2) Use the psql CLI: psql '<DATABASE_URL>' -f supabase_schema.sql")
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())