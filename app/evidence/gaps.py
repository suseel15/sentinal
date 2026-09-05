"""Evidence gaps engine.

A3 must explicitly report missing evidence. Each gap is a small structured
record so that downstream agents (A5/A7) and the dashboard can surface
them to the investigator.
"""
from __future__ import annotations

from typing import Any

GAPS = {
    "DEVICE_HISTORY_NOT_AVAILABLE": "Unable to validate account-takeover indicators.",
    "EXTERNAL_SANCTIONS_UNAVAILABLE": "Sanctions intelligence not configured in this environment.",
    "IP_GEOLOCATION_UNAVAILABLE": "IP / geolocation intelligence not configured in this environment.",
    "SIMILAR_CASE_SEARCH_PARTIAL": "Similar case search returned fewer than 3 historical cases.",
    "NO_PRIOR_INVESTIGATIONS": "Customer has no prior investigations on file.",
    "KYC_FIELDS_INCOMPLETE": "KYC profile missing risk-relevant fields.",
    "BENEFICIARY_HISTORY_SHALLOW": "Receiving account has fewer than 5 prior transactions.",
}


def gaps_for(items: list[dict[str, Any]], similar_cases: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    src_types = {str(it.get("source_type") or "") for it in items or []}
    if "DEVICE" not in src_types and "DEVICE_HISTORY" not in src_types and "INTERNAL_DEVICE" not in src_types:
        out.append({"gap": "DEVICE_HISTORY_NOT_AVAILABLE", "impact": GAPS["DEVICE_HISTORY_NOT_AVAILABLE"]})
    if "EXTERNAL_SANCTIONS" not in src_types:
        out.append({"gap": "EXTERNAL_SANCTIONS_UNAVAILABLE", "impact": GAPS["EXTERNAL_SANCTIONS_UNAVAILABLE"]})
    if "IP_GEOLOCATION" not in src_types:
        out.append({"gap": "IP_GEOLOCATION_UNAVAILABLE", "impact": GAPS["IP_GEOLOCATION_UNAVAILABLE"]})
    if len(similar_cases or []) < 3:
        out.append({"gap": "SIMILAR_CASE_SEARCH_PARTIAL", "impact": GAPS["SIMILAR_CASE_SEARCH_PARTIAL"]})
    if not items:
        out.append({"gap": "NO_PRIOR_INVESTIGATIONS", "impact": GAPS["NO_PRIOR_INVESTIGATIONS"]})
    return out