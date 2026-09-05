"""A5 Regulatory Intelligence (lightweight RAG).

Retrieves structured investigation facts, maps them to a small built-in regulatory
corpus using deterministic keyword/tag matching, validates that every cited provision
actually exists in the corpus, and finally asks the NVIDIA LLM to produce an
explanation grounded in those provisions.

No external paid services are required. The corpus lives in JSON inside the package.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
CORPUS_PATH = Path(__file__).resolve().parent.parent / "data" / "regulatory_corpus.json"

_JURISDICTION_DEFAULT = os.environ.get("SENTINEL_JURISDICTION", "IN")

_FALLBACK_CORPUS: list[dict] = [
    {
        "id": "IN_PMLA_2002_S3",
        "jurisdiction": "IN",
        "title": "Prevention of Money Laundering Act, 2002 — Sec. 3",
        "summary": "Offence of money-laundering: whosover directly or indirectly attempts to indulge or knowingly assists, or knowingly is a party to or is actually involved in any process or activity connected with the proceeds of crime and projecting it as untainted property is guilty of offence of money-laundering.",
        "tags": ["money_laundering", "layering", "placement", "integration", "high_value"],
    },
    {
        "id": "IN_RBI_KYC_2016",
        "jurisdiction": "IN",
        "title": "RBI Master Direction — KYC (2016, updated)",
        "summary": "Customer Due Diligence requires banks to verify customer identity, beneficial ownership, risk profile, and ongoing monitoring of transactions inconsistent with the customer's profile.",
        "tags": ["kyc", "cdd", "customer_profile", "behavioral_deviation", "monitoring"],
    },
    {
        "id": "IN_RBI_STR_2017",
        "jurisdiction": "IN",
        "title": "RBI Master Direction — Suspicious Transaction Reporting",
        "summary": "Reporting entities shall report suspicious transactions to the FIU-IND irrespective of the amount involved. STR must include reasons for suspicion.",
        "tags": ["str", "suspicious_transaction", "fiu", "reporting"],
    },
    {
        "id": "FATF_REC_10",
        "jurisdiction": "GLOBAL",
        "title": "FATF Recommendation 10 — Customer Due Diligence",
        "summary": "Financial institutions should undertake CDD when establishing business relations, carrying out occasional transactions, when there is suspicion of money-laundering, or when there are doubts about the veracity of previously obtained customer identification data.",
        "tags": ["cdd", "kyc", "suspicion", "high_risk_country"],
    },
    {
        "id": "FATF_REC_20",
        "jurisdiction": "GLOBAL",
        "title": "FATF Recommendation 20 — Suspicious Transaction Reports",
        "summary": "If a financial institution suspects or has reasonable grounds to suspect that funds are connected to criminal activity, it should report promptly to the financial intelligence unit.",
        "tags": ["str", "reporting", "suspicion"],
    },
    {
        "id": "FATF_TYPOLOGIES_MULE",
        "jurisdiction": "GLOBAL",
        "title": "FATF Money Mule Typologies",
        "summary": "Mule networks are characterized by rapid pass-through of funds across multiple accounts, often newly opened, with limited retention and frequent use of intermediaries that act as hubs.",
        "tags": ["mule", "pass_through", "rapid_layering", "fan_in", "fan_out", "hub_aware"],
    },
    {
        "id": "FATF_TYPOLOGIES_STRUCTURING",
        "jurisdiction": "GLOBAL",
        "title": "FATF Structuring / Smurfing Typologies",
        "summary": "Breaking transactions into amounts designed to evade reporting thresholds, often across multiple accounts, beneficiaries, or time windows.",
        "tags": ["structuring", "smurfing", "threshold_evasion"],
    },
    {
        "id": "IN_RBI_HUB_PAYMENT_GATEWAYS",
        "jurisdiction": "IN",
        "title": "RBI Guidelines on Payment Gateways and Hubs",
        "summary": "Payment aggregators and hubs often appear high-degree in transaction networks. Such high-degree nodes are not inherently suspicious; risk must be assessed by the role they play in the specific flow.",
        "tags": ["hub", "payment_gateway", "supernode", "false_positive"],
    },
]


def _load_corpus() -> list[dict]:
    try:
        if CORPUS_PATH.exists():
            data = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
            if isinstance(data, list) and data:
                return data
    except Exception:
        log.exception("corpus load failed; using fallback")
    return list(_FALLBACK_CORPUS)


_CORPUS: list[dict] | None = None


def corpus() -> list[dict]:
    global _CORPUS
    if _CORPUS is None:
        _CORPUS = _load_corpus()
    return _CORPUS


def _tags_from_investigation(a2: dict, evidence: dict, graph: dict) -> set[str]:
    tags: set[str] = set()
    risk_level = str(a2.get("risk_level", "")).upper()
    if risk_level in ("MED", "MEDIUM", "HIGH"):
        tags.add("suspicion")
        tags.add("str")
    typologies = a2.get("possible_typologies") or []
    for t in typologies:
        ts = str(t).lower()
        if "lay" in ts:
            tags.update({"layering", "money_laundering", "rapid_layering"})
        if "struct" in ts or "smurf" in ts:
            tags.update({"structuring", "smurfing", "threshold_evasion"})
        if "mule" in ts:
            tags.update({"mule", "pass_through"})
    amt = float(a2.get("risk_score") or 0)
    if amt >= 80:
        tags.update({"high_value", "high_risk_country"})
    patterns = ((graph or {}).get("patterns") or {})
    for k, v in patterns.items():
        try:
            if (v or {}).get("pattern_detected"):
                tags.add(str(k))
        except Exception:
            continue
    if ((graph or {}).get("analysis_mode")) == "HUB_AWARE":
        tags.update({"hub_aware", "supernode"})
    if (evidence or {}).get("summary", {}).get("supporting", 0) > 0:
        tags.update({"behavioral_deviation", "customer_profile"})
    if (evidence or {}).get("summary", {}).get("contradicting", 0) > 0:
        tags.add("cdd")
    return tags


def retrieve(jurisdiction: str | None, tags: set[str]) -> list[dict]:
    jur = (jurisdiction or _JURISDICTION_DEFAULT).upper()
    out: list[tuple[int, dict]] = []
    for prov in corpus():
        prov_tags = set(prov.get("tags") or [])
        prov_jur = str(prov.get("jurisdiction", "GLOBAL")).upper()
        score = len(tags & prov_tags)
        if prov_jur == jur:
            score += 2
        elif prov_jur == "GLOBAL" and jur != "GLOBAL":
            score += 1
        if score > 0:
            out.append((score, prov))
    out.sort(key=lambda x: (-x[0], x[1]["id"]))
    return [p for _, p in out[:5]]


def analyze(investigation_id: str, a2: dict, evidence_pack: dict,
            graph: dict, jurisdiction: str | None = None) -> dict:
    """Returns canonical A5 result; never fabricates citations."""
    tags = _tags_from_investigation(a2 or {}, evidence_pack or {}, graph or {})
    jur = jurisdiction or _JURISDICTION_DEFAULT
    citations = retrieve(jur, tags)
    provisions = [
        {
            "id": c["id"],
            "title": c["title"],
            "jurisdiction": c.get("jurisdiction"),
            "matched_tags": sorted(tags & set(c.get("tags") or [])),
            "excerpt": (c.get("summary") or "")[:240],
        }
        for c in citations
    ]
    matched_tags = sorted({t for p in provisions for t in p["matched_tags"]})
    limitations = []
    if not provisions:
        limitations.append("No regulatory provisions matched the investigation profile.")
    if (graph or {}).get("analysis_mode") == "SIZE_FALLBACK":
        limitations.append("Graph analysis incomplete; regulatory mapping is provisional.")
    if (evidence_pack or {}).get("status") in ("PARTIAL", "UNAVAILABLE"):
        limitations.append("Evidence is partial; regulatory relevance subject to change.")
    result = {
        "investigation_id": investigation_id,
        "agent": "A5",
        "jurisdiction": jur,
        "matched_tags": matched_tags,
        "potential_regulatory_relevance": [
            f"{p['id']} — {p['title']}" for p in provisions
        ],
        "citations": provisions,
        "human_review_required": True,
        "limitations": limitations,
        "disclaimer": (
            "Regulatory assessment is informational. It does not constitute a legal "
            "conclusion and requires confirmation by a qualified compliance officer."
        ),
        "status": "COMPLETE" if provisions else "PARTIAL",
    }
    return result


def explain_with_llm(a5: dict) -> dict:
    """Optional NVIDIA LLM explanation grounded in citations only."""
    from app.services import llm
    citations = a5.get("citations") or []
    if not llm.available() or not citations:
        a5["narrative"] = (
            "Template-only narrative: regulatory relevance is established by deterministic "
            "tag-based retrieval. Citations are listed below; no LLM elaboration was performed."
        )
        a5["narrative_source"] = "TEMPLATE"
        a5["narrative_grounded_in"] = [c["id"] for c in citations]
        return a5
    sys_p = (
        "You are a compliance assistant. Explain WHY each cited provision is relevant to "
        "the investigation based ONLY on the structured facts and the citation excerpts "
        "provided. Never invent facts. Reference each provision by its id. If a finding "
        "cannot be grounded in the inputs, say 'Insufficient evidence' for that point."
    )
    user_p = json.dumps({
        "matched_tags": a5.get("matched_tags", []),
        "citations": citations,
        "instruction": (
            "Return a short explanation per citation (2-3 sentences), referencing only "
            "the provided citation ids and tags. Do not introduce new facts."
        ),
    }, indent=2)
    resp = llm.chat(sys_p, user_p, max_tokens=500)
    if not resp:
        a5["narrative"] = (
            "Template-only narrative: regulatory relevance is established by deterministic "
            "tag-based retrieval. Citations are listed below; NVIDIA LLM call failed or was "
            "disabled."
        )
        a5["narrative_source"] = "TEMPLATE_FALLBACK"
    else:
        a5["narrative"] = resp.get("content", "")
        a5["narrative_source"] = "NVIDIA_LLM"
        a5["narrative_model"] = resp.get("model")
    a5["narrative_grounded_in"] = [c["id"] for c in citations]
    return a5