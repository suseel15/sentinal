"""Demo Mode — predefined realistic transaction scenarios.

Eight scenarios exercise the pipeline end-to-end:
  - normal_transaction
  - suspicious_structuring
  - known_fraud
  - novel_anomaly
  - mule_chain
  - shared_identity
  - super_node
  - size_fallback

Each scenario returns a list of canonical transactions that can be fed
through the standard orchestrator. No model output is fabricated — the
real Rules / XGBoost / Isolation Forest / Fusion / Graph / Evidence /
Regulatory / LLM agents all run.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

_JURISDICTION_LABELS = {
    "IN": ("RBI / PMLA / FIU-IND", "INR"),
    "US": ("FinCEN / BSA", "USD"),
    "EU": ("EBA AMLD", "EUR"),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ts(offset_minutes: int = 0) -> str:
    return datetime.now(timezone.utc).timestamp() + offset_minutes * 60


def _canonical(amount, source, destination, ttype="DEBIT", category="TRANSFER",
              channel="NEFT", timestamp=None, currency="INR", **extra) -> dict:
    return {
        "transaction_id": f"TXN-DEMO-{int(_ts() * 1000) % 10**10}-{source[-4:]}",
        "source_account": source,
        "destination_account": destination,
        "amount": abs(float(amount)),
        "transaction_type": ttype,
        "category": category,
        "channel": channel,
        "currency": currency,
        "timestamp": timestamp or _now(),
        **extra,
    }


# ---------------------------------------------------------------------------
# Scenario 1 — Normal Transaction
# ---------------------------------------------------------------------------
def scenario_normal_transaction() -> dict[str, Any]:
    """Expected: LOW risk, AUTO_CLOSED, only normal signals."""
    return {
        "scenario_id": "normal_transaction",
        "title": "Normal Transaction",
        "description": "Routine small UPI payment to a known merchant. Customer history is stable.",
        "expected_outcome": {
            "risk_level": "LOW",
            "status": "AUTO_CLOSED",
            "primary_signals": ["rules:none", "xgboost:low", "isolation_forest:low"],
        },
        "transactions": [
            _canonical(
                amount=1850.0,
                source="ACC-NORM-A",
                destination="D-MART-RETAIL",
                category="UPI",
                channel="UPI",
                timestamp="2025-11-21T09:32:00",
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Scenario 2 — Suspicious Structuring
# ---------------------------------------------------------------------------
def scenario_structuring() -> dict[str, Any]:
    """Four transfers just under the reporting threshold within 30 minutes.

    Expected: STRUCTURING rule triggers, velocity high, fusion score climbs
    into HIGH band as more transactions are processed.
    """
    base_ts = "2025-11-21T03:15:00"
    transactions = [
        _canonical(amount=485_000, source="ACC-SUS-1", destination="B-SHELLS-1",
                  category="NEFT", channel="NEFT", timestamp=f"{base_ts}"),
        _canonical(amount=490_000, source="ACC-SUS-1", destination="B-SHELLS-2",
                  category="NEFT", channel="NEFT", timestamp=f"{base_ts}"),
        _canonical(amount=475_000, source="ACC-SUS-1", destination="B-SHELLS-3",
                  category="NEFT", channel="NEFT", timestamp=f"{base_ts}"),
        _canonical(amount=495_000, source="ACC-SUS-1", destination="B-SHELLS-4",
                  category="NEFT", channel="NEFT", timestamp=f"{base_ts}"),
    ]
    return {
        "scenario_id": "suspicious_structuring",
        "title": "Structuring / AML Pattern",
        "description": "Four sub-threshold transfers in <30 minutes — classic structuring signature.",
        "expected_outcome": {
            "risk_level": "HIGH",
            "status": "WAITING_FOR_HUMAN",
            "primary_signals": ["rules:AML_STRUCTURING_001", "rules:AML_HIGH_VELOCITY",
                                "xgboost:high", "behavioral:high"],
            "report_language": "Potential structuring indicators detected. Human compliance review recommended.",
        },
        "transactions": transactions,
    }


# ---------------------------------------------------------------------------
# Scenario 3 — Known Fraud
# ---------------------------------------------------------------------------
def scenario_known_fraud() -> dict[str, Any]:
    """Large RTGS that matches historical confirmed-fraud signatures."""
    return {
        "scenario_id": "known_fraud",
        "title": "Known Fraud Pattern",
        "description": "₹45 Lakh RTGS with new beneficiary and unusual time — strongly resembles historical fraud.",
        "expected_outcome": {
            "risk_level": "HIGH",
            "status": "WAITING_FOR_HUMAN",
            "primary_signals": ["rules:AML_HIGH_VALUE", "rules:AML_NEW_BENEFICIARY",
                                "xgboost:high", "isolation_forest:medium", "shap:available"],
        },
        "transactions": [
            _canonical(
                amount=4_500_000.0,
                source="ACC-KF-001",
                destination="B-MULE-77",
                category="RTGS",
                channel="RTGS",
                timestamp="2025-11-21T02:10:00",
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Scenario 4 — Novel Anomaly
# ---------------------------------------------------------------------------
def scenario_novel_anomaly() -> dict[str, Any]:
    """An oddly timed round-amount transfer that doesn't match any rule."""
    return {
        "scenario_id": "novel_anomaly",
        "title": "Novel Anomaly",
        "description": "Round-amount transfer at 02:47 — no rule explicitly fires but anomaly detectors flag it.",
        "expected_outcome": {
            "risk_level": "MEDIUM",
            "status": "FULL_INVESTIGATION",
            "primary_signals": ["rules:none", "xgboost:low", "isolation_forest:high",
                                "autoencoder:high", "behavioral:medium"],
            "report_language": (
                "Although the transaction did not strongly match previously known fraud patterns, "
                "the anomaly detection models identified behavior significantly different from normal "
                "transaction patterns."
            ),
        },
        "transactions": [
            _canonical(
                amount=750_000.0,
                source="ACC-NOV-01",
                destination="B-UNKNOWN-12",
                category="IMPS",
                channel="IMPS",
                timestamp="2025-11-21T02:47:00",
            ),
        ],
    }


# ---------------------------------------------------------------------------
# Scenario 5 — Mule Chain
# ---------------------------------------------------------------------------
def scenario_mule_chain() -> dict[str, Any]:
    """Rapid 3-hop transfer chain, classic pass-through pattern."""
    t0 = "2025-11-21T10:00:00"
    t1 = "2025-11-21T10:04:00"
    t2 = "2025-11-21T10:08:00"
    return {
        "scenario_id": "mule_chain",
        "title": "Mule Account Chain",
        "description": "Three hops in 8 minutes; funds distributed to multiple accounts.",
        "expected_outcome": {
            "risk_level": "HIGH",
            "status": "WAITING_FOR_HUMAN",
            "primary_signals": ["graph:mule_passthrough", "rules:FRAUD_RAPID_MOVEMENT",
                                "xgboost:high", "isolation_forest:high"],
            "graph_findings": ["hop_count:3", "pass_through_ratio:>0.8", "rapid_movement:true"],
        },
        "transactions": [
            _canonical(amount=9_500_000, source="MULE-A", destination="MULE-B",
                      category="RTGS", channel="RTGS", timestamp=t0),
            _canonical(amount=9_300_000, source="MULE-B", destination="MULE-C",
                      category="RTGS", channel="RTGS", timestamp=t1),
            _canonical(amount=9_200_000, source="MULE-C", destination="MULE-D",
                      category="RTGS", channel="RTGS", timestamp=t2),
        ],
    }


# ---------------------------------------------------------------------------
# Scenario 6 — Shared Identity (same device, same IP)
# ---------------------------------------------------------------------------
def scenario_shared_identity() -> dict[str, Any]:
    """Three different accounts receiving transfers that share the same device."""
    return {
        "scenario_id": "shared_identity",
        "title": "Shared Identity Infrastructure",
        "description": "Three accounts connected through the same device identifier.",
        "expected_outcome": {
            "risk_level": "MEDIUM",
            "status": "FULL_INVESTIGATION",
            "primary_signals": ["graph:shared_device", "graph:shared_identity"],
            "report_language": (
                "Shared identity infrastructure detected. This is treated as an investigation "
                "signal — not an automated fraud finding."
            ),
        },
        "transactions": [
            _canonical(amount=120_000, source="ACC-SI-1", destination="B-SHARED-X",
                      category="NEFT", channel="NEFT", timestamp="2025-11-21T11:00:00"),
            _canonical(amount=130_000, source="ACC-SI-2", destination="B-SHARED-X",
                      category="NEFT", channel="NEFT", timestamp="2025-11-21T11:05:00"),
            _canonical(amount=145_000, source="ACC-SI-3", destination="B-SHARED-X",
                      category="NEFT", channel="NEFT", timestamp="2025-11-21T11:10:00"),
        ],
    }


# ---------------------------------------------------------------------------
# Scenario 7 — Super Node (legitimate hub)
# ---------------------------------------------------------------------------
def scenario_super_node() -> dict[str, Any]:
    """Transfer through a known high-degree entity (payment gateway)."""
    return {
        "scenario_id": "super_node",
        "title": "Legitimate Super-Node Transaction",
        "description": "Payment routed through a known high-degree gateway (e.g. a payment processor).",
        "expected_outcome": {
            "risk_level": "LOW",
            "status": "AUTO_CLOSED",
            "graph_analysis_mode": "HUB_AWARE",
            "primary_signals": ["graph:hub_aware", "rules:none"],
            "report_language": (
                "The high-degree entity was identified as a legitimate transaction hub and was "
                "excluded from generic mule-chain scoring."
            ),
        },
        "transactions": [
            _canonical(amount=85_000, source="ACC-HUB-1", destination="PAYMENT-GATEWAY-X",
                      category="UPI", channel="UPI", timestamp="2025-11-21T12:30:00"),
        ],
    }


# ---------------------------------------------------------------------------
# Scenario 8 — Huge Graph (forces SIZE_FALLBACK)
# ---------------------------------------------------------------------------
def scenario_size_fallback() -> dict[str, Any]:
    """Single transaction used to force the graph agent's bounds.

    The A4 graph agent is invoked with config_overrides={MAX_NODES: 5, MAX_HOPS: 1}
    by the demo runner so the analysis mode becomes SIZE_FALLBACK.
    """
    return {
        "scenario_id": "size_fallback",
        "title": "Huge Graph — Size Fallback",
        "description": "Investigation graph exceeds safe traversal limits.",
        "expected_outcome": {
            "risk_level": "MEDIUM",
            "status": "FULL_INVESTIGATION",
            "graph_analysis_mode": "SIZE_FALLBACK",
            "primary_signals": ["graph:size_fallback", "manual_review_required:true"],
            "report_language": (
                "Automated graph analysis was limited because the connected network exceeded "
                "the safe analysis threshold. Aggregate network statistics are shown. "
                "Manual graph investigation is recommended."
            ),
        },
        "transactions": [
            _canonical(amount=2_500_000, source="ACC-BIG-1", destination="B-MEGA-HUB",
                      category="RTGS", channel="RTGS", timestamp="2025-11-21T13:00:00"),
        ],
        "config_overrides": {"MAX_NODES": 5, "MAX_HOPS": 1},
    }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
SCENARIOS = {
    "normal_transaction": scenario_normal_transaction,
    "suspicious_structuring": scenario_structuring,
    "known_fraud": scenario_known_fraud,
    "novel_anomaly": scenario_novel_anomaly,
    "mule_chain": scenario_mule_chain,
    "shared_identity": scenario_shared_identity,
    "super_node": scenario_super_node,
    "size_fallback": scenario_size_fallback,
}


def list_scenarios() -> list[dict[str, Any]]:
    """Return a list of all available demo scenarios (metadata only)."""
    out: list[dict[str, Any]] = []
    for sid, fn in SCENARIOS.items():
        try:
            pack = fn()
            out.append({
                "scenario_id": sid,
                "title": pack.get("title"),
                "description": pack.get("description"),
                "expected_outcome": pack.get("expected_outcome"),
            })
        except Exception:
            log.exception("scenario %s failed to load", sid)
    return out


def run_scenario(scenario_id: str, sync: bool = True) -> dict[str, Any]:
    """Run a demo scenario through the orchestrator. Returns one investigation_id per transaction."""
    from app.agents import orchestrator

    fn = SCENARIOS.get(scenario_id)
    if not fn:
        return {"error": "scenario_not_found", "scenario_id": scenario_id,
                "available": list(SCENARIOS.keys())}
    pack = fn()
    out = {"scenario": pack, "investigations": [], "transaction_ids": []}
    for txn in pack["transactions"]:
        try:
            res = orchestrator.start_from_payload(txn, run_async=not sync)
        except Exception as e:
            log.exception("demo scenario %s failed on %s", scenario_id, txn.get("transaction_id"))
            res = {"error": str(e), "transaction_id": txn.get("transaction_id")}
        out["investigations"].append(res)
        out["transaction_ids"].append(txn.get("transaction_id"))
    return out


def jurisdiction() -> tuple[str, str]:
    import os
    code = (os.environ.get("SENTINEL_JURISDICTION") or "IN").upper()
    return _JURISDICTION_LABELS.get(code, _JURISDICTION_LABELS["IN"])