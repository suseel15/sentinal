"""End-to-End Investigation Orchestrator — Phase 14 Integration.

Pipeline (state machine):

    START
      │
      ▼
   A1 INGESTION  ────────────► DUPLICATE_LOGGED (terminal)
      │
      ▼
   A2 DETECTION (single owner of risk_score)
      │
      ▼
   ROUTING
      │
      ├── risk_score < low_max       → AUTO_CLOSED (terminal)
      │
      └── risk_score >= inv_min      → INVESTIGATION
                                       │
                                       ▼
                                  PARALLEL ──┬── A3 EVIDENCE
                                             └── A4 GRAPH
                                       │
                                       ▼
                                  A5 REGULATORY
                                       │
                                       ▼
                                  A8 RECOMMENDATION
                                       │
                                       ▼
                                  A7 REPORT
                                       │
                                       ▼
                                  WAITING_FOR_HUMAN
                                       │
                                       ▼
                                  HUMAN DECISION → COMPLETED / ESCALATED

Each agent only writes to its own `agent_sections` row. Status updates
are visible via `investigation_state.status`. Audit events are written
for every stage. Every failure returns an explicit status — never silent.

The module is designed to be LangGraph-compatible: every transition is
an explicit function. A future swap to LangGraph only needs to wrap the
pipeline functions as nodes.
"""
from __future__ import annotations

import concurrent.futures
import json
import logging
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LABELED_CSV = REPO_ROOT / "labeled_transactions.csv"

DEFAULT_LOW_THRESHOLD = 30
DEFAULT_INVESTIGATION_THRESHOLD = 60
PARALLEL_TIMEOUT_S = 120
RECOMMENDATION_CONFIDENCE_AUTO_CLOSE = 0.95

_state_lock = threading.Lock()
PIPELINE_TIMEOUTS = {
    "A1": 30,
    "A2": 60,
    "A3": PARALLEL_TIMEOUT_S,
    "A4": PARALLEL_TIMEOUT_S,
    "A5": 60,
    "A7": 60,
    "A8": 30,
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_thresholds() -> tuple[int, int]:
    p = REPO_ROOT / "config" / "thresholds.json"
    try:
        if p.exists():
            cfg = json.loads(p.read_text())
            low = int(cfg.get("low_risk_max", DEFAULT_LOW_THRESHOLD))
            inv = int(cfg.get("investigation_min", DEFAULT_INVESTIGATION_THRESHOLD))
            return low, inv
    except Exception:
        log.exception("thresholds read failed")
    return DEFAULT_LOW_THRESHOLD, DEFAULT_INVESTIGATION_THRESHOLD


def _load_transaction_row(transaction_id: str) -> dict | None:
    try:
        from app.services import datasets as ds
        row = ds.load_txn_row(str(transaction_id))
        if row:
            return row
    except Exception:
        log.exception("datasets transaction lookup failed")
    if not LABELED_CSV.exists():
        return None
    try:
        import pandas as pd
        df = pd.read_csv(LABELED_CSV, low_memory=True)
        sub = df[df["transaction_id"].astype(str) == str(transaction_id)]
        if sub.empty:
            return None
        return dict(sub.iloc[0].to_dict())
    except Exception:
        log.exception("transaction lookup failed")
        return None


def _canonical_from_row(row: dict) -> dict:
    if "source_account" in row and "destination_account" in row:
        out = dict(row)
        out.setdefault("transaction_id", str(row.get("transaction_id", "")))
        out.setdefault("transaction_type", str(row.get("transaction_type") or row.get("type") or "DEBIT").upper())
        out.setdefault("category", str(row.get("category") or row.get("merchant_category") or "TRANSFER"))
        out.setdefault("currency", str(row.get("currency", "INR")))
        out.setdefault("channel", str(row.get("channel", "ONLINE")))
        out.setdefault("timestamp", str(row.get("timestamp") or row.get("date") or _now()))
        return out
    amt = float(row.get("amount") or 0)
    ttype = str(row.get("transaction_type") or row.get("type") or "DEBIT").upper()
    ts = row.get("timestamp") if "timestamp" in row else row.get("date")
    out = {
        "transaction_id": str(row.get("transaction_id", "")),
        "source_account": str(row.get("sender_account_id") or row.get("account_id", "UNK")),
        "destination_account": str(row.get("receiver_account_id") or row.get("counterparty_name", "UNK")),
        "amount": abs(amt),
        "timestamp": str(ts if ts not in (None, "") else _now()),
        "transaction_type": ttype,
        "category": str(row.get("merchant_category") or row.get("category", "TRANSFER")),
        "currency": str(row.get("currency", "INR")),
        "channel": str(row.get("channel", "ONLINE")),
    }
    for k in ("device_id", "ip_address", "location", "channel",
              "sender_customer_id", "receiver_customer_id",
              "sender_bank", "receiver_bank", "sender_country", "receiver_country",
              "transaction_status", "merchant_category", "transaction_type"):
        if k in row and row[k] not in (None, "") and k not in out:
            out[k] = row[k]
    for k in ("device_id", "ip_address", "location",
              "sender_customer_id", "receiver_customer_id",
              "sender_bank", "receiver_bank"):
        if k in row and row[k] not in (None, ""):
            out[k] = row[k]
    return out


def _build_triage_decision(triage_score: float) -> str:
    low_max, _ = _load_thresholds()
    return "LOG_ONLY" if triage_score < (low_max / 100.0) else "FULL_INVESTIGATION"


def _ingest_with_a1(canonical: dict) -> dict:
    """A1: validate+normalize+dedup+create investigation id."""
    from app.agents.a1_ingestion import A1Agent
    a1 = A1Agent()
    raw = {
        "transaction_id": canonical.get("transaction_id"),
        "account_id": canonical.get("source_account") or canonical.get("account_id") or "UNK",
        "counterparty_name": canonical.get("destination_account") or canonical.get("counterparty_name") or "UNK",
        "amount": float(canonical.get("amount", 0) or 0),
        "currency": canonical.get("currency", "INR"),
        "date": canonical.get("timestamp") or canonical.get("date") or _now(),
        "type": canonical.get("transaction_type") or canonical.get("type") or "DEBIT",
        "category": canonical.get("category", "TRANSFER"),
        "channel": canonical.get("channel", "ONLINE"),
        "source_system": "STREAM",
    }
    try:
        resp = a1.ingest(raw, source_system="STREAM")
        return {
            "investigation_id": resp.investigation_id,
            "transaction_id": resp.transaction_id,
            "triage": resp.triage.model_dump() if hasattr(resp.triage, "model_dump") else dict(resp.triage),
            "duplicate": resp.duplicate,
            "detection": resp.detection,
        }
    except Exception as e:
        log.exception("A1 ingest failed")
        return {"error": str(e), "raw": canonical}


def _run_a2(canonical: dict, triage: dict) -> dict:
    from app.agents import a2_detection
    try:
        return a2_detection.run(canonical)
    except Exception as e:
        log.exception("A2 failed; rules-only fallback")
        return {
            "risk_score": float(triage.get("triage_score", 0) or 0) * 100.0,
            "risk_level": "MED",
            "fraud_probability": 0.0,
            "anomaly_score": 0.0,
            "rule_score": float(triage.get("triage_score", 0) or 0) * 100.0,
            "possible_typologies": [],
            "top_reasons": list(triage.get("reasons") or []),
            "ml_unavailable": True,
            "models": {"xgboost": 0, "isolation_forest": 0, "behavioral": 0,
                       "rules": float(triage.get("triage_score", 0) or 0),
                       "velocity": 0, "customer_risk": 0},
            "rules": {"aml_rule_count": 0, "fraud_rule_count": 0, "rule_count": 0,
                      "max_severity": "NONE", "rule_score": 0, "triggered_rules": []},
            "error": str(e),
        }


def _run_a3(inv_id: str, a2: dict | None = None, canonical: dict | None = None) -> dict:
    from app.agents import a3_evidence
    from app.agents.a3_postprocess import augment
    try:
        pack = a3_evidence.gather(inv_id, a2_override=a2)
        return augment(pack, canonical=canonical, a2=a2 or {})
    except Exception as e:
        log.exception("A3 failed")
        return {
            "investigation_id": inv_id, "agent": "A3", "status": "UNAVAILABLE",
            "error": str(e), "supporting_evidence": [], "contradictory_evidence": [],
            "evidence": [], "similar_cases": [], "evidence_gaps": [],
            "unavailable_sources": [], "sources_checked": [],
            "overall_evidence_confidence": 0.0,
        }


def _run_a4(inv_id: str) -> dict:
    from app.agents import a4_graph
    try:
        r = a4_graph.analyze(inv_id)
        return r.model_dump() if hasattr(r, "model_dump") else dict(r)
    except Exception as e:
        log.exception("A4 failed")
        return {"status": "INCOMPLETE", "investigation_id": inv_id, "error": str(e)}


def _run_a5(a2: dict, evidence_pack: dict, graph: dict) -> dict:
    from app.agents import a5_regulatory
    inv_id = (evidence_pack or {}).get("investigation_id") or (graph or {}).get("investigation_id") or ""
    try:
        res = a5_regulatory.analyze(inv_id, a2, evidence_pack, graph)
        try:
            res = a5_regulatory.explain_with_llm(res)
        except Exception:
            log.exception("A5 LLM explain failed")
        return res
    except Exception as e:
        log.exception("A5 failed")
        return {
            "investigation_id": inv_id, "agent": "A5", "status": "UNAVAILABLE",
            "error": str(e), "potential_regulatory_relevance": [],
            "citations": [], "human_review_required": True,
            "limitations": ["regulatory analysis unavailable"],
        }


def _run_a7(a2: dict, evidence_pack: dict, graph: dict, a5: dict, a8: dict) -> dict:
    from app.agents import a7_report
    inv_id = (evidence_pack or {}).get("investigation_id") or (graph or {}).get("investigation_id") or ""
    try:
        return a7_report.generate(inv_id, a2, evidence_pack, graph, a5, a8)
    except Exception as e:
        log.exception("A7 failed")
        return {"investigation_id": inv_id, "agent": "A7", "error": str(e),
                "sections": {"ANALYSIS_LIMITATIONS": ["report generation failed"]}}


def _run_a8(a2: dict, evidence_pack: dict, graph: dict, a5: dict) -> dict:
    from app.agents import a8_recommendation
    inv_id = (evidence_pack or {}).get("investigation_id") or (graph or {}).get("investigation_id") or ""
    try:
        return a8_recommendation.recommend(inv_id, a2, evidence_pack, graph, a5)
    except Exception as e:
        log.exception("A8 failed")
        return {
            "investigation_id": inv_id, "agent": "A8", "recommendation": "FURTHER_INVESTIGATION",
            "reasoning": [f"recommender unavailable: {e}"], "confidence": 0.0,
            "human_review_required": True,
        }


def _persist_section(inv_id: str, agent: str, section: str, payload: dict) -> None:
    from app.services import store as st
    st.save_section(inv_id, agent, section, payload or {})


def _set_status(inv_id: str, status: str, risk_score: float | None = None,
                risk_level: str | None = None) -> None:
    from app.services import store as st
    st.update_status(inv_id, status, risk_score, risk_level)
    try:
        st.log_event(inv_id, "ORCHESTRATOR", f"STATUS:{status}")
    except Exception:
        log.exception("log_event failed")


def _persist_agent_sections(inv_id: str, a2: dict, evidence_pack: dict,
                            graph: dict, a5: dict, a7: dict, a8: dict) -> None:
    if a2:
        _persist_section(inv_id, "A2", "detection", a2)
    if evidence_pack:
        _persist_section(inv_id, "A3", "evidence", evidence_pack)
    if graph:
        _persist_section(inv_id, "A4", "graph", graph)
    if a5:
        _persist_section(inv_id, "A5", "regulatory", a5)
    if a7:
        _persist_section(inv_id, "A7", "report", a7)
    if a8:
        _persist_section(inv_id, "A8", "recommendation", a8)


def _store_feedback(inv_id: str, txn_id: str, a2: dict, evidence_pack: dict,
                    graph: dict, a8: dict, human: dict | None) -> None:
    try:
        from app.services import store as st
        st.save_feedback(
            inv_id=inv_id,
            txn_id=txn_id,
            features={
                "evidence_summary": (evidence_pack or {}).get("evidence_summary"),
                "evidence_count": (evidence_pack or {}).get("evidence_summary", {}).get("total") if evidence_pack else 0,
            },
            original_risk=float((a2 or {}).get("risk_score") or 0),
            ml_predictions={
                "fraud_probability": (a2 or {}).get("fraud_probability"),
                "anomaly_score": (a2 or {}).get("anomaly_score"),
                "rule_score": (a2 or {}).get("rule_score"),
                "typologies": (a2 or {}).get("possible_typologies"),
            },
            rules_triggered={"top_reasons": (a2 or {}).get("top_reasons") or []},
            graph_features={
                "analysis_mode": (graph or {}).get("analysis_mode"),
                "graph_risk_score": (graph or {}).get("graph_risk_score"),
                "patterns": list(((graph or {}).get("patterns") or {}).keys()),
            },
            recommendation=(a8 or {}).get("recommendation"),
            human_decision=(human or {}).get("decision"),
            confirmed_outcome=(human or {}).get("confirmed_outcome"),
        )
    except Exception:
        log.exception("feedback storage failed")


def start_from_transaction_id(transaction_id: str, run_async: bool = True) -> dict:
    """POST /investigations/start payload = {transaction_id}."""
    row = _load_transaction_row(transaction_id)
    if not row:
        return {"error": "transaction_not_found", "transaction_id": transaction_id}
    return start_from_payload(_canonical_from_row(row), run_async=run_async)


def start_from_payload(payload: dict, run_async: bool = True) -> dict:
    canonical = _canonical_from_row(payload) if ("account_id" in payload or "sender_account_id" in payload) else dict(payload)
    tid = str(canonical.get("transaction_id") or "")
    if not tid:
        canonical["transaction_id"] = f"TXN-LIVE-{uuid.uuid4().hex[:8].upper()}"
        tid = canonical["transaction_id"]
    if run_async:
        t = threading.Thread(target=_run_pipeline, args=(canonical,), daemon=True)
        t.start()
        return {"investigation_id": "", "transaction_id": tid, "status": "STARTED_ASYNC"}
    return _run_pipeline(canonical)


# ----- state-machine steps --------------------------------------------
def _step_a1(canonical: dict) -> dict:
    return _ingest_with_a1(canonical)


def _step_a2(canonical: dict, triage: dict, a1_detection: dict | None) -> dict:
    return a1_detection or _run_a2(canonical, triage)


def _route(a2: dict, triage: dict, low_max: int, inv_min: int) -> str:
    tri_decision = triage.get("decision") or _build_triage_decision(float(triage.get("triage_score") or 0))
    risk = float(a2.get("risk_score") or 0)
    if tri_decision != "FULL_INVESTIGATION" and risk < float(inv_min):
        return "AUTO_CLOSED"
    if risk < float(low_max):
        return "AUTO_CLOSED"
    return "FULL_INVESTIGATION"


def _step_parallel_a3_a4(inv_id: str, canonical: dict, a2: dict) -> tuple[dict, dict]:
    """Run A3 and A4 concurrently with explicit timeouts."""
    evidence_pack: dict = {}
    graph: dict = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_a3 = ex.submit(_run_a3, inv_id, a2, canonical)
        f_a4 = ex.submit(_run_a4, inv_id)
        try:
            evidence_pack = f_a3.result(timeout=PIPELINE_TIMEOUTS["A3"]) or {}
        except concurrent.futures.TimeoutError:
            log.exception("A3 timeout")
            evidence_pack = {"status": "UNAVAILABLE", "investigation_id": inv_id, "error": "timeout"}
        except Exception as e:
            log.exception("A3 result failed")
            evidence_pack = {"status": "UNAVAILABLE", "investigation_id": inv_id, "error": str(e)}
        try:
            graph = f_a4.result(timeout=PIPELINE_TIMEOUTS["A4"]) or {}
        except concurrent.futures.TimeoutError:
            log.exception("A4 timeout")
            graph = {"status": "INCOMPLETE", "investigation_id": inv_id, "error": "timeout"}
        except Exception as e:
            log.exception("A4 result failed")
            graph = {"status": "INCOMPLETE", "investigation_id": inv_id, "error": str(e)}
    return evidence_pack, graph


# ----- main pipeline ----------------------------------------------------
def _run_pipeline(canonical: dict) -> dict:
    """Synchronous execution of the full state machine; safe to call from a worker thread."""
    from app.services import store as st
    low_max, inv_min = _load_thresholds()
    inv_id = ""
    txn_id = str(canonical.get("transaction_id", ""))
    try:
        # ---- A1 ------------------------------------------------------
        a1_out = _step_a1(canonical)
        if "error" in a1_out and not a1_out.get("investigation_id"):
            return {"status": "FAILED", "stage": "A1", "error": a1_out["error"]}
        inv_id = a1_out["investigation_id"]
        txn_id = a1_out["transaction_id"]
        st.save_state(inv_id, txn_id, "A1_COMPLETED", None, None, payload={"canonical": canonical})
        st.log_event(inv_id, "A1", "INGESTED")
        _set_status(inv_id, "A1_COMPLETED")

        if a1_out.get("duplicate"):
            existing = a1_out.get("detection") or {}
            st.update_status(inv_id, "DUPLICATE_LOGGED")
            return {"investigation_id": inv_id, "transaction_id": txn_id, "status": "DUPLICATE_LOGGED",
                    "detection": existing}

        triage = a1_out.get("triage") or {}

        # ---- A2 ------------------------------------------------------
        a2 = _step_a2(canonical, triage, a1_out.get("detection"))
        _persist_section(inv_id, "A2", "detection", a2)
        risk_score = float(a2.get("risk_score") or 0)
        risk_level = str(a2.get("risk_level") or "LOW").upper()
        _set_status(inv_id, "A2_COMPLETED", risk_score, risk_level)

        # ---- ROUTER --------------------------------------------------
        decision = _route(a2, triage, low_max, inv_min)
        if decision == "AUTO_CLOSED":
            _set_status(inv_id, "AUTO_CLOSED", risk_score, risk_level)
            try:
                _persist_section(inv_id, "A8", "recommendation",
                                 {"recommendation": "CLEAR",
                                  "reasoning": ["Below investigation threshold; auto-closed."],
                                  "confidence": 0.0,
                                  "human_review_required": False,
                                  "auto_closed": True})
            except Exception:
                log.exception("auto-close persist failed")
            return {"investigation_id": inv_id, "transaction_id": txn_id,
                    "status": "AUTO_CLOSED", "risk_score": risk_score,
                    "risk_level": risk_level}

        _set_status(inv_id, "INVESTIGATION_STARTED", risk_score, risk_level)

        # ---- PARALLEL: A3 + A4 --------------------------------------
        _set_status(inv_id, "A3_PROCESSING")
        _set_status(inv_id, "A4_PROCESSING")
        evidence_pack, graph = _step_parallel_a3_a4(inv_id, canonical, a2)
        _persist_section(inv_id, "A3", "evidence", evidence_pack)
        _persist_section(inv_id, "A4", "graph", graph)
        _set_status(inv_id, "A3_COMPLETED")
        _set_status(inv_id, "A4_COMPLETED")

        # ---- A5 ------------------------------------------------------
        _set_status(inv_id, "A5_PROCESSING")
        a5 = _run_a5(a2, evidence_pack, graph)
        _persist_section(inv_id, "A5", "regulatory", a5)
        _set_status(inv_id, "A5_COMPLETED")

        # ---- A8 (before A7) -----------------------------------------
        _set_status(inv_id, "A8_PROCESSING")
        a8 = _run_a8(a2, evidence_pack, graph, a5)
        _persist_section(inv_id, "A8", "recommendation", a8)

        # ---- A7 ------------------------------------------------------
        _set_status(inv_id, "REPORT_GENERATING")
        a7 = _run_a7(a2, evidence_pack, graph, a5, a8)
        _persist_section(inv_id, "A7", "report", a7)
        _set_status(inv_id, "RECOMMENDATION_READY")

        _set_status(inv_id, "WAITING_FOR_HUMAN", risk_score, risk_level)
        try:
            _store_feedback(inv_id, txn_id, a2, evidence_pack, graph, a8, None)
        except Exception:
            log.exception("feedback storage failed (pre-decision)")

        return {
            "investigation_id": inv_id, "transaction_id": txn_id,
            "status": "WAITING_FOR_HUMAN", "risk_score": risk_score, "risk_level": risk_level,
            "recommendation": a8.get("recommendation"), "report_available": True,
        }
    except Exception as e:
        log.exception("pipeline failed for %s", txn_id)
        if inv_id:
            _set_status(inv_id, "FAILED")
            try:
                st.log_event(inv_id, "ORCHESTRATOR", f"PIPELINE_FAILED:{e}")
            except Exception:
                pass
        return {"status": "FAILED", "error": str(e), "transaction_id": txn_id,
                "investigation_id": inv_id}


def submit_human_decision(investigation_id: str, investigator_id: str, decision: str,
                          justification: str | None = None,
                          confirmed_outcome: str | None = None) -> dict:
    """Persist a human investigator's decision; never overwrites the AI recommendation."""
    from app.services import store as st
    allowed = {"ACCEPT", "OVERRIDE", "REQUEST_MORE_EVIDENCE", "ESCALATE"}
    decision = str(decision or "").upper()
    if decision not in allowed:
        return {"error": f"decision must be one of {sorted(allowed)}"}
    inv = st.get_investigation(investigation_id)
    if not inv:
        return {"error": "investigation_not_found"}
    original = ""
    try:
        sec = st.get_section(investigation_id, "A8", "recommendation") or {}
        original = str(sec.get("recommendation") or "")
    except Exception:
        log.exception("read original recommendation failed")
    st.save_human_decision(investigation_id, investigator_id, decision, original, justification)
    new_status = "COMPLETED" if decision in ("ACCEPT", "OVERRIDE") else "REQUESTED_MORE_EVIDENCE" if decision == "REQUEST_MORE_EVIDENCE" else "ESCALATED"
    _set_status(investigation_id, new_status)
    try:
        a2 = st.get_section(investigation_id, "A2", "detection") or {}
        ev = st.get_section(investigation_id, "A3", "evidence") or {}
        g = st.get_section(investigation_id, "A4", "graph") or {}
        rec = st.get_section(investigation_id, "A8", "recommendation") or {}
        st.save_feedback(
            inv_id=investigation_id,
            txn_id=str(inv.get("txn_id", "")),
            features={"evidence_summary": (ev or {}).get("evidence_summary")},
            original_risk=float((a2 or {}).get("risk_score") or 0),
            ml_predictions={"fraud_probability": (a2 or {}).get("fraud_probability"),
                            "anomaly_score": (a2 or {}).get("anomaly_score"),
                            "rule_score": (a2 or {}).get("rule_score")},
            rules_triggered={"top_reasons": (a2 or {}).get("top_reasons") or []},
            graph_features={"analysis_mode": (g or {}).get("analysis_mode"),
                            "graph_risk_score": (g or {}).get("graph_risk_score"),
                            "patterns": list(((g or {}).get("patterns") or {}).keys())},
            recommendation=str((rec or {}).get("recommendation") or ""),
            human_decision=decision,
            confirmed_outcome=confirmed_outcome,
        )
    except Exception:
        log.exception("feedback update failed")
    return {
        "investigation_id": investigation_id,
        "decision": decision,
        "original_recommendation": original,
        "status": new_status,
    }