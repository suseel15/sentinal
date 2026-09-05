"""Evidence corroboration engine.

Multiple independent sources supporting the same finding -> higher confidence.
Duplicate data sources (same source_type + entity_id) are NOT counted as
independent corroboration.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

log = logging.getLogger(__name__)


def corroborate(evidence_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Group items by finding key and compute corroboration counts.

    Returns a mapping evidence_id -> {corroboration_count, unique_sources}.
    """
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for ev in evidence_items or []:
        key = str(ev.get("finding_key") or ev.get("type") or ev.get("title") or ev.get("evidence_id"))
        groups[key].append(ev)

    out: dict[str, dict[str, Any]] = {}
    for key, items in groups.items():
        unique_sources: set[str] = set()
        for it in items:
            src = str(it.get("source_type") or it.get("source") or "UNVERIFIED")
            entity = str(it.get("entity_id") or "")
            unique_sources.add(f"{src}::{entity}")
        count = len(unique_sources)
        for it in items:
            out[str(it.get("evidence_id") or id(it))] = {
                "corroboration_count": count,
                "unique_sources": sorted(unique_sources),
            }
    return out


def contradictory(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return evidence items whose direction is CONTRADICTS_RISK."""
    return [e for e in items or [] if str(e.get("direction", "")).upper() == "CONTRADICTS_RISK"]


def supporting(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in items or [] if str(e.get("direction", "SUPPORTS_RISK")).upper() == "SUPPORTS_RISK"]


def unavailable(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in items or [] if str(e.get("status", "")).upper() == "UNAVAILABLE"]