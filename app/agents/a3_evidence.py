"""A3 Evidence Gathering Agent: collect 9 evidence sources, never recalc risk."""
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
LABELED_CSV = REPO_ROOT / "labeled_transactions.csv"
PROFILE_CSV = REPO_ROOT / "account_profiles.csv"

from app.schemas.evidence import EvidenceItem, EvidencePack, EvidenceSummary
from app.services import evidence_store as es
from app.services import evidence_retrieval as ret
from app.services import evidence_scoring as scoring
from app.services.store import get_investigation, log_event


def _eid(inv_id: str, etype: str) -> str:
    return f"EV_{inv_id[-6:]}_{etype[:4].upper()}_{uuid.uuid4().hex[:6].upper()}"


_A3_CACHE: dict = {}


def _load_history(account_id: str, ts_iso: str):
    try:
        import pandas as pd
        if not LABELED_CSV.exists():
            return None
        df = _A3_CACHE.get("hist")
        if df is None:
            df = pd.read_csv(LABELED_CSV, usecols=["account_id", "counterparty_name",
                          "transaction_id", "date", "amount", "type",
                          "category", "is_suspicious", "typology"],
                          low_memory=True)
            df["_d"] = pd.to_datetime(df["date"], errors="coerce", format="mixed")
            _A3_CACHE["hist"] = df
        df = df[df["account_id"].astype(str) == str(account_id)].copy()
        if df.empty:
            return df
        try:
            ts = pd.Timestamp(str(ts_iso).replace("Z", "+00:00"))
            try:
                ts = ts.tz_convert(None)
            except Exception:
                pass
            df = df[df["_d"] < ts].copy()
        except Exception:
            pass
        return df
    except Exception:
        log.exception("history load failed")
        return None


def _load_profile(account_id: str):
    try:
        import pandas as pd
        if not PROFILE_CSV.exists():
            return None
        df = pd.read_csv(PROFILE_CSV, usecols=["account_id", "holder_profile",
                          "n_transactions", "n_credits", "n_debits",
                          "total_credit_amount", "total_debit_amount",
                          "n_suspicious_txns", "dominant_typology",
                          "max_single_txn_amount", "distinct_counterparties",
                          "final_balance"], low_memory=True)
        sub = df[df["account_id"].astype(str) == str(account_id)]
        if sub.empty:
            return None
        return dict(sub.iloc[0].to_dict())
    except Exception:
        log.exception("profile load failed")
        return None


def _recency_days(ts_iso: str) -> int:
    try:
        ts = datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - ts).days)
    except Exception:
        return 0


def _unavailable(inv_id: str, etype: str, title: str, reason: str, source: str, tier: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=_eid(inv_id, etype), type=etype, direction="NEUTRAL",
        title=title, description=f"{reason} Evidence unavailable; no values fabricated.",
        actual_value=None, comparison_value=None, confidence=0.0,
        source=source, source_tier=tier, status="UNAVAILABLE",
    )


def gather(investigation_id: str, a2_override: dict | None = None) -> EvidencePack:
    inv = get_investigation(investigation_id)
    if not inv:
        raise ValueError(f"investigation {investigation_id} not found")
    txn_row = es.get_transaction_by_inv(investigation_id)
    if not txn_row:
        raise ValueError(f"transaction for {investigation_id} not found")
    payload = txn_row.get("payload") or {}
    canon = payload.get("canonical", {}) if isinstance(payload, dict) else {}
    velocity = payload.get("velocity", {}) if isinstance(payload, dict) else {}
    a2 = a2_override if a2_override else (inv.get("result") or {})
    if not isinstance(a2, dict) or "risk_score" not in a2:
        try:
            from app.services import store as st
            sec = st.get_section(investigation_id, "A2", "detection")
            if isinstance(sec, dict) and "risk_score" in sec:
                a2 = sec
        except Exception:
            log.exception("A2 section lookup failed")
    if not isinstance(a2, dict) or "risk_score" not in a2:
        raise ValueError(f"A2 result missing for {investigation_id}")
    txn_id = str(inv.get("txn_id", canon.get("transaction_id", "")))
    src_acct = str(canon.get("source_account", ""))
    dst_acct = str(canon.get("destination_account", ""))
    try:
        amount = abs(float(canon.get("amount", 0) or 0))
    except (TypeError, ValueError):
        amount = 0.0
    ts_iso = str(canon.get("timestamp", ""))
    recency = _recency_days(ts_iso)
    history_df = _load_history(src_acct, ts_iso)
    profile_row = _load_profile(src_acct)
    recent_volume = None
    daily_avg = None
    try:
        if history_df is not None and len(history_df) and "amount" in history_df.columns:
            import pandas as pd
            vals = pd.to_numeric(history_df["amount"], errors="coerce").abs().dropna()
            recent_volume = round(float(vals.tail(20).sum()), 2) if len(vals) else None
    except Exception:
        log.exception("recent_volume failed")

    items: list[EvidenceItem] = []
    status_map: dict = {}
    partial = False
    finding_keys: dict = {}

    def _push(item: EvidenceItem, category: str | None = None, fkey: str | None = None):
        items.append(item)
        if category:
            status_map[category] = item.status
        if fkey and item.status == "AVAILABLE":
            finding_keys.setdefault(fkey, []).append(item)

    # 1 behavioral deviation
    try:
        r = ret.behavioral_deviation(history_df, amount)
        if r.get("status") == "AVAILABLE":
            d = scoring.assign_direction("BEHAVIORAL_DEVIATION", r)
            items.append(EvidenceItem(
                evidence_id=_eid(investigation_id, "BEHAVIORAL_DEVIATION"),
                type="BEHAVIORAL_DEVIATION",
                direction=d, title="Amount deviation vs customer history",
                description=f"Amount {r['amount']:,.2f} may be {'inconsistent with' if d=='SUPPORTING' else 'consistent with'} history (mean {r['mean']:,.2f}, median {r['median']:,.2f}, max {r['max']:,.2f}, ratio-to-mean {r['ratio_to_mean']}). Deviation is indicative only.",
                actual_value=r["amount"], comparison_value={"mean": r["mean"], "median": r["median"], "max": r["max"], "ratio_to_mean": r["ratio_to_mean"]},
                confidence=0.0, source="INTERNAL_TXN_HISTORY", source_tier="T1", status="AVAILABLE"))
            status_map["customer_history"] = "AVAILABLE"
            finding_keys.setdefault("amount_deviation", []).append(items[-1])
        else:
            partial = True
            _push(_unavailable(investigation_id, "BEHAVIORAL_DEVIATION", "Amount deviation vs customer history", str(r.get("reason", "unavailable")), "INTERNAL_TXN_HISTORY", "T1"), "customer_history")
    except Exception as e:
        log.exception("src behavioral failed")
        partial = True
        _push(_unavailable(investigation_id, "BEHAVIORAL_DEVIATION", "Amount deviation vs customer history", f"source error: {e}", "INTERNAL_TXN_HISTORY", "T1"), "customer_history")

    # 2 beneficiary
    try:
        r = ret.beneficiary_history(history_df, dst_acct)
        if r.get("status") == "AVAILABLE":
            d = scoring.assign_direction("BENEFICIARY_HISTORY", r)
            desc = (f"Beneficiary '{r['destination']}' may be new (no prior txns seen)" if r["is_new"] else f"Beneficiary '{r['destination']}' appears known ({r['match_count']} prior, total {r['total_with_beneficiary']:,.2f}); pattern is consistent with established relationship.")
            items.append(EvidenceItem(
                evidence_id=_eid(investigation_id, "BENEFICIARY_HISTORY"), type="BENEFICIARY_HISTORY",
                direction=d, title="Beneficiary familiarity", description=desc + " Indicative only.",
                actual_value={"is_new": r["is_new"], "match_count": r["match_count"]},
                comparison_value={"total_with_beneficiary": r["total_with_beneficiary"], "first_seen": r["first_seen"]},
                confidence=0.0, source="INTERNAL_TXN_HISTORY", source_tier="T1", status="AVAILABLE"))
            status_map["beneficiary"] = "AVAILABLE"
            finding_keys.setdefault("beneficiary", []).append(items[-1])
        else:
            partial = True
            _push(_unavailable(investigation_id, "BENEFICIARY_HISTORY", "Beneficiary familiarity", str(r.get("reason", "unavailable")), "INTERNAL_TXN_HISTORY", "T1"), "beneficiary")
    except Exception as e:
        log.exception("src beneficiary failed")
        partial = True
        _push(_unavailable(investigation_id, "BENEFICIARY_HISTORY", "Beneficiary familiarity", f"source error: {e}", "INTERNAL_TXN_HISTORY", "T1"), "beneficiary")

    # 3 velocity
    try:
        r = ret.velocity_evidence(velocity, history_df, daily_avg)
        if r.get("status") == "AVAILABLE":
            d = scoring.assign_direction("VELOCITY", r)
            items.append(EvidenceItem(
                evidence_id=_eid(investigation_id, "VELOCITY"), type="VELOCITY",
                direction=d, title="Transaction velocity",
                description=f"Day-count {r['day_count']} vs daily avg {r['daily_avg']} may be {'elevated' if d=='SUPPORTING' else 'within normal range'}. Indicative only.",
                actual_value=r["day_count"], comparison_value=r["daily_avg"],
                confidence=0.0, source="INTERNAL_TXN_HISTORY", source_tier="T1", status="AVAILABLE"))
            status_map["velocity"] = "AVAILABLE"
            finding_keys.setdefault("velocity", []).append(items[-1])
        else:
            partial = True
            _push(_unavailable(investigation_id, "VELOCITY", "Transaction velocity", str(r.get("reason", "unavailable")), "INTERNAL_TXN_HISTORY", "T1"), "velocity")
    except Exception as e:
        log.exception("src velocity failed")
        partial = True
        _push(_unavailable(investigation_id, "VELOCITY", "Transaction velocity", f"source error: {e}", "INTERNAL_TXN_HISTORY", "T1"), "velocity")

    # 4 profile
    try:
        r = ret.profile_consistency(profile_row, amount, recent_volume)
        if r.get("status") == "AVAILABLE":
            d = scoring.assign_direction("PROFILE_CONSISTENCY", r)
            items.append(EvidenceItem(
                evidence_id=_eid(investigation_id, "PROFILE_CONSISTENCY"), type="PROFILE_CONSISTENCY",
                direction=d, title="Profile consistency",
                description=f"Amount {r['amount']:,.2f} vs profile avg {r['avg_txn']} (holder={r['holder_profile']}, ratio {r['ratio_to_avg']}) may be {'inconsistent with' if d=='SUPPORTING' else 'consistent with'} expected profile (post-hoc aggregate). Indicative only.",
                actual_value=r["amount"], comparison_value={"avg_txn": r["avg_txn"], "holder_profile": r["holder_profile"], "post_hoc_aggregate": True},
                confidence=0.0, source="ACCOUNT_PROFILE", source_tier="T1", status="AVAILABLE"))
            status_map["profile"] = "AVAILABLE"
            finding_keys.setdefault("profile", []).append(items[-1])
        else:
            partial = True
            _push(_unavailable(investigation_id, "PROFILE_CONSISTENCY", "Profile consistency", str(r.get("reason", "unavailable")), "ACCOUNT_PROFILE", "T1"), "profile")
    except Exception as e:
        log.exception("src profile failed")
        partial = True
        _push(_unavailable(investigation_id, "PROFILE_CONSISTENCY", "Profile consistency", f"source error: {e}", "ACCOUNT_PROFILE", "T1"), "profile")

    # 5 device (always unavailable)
    try:
        r = ret.device_evidence()
        partial = True
        items.append(_unavailable(investigation_id, "DEVICE", "Device evidence", str(r.get("reason", "unavailable")), "DEVICE_DATA", "T4"))
    except Exception as e:
        log.exception("src device failed")
        partial = True
        items.append(_unavailable(investigation_id, "DEVICE", "Device evidence", f"source error: {e}", "DEVICE_DATA", "T4"))

    # 6 location (always unavailable)
    try:
        r = ret.location_evidence()
        partial = True
        items.append(_unavailable(investigation_id, "LOCATION", "Location evidence", str(r.get("reason", "unavailable")), "LOCATION_DATA", "T4"))
    except Exception as e:
        log.exception("src location failed")
        partial = True
        items.append(_unavailable(investigation_id, "LOCATION", "Location evidence", f"source error: {e}", "LOCATION_DATA", "T4"))

    # 7 previous alerts
    try:
        r = ret.previous_alerts(src_acct)
        if r.get("status") == "AVAILABLE":
            d = scoring.assign_direction("PREVIOUS_ALERTS", r)
            items.append(EvidenceItem(
                evidence_id=_eid(investigation_id, "PREVIOUS_ALERTS"), type="PREVIOUS_ALERTS",
                direction=d, title="Previous alerts for account",
                description=f"Account shows {r['prior_count']} prior investigation(s); pattern may be {'repeated' if d=='SUPPORTING' else 'first-time'}. Indicative only.",
                actual_value=r["prior_count"], comparison_value=r["outcomes"][:5],
                confidence=0.0, source="INVESTIGATION_DB", source_tier="T1", status="AVAILABLE"))
            status_map["previous_alerts"] = "AVAILABLE"
            finding_keys.setdefault("previous_alerts", []).append(items[-1])
        else:
            partial = True
            _push(_unavailable(investigation_id, "PREVIOUS_ALERTS", "Previous alerts for account", str(r.get("reason", "unavailable")), "INVESTIGATION_DB", "T1"), "previous_alerts")
    except Exception as e:
        log.exception("src prev_alerts failed")
        partial = True
        _push(_unavailable(investigation_id, "PREVIOUS_ALERTS", "Previous alerts for account", f"source error: {e}", "INVESTIGATION_DB", "T1"), "previous_alerts")

    # 8 rule evidence (stored A2 only)
    try:
        r = ret.rule_evidence(a2)
        if r.get("status") == "AVAILABLE":
            d = scoring.assign_direction("RULE", r)
            items.append(EvidenceItem(
                evidence_id=_eid(investigation_id, "RULE"), type="RULE",
                direction=d, title="Stored rule signals (A2)",
                description=f"Stored rule_score {r['rule_score']} with typologies {r['possible_typologies']} may be {'consistent with elevated rules' if d=='SUPPORTING' else 'consistent with low rule firing'}. Referenced only, never recomputed.",
                actual_value=r["rule_score"], comparison_value={"top_reasons": r["top_reasons"], "possible_typologies": r["possible_typologies"]},
                confidence=0.0, source="A2_RESULT", source_tier="T1", status="AVAILABLE"))
            finding_keys.setdefault("rule", []).append(items[-1])
        else:
            partial = True
            items.append(_unavailable(investigation_id, "RULE", "Stored rule signals (A2)", str(r.get("reason", "unavailable")), "A2_RESULT", "T1"))
    except Exception as e:
        log.exception("src rule failed")
        partial = True
        items.append(_unavailable(investigation_id, "RULE", "Stored rule signals (A2)", f"source error: {e}", "A2_RESULT", "T1"))

    # 9 model evidence (stored A2 only)
    try:
        r = ret.model_evidence(a2)
        if r.get("status") == "AVAILABLE":
            d = scoring.assign_direction("MODEL", r)
            items.append(EvidenceItem(
                evidence_id=_eid(investigation_id, "MODEL"), type="MODEL",
                direction=d, title="Stored model signals (A2)",
                description=f"Stored risk {r['risk_score']} ({r['risk_level']}), anomaly {r['anomaly_score']} may be {'elevated' if d=='SUPPORTING' else 'low'}. Referenced only, never recomputed.",
                actual_value={"risk_score": r["risk_score"], "risk_level": r["risk_level"], "anomaly_score": r["anomaly_score"]},
                comparison_value={"shap_top": r["shap_top"], "possible_typologies": r["possible_typologies"]},
                confidence=0.0, source="A2_RESULT", source_tier="T1", status="AVAILABLE"))
            finding_keys.setdefault("model", []).append(items[-1])
        else:
            partial = True
            items.append(_unavailable(investigation_id, "MODEL", "Stored model signals (A2)", str(r.get("reason", "unavailable")), "A2_RESULT", "T1"))
    except Exception as e:
        log.exception("src model failed")
        partial = True
        items.append(_unavailable(investigation_id, "MODEL", "Stored model signals (A2)", f"source error: {e}", "A2_RESULT", "T1"))

    # corroboration + confidence second pass
    comp = scoring.completeness(status_map)
    for it in items:
        if it.status != "AVAILABLE":
            continue
        fkey = {"BEHAVIORAL_DEVIATION": "amount_deviation", "BENEFICIARY_HISTORY": "beneficiary", "VELOCITY": "velocity", "PROFILE_CONSISTENCY": "profile", "PREVIOUS_ALERTS": "previous_alerts", "RULE": "rule", "MODEL": "model"}.get(it.type, "general")
        cor = len(finding_keys.get(fkey, []))
        # cross-corroborate deviation: behavioral+profile+rule+model pointing same way
        if fkey == "amount_deviation":
            cor = max(cor, sum(1 for k in ("amount_deviation", "profile", "rule", "model") for _ in finding_keys.get(k, [])) if it.direction == "SUPPORTING" else cor)
            cor = min(cor, 4)
        try:
            it.confidence = scoring.confidence(it.source_tier, comp, recency, max(cor, 1))
        except Exception:
            it.confidence = 0.5

    pack_status = "PARTIAL" if (partial or any(i.status == "UNAVAILABLE" for i in items)) else "COMPLETE"
    supporting = sum(1 for i in items if i.direction == "SUPPORTING" and i.status == "AVAILABLE")
    contradicting = sum(1 for i in items if i.direction == "CONTRADICTING" and i.status == "AVAILABLE")
    avail_conf = [i.confidence for i in items if i.status == "AVAILABLE"]
    avg_conf = round(sum(avail_conf) / len(avail_conf), 3) if avail_conf else 0.0
    limitations = [
        *(f"{i.type}: unavailable — {i.description[:180]}" for i in items if i.status == "UNAVAILABLE"),
        "Risk scores referenced from stored A2 result only; never recalculated.",
        "Profile aggregates are post-hoc; flagged post_hoc_aggregate=True.",
        "Findings are indicative only and do not assert fraud.",
    ]
    pack = EvidencePack(
        investigation_id=investigation_id, agent="A3", status=pack_status,
        evidence_summary=EvidenceSummary(total=len(items), supporting=supporting, contradicting=contradicting, avg_confidence=avg_conf, completeness=comp, status=pack_status),
        evidence=items, limitations=limitations, transaction_id=txn_id,
    )
    try:
        es.save_evidence_pack(pack)
    except Exception:
        log.exception("save pack failed")
        raise
    try:
        log_event(investigation_id, "A3", f"EVIDENCE_GATHERED:{pack_status}")
    except Exception:
        log.exception("log_event failed")
    log.info("A3 gather %s status=%s items=%d", investigation_id, pack_status, len(items))
    return pack
