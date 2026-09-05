"""Smoke test the new Phase 16 endpoints: /system/full-health + /demo/*."""
from __future__ import annotations
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request


def http(method, path, payload=None, timeout=15):
    req = urllib.request.Request(
        f"http://127.0.0.1:8000{path}",
        method=method,
        headers={"Content-Type": "application/json"},
    )
    if payload is not None:
        req.data = json.dumps(payload).encode()
    try:
        r = urllib.request.urlopen(req, timeout=timeout)
        return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


def main() -> int:
    backend = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(40):
            try:
                urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=1)
                break
            except Exception:
                time.sleep(0.5)

        print("--- /system/full-health ---")
        code, h = http("GET", "/system/full-health")
        print("status=", code, " overall=", h.get("overall_status"))
        for k, v in (h.get("components") or {}).items():
            print(f"  {k:<28} {v.get('status')}  - {v.get('detail') or v.get('error') or ''}")

        print("\n--- /demo/scenarios ---")
        code, s = http("GET", "/demo/scenarios")
        scenarios = s.get("scenarios") or []
        print(f"{len(scenarios)} scenarios | jurisdiction={s.get('jurisdiction')}")
        for sc in scenarios:
            print(f"  - {sc['scenario_id']:<24}  {sc['title']}")

        print("\n--- POST /demo/run (normal_transaction, sync) ---")
        code, r = http("POST", "/demo/run", {"scenario_id": "normal_transaction", "sync": True}, timeout=90)
        print("status=", code)
        for inv in (r.get("investigations") or []):
            print(f"  inv={inv.get('investigation_id')}  risk={inv.get('risk_score')}  level={inv.get('risk_level')}  status={inv.get('status')}")
        return 0
    finally:
        backend.terminate()
        try:
            backend.wait(timeout=5)
        except Exception:
            backend.kill()


if __name__ == "__main__":
    sys.exit(main())