"""A8 Action Recommendation.

Consumes the canonical fusion risk score (owned by A2), evidence confidence,
graph confidence, regulatory relevance, and analysis limitations. Never recomputes
fraud probability. Produces a single canonical recommendation.
"""
import logging
from typing import Any

log = logging.getLogger(__name__)

_RECOMMENDATIONS = ["CLEAR", "MONITOR", "FURTHER_INVESTIGATION", "ESCALATE", "COMPLIANCE_REVIEW", "STR_REVIEW"]


def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    try:
        return max(lo, min(hi, float(x)))
    except Exception:
        return lo


def recommend(investigation_id: str, a2: dict, evidence_pack: dict,
              graph: dict, a5: dict) -> dict:
    risk_score = float((a2 or {}).get("risk_score") or 0)
    risk_level = str((a2 or {}).get("risk_level") or "LOW").upper()
    ev_conf = float(((evidence_pack or {}).get("evidence_summary") or {}).get("avg_confidence") or 0.0)
    graph_conf = float(((graph or {}).get("graph_risk_score") or 0)) / 100.0
    graph_conf = _clamp(graph_conf if graph_conf <= 1.0 else graph_conf)
    a5_status = str((a5 or {}).get("status") or "")
    n_citations = len((a5 or {}).get("citations") or [])
    limitations: list[str] = list((a5 or {}).get("limitations") or [])
    limitations += list((evidence_pack or {}).get("limitations") or [])
    limitations += list((graph or {}).get("limitations") or [])
    incomplete_graph = str((graph or {}).get("analysis_mode")) == "SIZE_FALLBACK" or str((graph or {}).get("status")) in ("PARTIAL", "INCOMPLETE")

    typologies = list((a2 or {}).get("possible_typologies") or [])
    reasoning: list[str] = []

    if risk_score >= 80:
        rec = "ESCALATE"
        reasoning.append(f"Canonical fusion risk score {risk_score:.1f} ({risk_level}) crosses escalation threshold (>=80).")
    elif risk_score >= 60:
        rec = "FURTHER_INVESTIGATION"
        reasoning.append(f"Risk score {risk_score:.1f} ({risk_level}) requires deeper investigation.")
    elif risk_score >= 35:
        rec = "COMPLIANCE_REVIEW"
        reasoning.append(f"Risk score {risk_score:.1f} warrants compliance review.")
    else:
        rec = "MONITOR"
        reasoning.append(f"Risk score {risk_score:.1f} is below further-investigation threshold.")

    if any(str(t).lower().startswith("struct") for t in typologies):
        rec = "STR_REVIEW" if rec in ("COMPLIANCE_REVIEW", "FURTHER_INVESTIGATION") else rec
        reasoning.append("Structuring typology flagged; STR review considered.")

    if incomplete_graph:
        rec = "FURTHER_INVESTIGATION" if rec not in ("ESCALATE", "STR_REVIEW") else rec
        reasoning.append("Graph analysis incomplete; manual review required.")
    if not n_citations:
        reasoning.append("No regulatory provisions matched; recommend re-evaluation after evidence completion.")
    if a5_status == "PARTIAL":
        reasoning.append("Regulatory mapping is provisional.")

    human_required = bool(
        risk_score >= 60
        or incomplete_graph
        or ev_conf < 0.5
        or n_citations == 0
        or rec in ("ESCALATE", "STR_REVIEW", "FURTHER_INVESTIGATION")
    )

    confidence = round(_clamp(0.4 + 0.4 * ev_conf + 0.2 * graph_conf - 0.2 * (1.0 if incomplete_graph else 0.0)), 3)

    result = {
        "investigation_id": investigation_id,
        "agent": "A8",
        "recommendation": rec,
        "reasoning": reasoning,
        "confidence": confidence,
        "human_review_required": human_required,
        "supporting": {
            "canonical_risk_score": risk_score,
            "canonical_risk_level": risk_level,
            "evidence_confidence": round(ev_conf, 3),
            "graph_risk_score": round(graph_conf * 100.0, 2),
            "regulatory_citations": n_citations,
            "incomplete_graph": incomplete_graph,
        },
        "limitations": limitations,
        "allowed_recommendations": _RECOMMENDATIONS,
        "disclaimer": (
            "Recommendation is advisory. Final action rests with a qualified human "
            "investigator / compliance officer."
        ),
    }
    return result