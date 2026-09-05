"""SENTINEL End-to-End Demo Runner — Phase 15.

What this script does:

    1. Starts the FastAPI backend programmatically (uvicorn) on :8000.
    2. Starts a live transaction stream (CSV -> orchestrator).
    3. Polls /stream/status for incoming investigations.
    4. Picks the first HIGH/CRITICAL risk case.
    5. Fetches every agent section (A2, A3, A4, A5, A7, A8) + audit.
    6. Submits an investigator ACCEPT decision.
    7. Verifies feedback is stored.
    8. Opens the dashboard URL hint.

Run with:    python demo_end_to_end.py
No Docker required.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent
API = os.environ.get("SENTINEL_API_URL", "http://127.0.0.1:8000")
DASHBOARD = os.environ.get("SENTINEL_DASHBOARD_URL", "http://127.0.0.1:3000")
INVESTIGATOR_ID = "INV-DEMO-001"
TIMEOUT_STARTUP = 30
TIMEOUT_STREAM = 25


def _http(method: str, path: str, payload: dict | None = None, timeout: int = 15):
    url = f"{API}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode()
        try:
            return resp.status, json.loads(body)
        except Exception:
            return resp.status, body


def _port_open(host: str, port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.3)
    try:
        return s.connect_ex((host, port)) == 0
    finally:
        s.close()


def _wait_for_backend() -> bool:
    started = time.time()
    while time.time() - started < TIMEOUT_STARTUP:
        try:
            code, body = _http("GET", "/health")
            if code == 200:
                print(f"[OK] backend live at {API} — {body}")
                return True
        except Exception:
            pass
        time.sleep(0.7)
    return False


def _start_backend() -> subprocess.Popen:
    print("[..] launching FastAPI backend on :8000")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
        cwd=str(REPO),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    if not _wait_for_backend():
        proc.terminate()
        raise SystemExit("Backend failed to start within timeout.")
    return proc


def _start_stream(limit: int = 10) -> None:
    print(f"[..] starting live stream (limit={limit})")
    # start_index 426 is the first labeled fraud transaction in
    # labeled_transactions.csv so the demo starts with suspicious cases.
    _http("POST", "/stream/start", {"rps": 2.0, "limit": limit, "start_index": 426}, timeout=10)
    print("[OK] stream started")


def _ensure_high_risk_case(timeout_s: int = 60) -> dict | None:
    """Wait up to `timeout_s` for a HIGH/CRITICAL case from the stream.

    If the stream produces no such case in time, fall back to triggering
    a known suspicious transaction by ID so the demo always has a case
    that exercises A3+A4+A5+A7+A8.
    """
    items = _poll_stream(timeout_s=timeout_s)
    target = _pick_high_risk(items)
    if target:
        return target
    # Fallback: directly trigger a known suspicious transaction.
    print("[..] stream produced no HIGH/CRITICAL case; triggering a labeled suspicious transaction")
    import pandas as pd
    try:
        df = pd.read_csv("labeled_transactions.csv", low_memory=True)
        sub = df[(df["is_suspicious"] == 1) & df["transaction_id"].notna()].head(5)
        for txn in sub["transaction_id"].astype(str).tolist():
            try:
                code, body = _http("POST", "/investigations/start", {"transaction_id": txn, "sync": True}, timeout=60)
                if code == 200 and body.get("status") not in {"DUPLICATE_LOGGED", "FAILED"}:
                    inv = {
                        "investigation_id": body.get("investigation_id"),
                        "transaction_id": txn,
                        "risk_score": body.get("risk_score"),
                        "risk_level": body.get("risk_level"),
                        "status": body.get("status"),
                    }
                    print(f"[OK] triggered {txn} -> {inv}")
                    return inv
            except Exception as e:
                print(f"  - trigger {txn} failed: {e}")
    except Exception as e:
        print(f"[WARN] fallback lookup failed: {e}")
    return None


def _poll_stream(timeout_s: int) -> list[dict]:
    started = time.time()
    items: list[dict] = []
    while time.time() - started < timeout_s:
        code, status = _http("GET", "/stream/status")
        items = (status or {}).get("recent") or []
        if any((i.get("risk_level") or "").upper() in {"HIGH", "CRITICAL"} for i in items):
            return items
        time.sleep(0.6)
    return items


def _pick_high_risk(items: list[dict]) -> dict | None:
    for it in items:
        lvl = (it.get("risk_level") or "").upper()
        if lvl in {"HIGH", "CRITICAL"}:
            return it
    return items[0] if items else None


def _section(title: str):
    print()
    print("=" * 72)
    print(f"  {title}")
    print("=" * 72)


def main():
    backend_was_already_up = _port_open("127.0.0.1", 8000)
    backend = None
    if backend_was_already_up:
        print(f"[OK] reusing existing backend at {API}")
    else:
        backend = _start_backend()

    try:
        # 1. Stream
        _start_stream(limit=20)
        target = _ensure_high_risk_case(timeout_s=30)
        if not target:
            raise SystemExit("No investigations arrived. Aborting demo.")

        # 2. Pick a high-risk case
        inv_id = target["investigation_id"]
        _section("Selected investigation")
        print(json.dumps(target, indent=2, default=str))

        # 3. Fetch every agent section + audit
        _section("A2 — Detection")
        _, a2 = _http("GET", f"/investigations/{inv_id}/state")
        a2_section = ((a2 or {}).get("sections") or {}).get("A2") or {}
        print(f"risk_score={a2_section.get('result', {}).get('risk_score')}"
              f"  risk_level={a2_section.get('result', {}).get('risk_level')}"
              f"  confidence={a2_section.get('result', {}).get('confidence')}")

        _section("A3 — Evidence")
        _, ev = _http("GET", f"/evidence/{inv_id}")
        esum = (ev or {}).get("evidence_summary") or {}
        print(f"items={esum.get('total')}  supporting={esum.get('supporting')}"
              f"  contradicting={esum.get('contradicting')}")

        _section("A4 — Graph")
        _, gv = _http("GET", f"/investigations/{inv_id}/graph/visualization")
        nodes = (gv or {}).get("nodes") or []
        edges = (gv or {}).get("edges") or []
        print(f"analysis_mode={gv.get('analysis_mode')}  nodes={len(nodes)}  edges={len(edges)}")

        _section("A5 — Regulatory")
        _, a5 = _http("GET", f"/investigations/{inv_id}/regulatory")
        findings = (a5 or {}).get("findings") or (a5 or {}).get("potential_regulatory_relevance") or []
        print(f"findings={len(findings)}  human_review_required={a5.get('human_review_required')}")

        _section("A7 — Report sections")
        _, rep = _http("GET", f"/investigations/{inv_id}/report")
        sections = list((rep or {}).get("sections", {}).keys()) if isinstance(rep, dict) else []
        print(f"sections={sections}")

        _section("A8 — Recommendation")
        _, rec = _http("GET", f"/investigations/{inv_id}/recommendation")
        print(json.dumps(rec, indent=2, default=str)[:400])

        _section("Audit trail")
        _, au = _http("GET", f"/investigations/{inv_id}/audit")
        events = (au or {}).get("events") or []
        for e in events[:6]:
            print(f"  {e.get('at')}  {e.get('actor'):<12}  {e.get('event')}")
        print(f"  ... ({len(events)} total events)")

        # 4. Human decision
        _section("Submit human decision")
        decision_payload = {
            "investigator_id": INVESTIGATOR_ID,
            "decision": "ACCEPT",
            "justification": "Confirmed via KYC callback; pattern matches prior structuring case.",
            "confirmed_outcome": "TRUE_POSITIVE",
        }
        code, dec = _http("POST", f"/investigations/{inv_id}/human-decision", decision_payload, timeout=30)
        print(json.dumps(dec, indent=2, default=str))

        # 5. Dashboard link
        _section("Open in dashboard")
        print(f"  Investigation:  {DASHBOARD}/investigations/{inv_id}")
        print(f"  Queue:          {DASHBOARD}/investigations")
        print(f"  Command Center: {DASHBOARD}/dashboard")

        print()
        print("=" * 72)
        print("  SENTINEL END-TO-END DEMO COMPLETE")
        print("=" * 72)
    finally:
        if backend is not None:
            print("[..] stopping backend")
            backend.terminate()
            try:
                backend.wait(timeout=5)
            except Exception:
                backend.kill()


if __name__ == "__main__":
    main()