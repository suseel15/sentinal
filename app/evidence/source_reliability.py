"""Source reliability registry.

Used by the corroboration engine and by evidence scoring to derive an
authoritative base confidence. Sources with higher tier get more weight
than unverified ones. An unverified source alone never justifies escalation.
"""
from __future__ import annotations

SOURCE_RELIABILITY: dict[str, float] = {
    "INTERNAL_BANK_DATA": 1.00,
    "INTERNAL_KYC": 0.95,
    "VERIFIED_HISTORICAL_CASE": 0.95,
    "INVESTIGATOR_DECISION": 0.90,
    "INTERNAL_TRANSACTION_HISTORY": 0.90,
    "INTERNAL_ALERT_HISTORY": 0.88,
    "EXTERNAL_VERIFIED_SOURCE": 0.85,
    "INTERNAL_GRAPH": 0.80,
    "SIMILARITY_SEARCH": 0.70,
    "UNVERIFIED_SOURCE": 0.40,
}


def reliability(source_type: str) -> float:
    """Return 0..1 reliability for the given source type."""
    if not source_type:
        return SOURCE_RELIABILITY["UNVERIFIED_SOURCE"]
    return SOURCE_RELIABILITY.get(source_type.upper(), SOURCE_RELIABILITY["UNVERIFIED_SOURCE"])