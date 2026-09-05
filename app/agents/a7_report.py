"""A7 Investigation Report.

Template-first investigation report. All numeric / factual sections are populated
directly from the structured agent outputs. The NVIDIA LLM is used only to connect
findings and create a readable narrative; every claim is grounded in evidence_ids or
citation_ids and the LLM is explicitly forbidden from inventing facts.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

_REPORT_SECTIONS = [
    "EXECUTIVE_SUMMARY",
    "TARGET_TRANSACTION",
    "DETECTION_FINDINGS",
    "WHY_FLAGGED",
    "RELATED_ENTITIES",
    "MONEY_FLOW",
    "EVIDENCE",
    "GRAPH_ANALYSIS",
    "REGULATORY_ASSESSMENT",
    "ANALYSIS_LIMITATIONS",
    "RECOMMENDED_NEXT_STEP",
]


def _llm_narrative(structured: dict) -> tuple[str, str, list[str]]:
    """Returns (narrative_text, source, grounded_in_ids)."""
    from app.services import llm
    if not llm.available():
        return (
            "Template-only narrative. Structured findings below; LLM unavailable.",
            "TEMPLATE",
            [],
        )
    sys_p = (
        "You are an investigation report writer. Write a concise 4-6 sentence "
        "EXECUTIVE SUMMARY that ties together the detection, evidence, graph, and "
        "regulatory findings provided. You MUST reference only the structured facts "
        "and IDs given. Do NOT invent evidence, identities, or amounts. If a finding "
        "cannot be grounded, write 'Insufficient evidence' for that point. Cite at "
        "least one evidence_id and one citation_id when available."
    )
    user_p = json.dumps(structured, indent=2)
    resp = llm.chat(sys_p, user_p, max_tokens=500)
    if not resp:
        return (
            "Template-only narrative. NVIDIA LLM call failed; structured findings below.",
            "TEMPLATE_FALLBACK",
            [],
        )
    content = resp.get("content", "")
    grounded: list[str] = []
    for ev in (structured.get("evidence") or []):
        eid = ev.get("evidence_id")
        if eid and eid in content:
            grounded.append(eid)
    for c in (structured.get("citations") or []):
        cid = c.get("id")
        if cid and cid in content:
            grounded.append(cid)
    return content, "NVIDIA_LLM", grounded


def generate(investigation_id: str, a2: dict, evidence_pack: dict,
             graph: dict, a5: dict, a8: dict) -> dict:
    txn = (evidence_pack or {}).get("transaction_id") or (a2 or {}).get("transaction_id") or ""
    risk_score = float((a2 or {}).get("risk_score") or 0)
    risk_level = str((a2 or {}).get("risk_level") or "LOW").upper()
    typologies = list((a2 or {}).get("possible_typologies") or [])
    evidence_items = list((evidence_pack or {}).get("evidence") or [])
    strongest = [e.get("evidence_id") for e in evidence_items if e.get("direction") == "SUPPORTING"][:5]
    weakest = [e.get("evidence_id") for e in evidence_items if e.get("direction") == "CONTRADICTING"][:5]
    money_flow = (graph or {}).get("money_flow") or {}
    patterns = (graph or {}).get("patterns") or {}
    detected = sorted(k for k, v in patterns.items() if isinstance(v, dict) and v.get("pattern_detected"))
    limitations = []
    limitations += list((evidence_pack or {}).get("limitations") or [])
    limitations += list((graph or {}).get("limitations") or [])
    limitations += list((a5 or {}).get("limitations") or [])

    structured = {
        "transaction_id": txn,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "typologies": typologies,
        "evidence": [
            {"evidence_id": e.get("evidence_id"), "direction": e.get("direction"),
             "title": e.get("title"), "confidence": e.get("confidence")}
            for e in evidence_items
        ],
        "graph_mode": (graph or {}).get("analysis_mode"),
        "patterns_detected": detected,
        "citations": [{"id": c.get("id"), "title": c.get("title")}
                      for c in (a5 or {}).get("citations") or []],
        "recommendation": (a8 or {}).get("recommendation"),
    }
    narrative, source, grounded = _llm_narrative(structured)

    report = {
        "investigation_id": investigation_id,
        "agent": "A7",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sections": {
            "EXECUTIVE_SUMMARY": narrative,
            "TARGET_TRANSACTION": {
                "transaction_id": txn,
                "risk_score": risk_score,
                "risk_level": risk_level,
                "possible_typologies": typologies,
            },
            "DETECTION_FINDINGS": {
                "rules_score": (a2 or {}).get("rule_score"),
                "anomaly_score": (a2 or {}).get("anomaly_score"),
                "fraud_probability": (a2 or {}).get("fraud_probability"),
                "top_reasons": (a2 or {}).get("top_reasons") or [],
            },
            "WHY_FLAGGED": {
                "typologies": typologies,
                "top_reasons": (a2 or {}).get("top_reasons") or [],
            },
            "RELATED_ENTITIES": (graph or {}).get("supporting_entities") or [],
            "MONEY_FLOW": money_flow,
            "EVIDENCE": {
                "total": (evidence_pack.get("evidence_summary") or {}).get("total") if evidence_pack else 0,
                "supporting": (evidence_pack.get("evidence_summary") or {}).get("supporting") if evidence_pack else 0,
                "contradicting": (evidence_pack.get("evidence_summary") or {}).get("contradicting") if evidence_pack else 0,
                "items": evidence_items,
                "strongest_ids": strongest,
                "contradicting_ids": weakest,
            },
            "GRAPH_ANALYSIS": {
                "mode": (graph or {}).get("analysis_mode"),
                "status": (graph or {}).get("status"),
                "node_count": (graph or {}).get("node_count"),
                "edge_count": (graph or {}).get("edge_count"),
                "patterns": detected,
                "graph_risk_score": (graph or {}).get("graph_risk_score"),
                "risk_level": (graph or {}).get("risk_level"),
                "manual_review_required": (graph or {}).get("manual_review_required"),
            },
            "REGULATORY_ASSESSMENT": {
                "jurisdiction": (a5 or {}).get("jurisdiction"),
                "potential_relevance": (a5 or {}).get("potential_regulatory_relevance") or [],
                "citations": (a5 or {}).get("citations") or [],
                "human_review_required": (a5 or {}).get("human_review_required"),
                "disclaimer": (a5 or {}).get("disclaimer"),
            },
            "ANALYSIS_LIMITATIONS": limitations,
            "RECOMMENDED_NEXT_STEP": (a8 or {}).get("recommendation"),
        },
        "narrative_source": source,
        "narrative_grounded_in": grounded,
        "disclaimer": (
            "This report is generated by an automated system. It is grounded in "
            "structured agent outputs and the cited evidence. It does not assert "
            "fraud or guilt. Final decision rests with a human investigator."
        ),
    }
    return report