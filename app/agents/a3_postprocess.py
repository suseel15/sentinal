"""A3 post-processing: similar cases, corroboration, contradictions, gaps.

Wraps the existing `a3_evidence.gather` result with:
  - similar_cases  (vector fingerprint search over prior investigations)
  - corroboration  (independent-source agreement)
  - contradictions  (subset of evidence pointing AGAINST risk)
  - gaps           (explicit missing-source list)
  - canonical schema (summary, supporting/contradicting counts, sources_checked)

This module does NOT mutate the underlying evidence items. It only
adds aggregate fields so downstream agents (A5/A7/A8) and the dashboard
have a consistent canonical A3 shape.
"""
from __future__ import annotations

import logging
from typing import Any

from app.evidence import gaps as gaps_mod
from app.evidence import similar_cases as similar
from app.evidence.corroboration import corroborate, supporting, contradictory, unavailable
from app.evidence.source_reliability import reliability

log = logging.getLogger(__name__)


def _items_as_dicts(pack: Any) -> list[dict[str, Any]]:
    out = []
    for it in getattr(pack, "evidence", []) or []:
        if hasattr(it, "model_dump"):
            out.append(it.model_dump())
        elif isinstance(it, dict):
            out.append(it)
        else:
            out.append(dict(it))
    return out


def _pack_id(pack: Any) -> str:
    return str(getattr(pack, "investigation_id", "") or "")


def _pack_canonical(pack: Any) -> dict[str, Any]:
    tx = getattr(pack, "transaction_id", None)
    return {"transaction_id": tx, "amount": 0}


def augment(pack: Any, canonical: dict | None = None, a2: dict | None = None) -> dict[str, Any]:
    """Return the canonical A3 dict, enriching the existing pack."""
    inv_id = _pack_id(pack)
    items = _items_as_dicts(pack)
    canon = canonical or _pack_canonical(pack)
    a2 = a2 or {}

    # ---- similar cases ----------------------------------------------
    try:
        similar_cases = similar.find_similar(canon, a2, top_k=5, exclude_self=inv_id)
    except Exception:
        log.exception("similar_cases failed")
        similar_cases = []

    # ---- corroboration ---------------------------------------------
    try:
        cor_map = corroborate(items)
    except Exception:
        log.exception("corroborate failed")
        cor_map = {}

    # attach corroboration_count to each item (read-only)
    for it in items:
        key = str(it.get("evidence_id") or id(it))
        ent = cor_map.get(key) or {}
        it["corroboration_count"] = int(ent.get("corroboration_count") or 1)
        it["unique_sources"] = list(ent.get("unique_sources") or [])

    # ---- contradictions / supporting / unavailable ------------------
    sup = supporting(items)
    con = contradictory(items)
    una = unavailable(items)
    sources_checked = sorted({str(it.get("source_type") or it.get("source") or "UNKNOWN") for it in items})
    unavailable_sources = sorted({str(it.get("source_type") or it.get("source") or "UNKNOWN") for it in una})

    # ---- evidence gaps ----------------------------------------------
    try:
        gaps = gaps_mod.gaps_for(items, similar_cases)
    except Exception:
        log.exception("gaps_for failed")
        gaps = []

    # ---- overall evidence confidence --------------------------------
    confidences = [float(it.get("confidence") or 0.0) for it in items if it.get("status") == "AVAILABLE"]
    if confidences:
        # weight by source reliability
        weighted = []
        for it, c in zip([i for i in items if i.get("status") == "AVAILABLE"], confidences):
            rel = reliability(str(it.get("source_type") or it.get("source") or "UNVERIFIED_SOURCE"))
            weighted.append(rel * c)
        overall = (sum(weighted) / len(weighted)) if weighted else 0.0
    else:
        overall = 0.0

    # ---- build canonical pack dict ----------------------------------
    summary = {
        "total_evidence": len(items),
        "supporting_evidence": len(sup),
        "contradictory_evidence": len(con),
        "unverified_evidence": len(una),
        "overall_evidence_confidence": round(overall, 3),
        "similar_cases_found": len(similar_cases),
    }

    return {
        "investigation_id": inv_id,
        "agent": "A3",
        "status": getattr(pack, "status", "COMPLETE"),
        "transaction_id": getattr(pack, "transaction_id", None),
        "evidence_summary": (
            getattr(pack, "evidence_summary").model_dump()
            if hasattr(getattr(pack, "evidence_summary", None), "model_dump")
            else getattr(pack, "evidence_summary", None) and dict(getattr(pack, "evidence_summary")) or {}
        ) or {},
        "summary": summary,
        "supporting_evidence": sup,
        "contradictory_evidence": con,
        "evidence": items,
        "similar_cases": similar_cases,
        "evidence_gaps": gaps,
        "unavailable_sources": unavailable_sources,
        "sources_checked": sources_checked,
        "limitations": list(getattr(pack, "limitations", []) or []),
        "overall_evidence_confidence": summary["overall_evidence_confidence"],
    }