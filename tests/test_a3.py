"""A3 tests: pytest-style, runnable via plain python (no pytest dep)."""
import logging
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("test_a3")

import pandas as pd


def _hist(amounts, cp="KNOWN_CP", start="2025-09-01"):
    n = len(amounts)
    return pd.DataFrame({
        "account_id": ["ACC_TEST"] * n,
        "counterparty_name": [cp] * n,
        "transaction_id": [f"TX{i}" for i in range(n)],
        "date": pd.date_range(start, periods=n, freq="D").astype(str),
        "amount": amounts,
        "type": ["DEBIT"] * n,
        "is_suspicious": [0] * n,
        "typology": ["NONE"] * n,
    })


def _a2(high=True):
    if high:
        return {"transaction_id": "tx1", "risk_score": 85.0, "risk_level": "HIGH",
                "rule_score": 60, "anomaly_score": 0.9,
                "possible_typologies": ["MULE"], "top_reasons": ["large amount", "new beneficiary"],
                "shap": {"top_features": [{"feature": "amount", "value": 1.0}], "sentence": "Amount drove risk."}}
    return {"transaction_id": "tx1", "risk_score": 12.0, "risk_level": "LOW",
            "rule_score": 0, "anomaly_score": 0.05,
            "possible_typologies": [], "top_reasons": ["normal pattern"],
            "shap": {"top_features": [], "sentence": "Low risk."}}


def _e2e_inv(suffix=""):
    from app.agents.a1_ingestion import A1Agent
    from app.services.evidence_store import init as einit
    from app.services.store import save_investigation
    einit()
    agent = A1Agent()
    dest = f"E2E_NEW_CP_{suffix}_{uuid.uuid4().hex[:5]}"
    raw = {"source_account": "ACC00008", "destination_account": dest,
           "amount": 850000, "timestamp": "2025-09-15T02:30:00",
           "transaction_type": "TRANSFER", "tms_alert": True}
    resp = agent.ingest(raw, "canonical")
    inv_id = resp.investigation_id if hasattr(resp, "investigation_id") else resp["investigation_id"]
    txn_id = resp.transaction_id if hasattr(resp, "transaction_id") else resp["transaction_id"]
    a2 = {"transaction_id": txn_id, "risk_score": 85.0, "risk_level": "HIGH",
          "rule_score": 60, "anomaly_score": 0.9,
          "possible_typologies": ["MULE"], "top_reasons": ["large amount", "new beneficiary"],
          "shap": {"top_features": [{"feature": "amount", "value": 1.0}], "sentence": "Amount drove risk."}}
    save_investigation(inv_id, txn_id, "OPEN", a2)
    return inv_id


def test_high_deviation():
    from app.services import evidence_retrieval as ret
    from app.services import evidence_scoring as sc
    df = _hist([4000, 5000, 6000, 5500, 4500] * 4)
    r = ret.behavioral_deviation(df, 100000)
    assert r["status"] == "AVAILABLE", r
    assert r["is_deviation"] is True, r
    assert r["mean"] > 0 and r["ratio_to_mean"] > 2.5, r
    assert sc.assign_direction("BEHAVIORAL_DEVIATION", r) == "SUPPORTING"


def test_new_beneficiary():
    from app.services import evidence_retrieval as ret
    from app.services import evidence_scoring as sc
    df = _hist([1000] * 10, cp="ALICE")
    r = ret.beneficiary_history(df, "BRAND_NEW_BOB")
    assert r["status"] == "AVAILABLE", r
    assert r["is_new"] is True and r["match_count"] == 0, r
    assert sc.assign_direction("BENEFICIARY_HISTORY", r) == "SUPPORTING"


def test_known_beneficiary_contradicting():
    from app.services import evidence_retrieval as ret
    from app.services import evidence_scoring as sc
    df = _hist([1000] * 5, cp="ALICE")
    r = ret.beneficiary_history(df, "ALICE")
    assert r["status"] == "AVAILABLE", r
    assert r["is_new"] is False and r["match_count"] == 5, r
    assert sc.assign_direction("BENEFICIARY_HISTORY", r) == "CONTRADICTING"


def test_high_velocity():
    from app.services import evidence_retrieval as ret
    from app.services import evidence_scoring as sc
    df = _hist([100] * 4)
    r = ret.velocity_evidence({"day_count": 8, "is_new_beneficiary": True}, df, daily_avg=0.5)
    assert r["status"] == "AVAILABLE", r
    assert r["is_high_velocity"] is True, r
    assert sc.assign_direction("VELOCITY", r) == "SUPPORTING"


def test_previous_alerts_present():
    from app.services import evidence_retrieval as ret
    inv_id = _e2e_inv("prev")
    from app.services import evidence_store as es
    from app.services.store import get_investigation
    inv = get_investigation(inv_id)
    assert inv, "e2e investigation missing"
    trow = es.get_transaction_by_inv(inv_id)
    acct = trow["payload"]["canonical"]["source_account"]
    r = ret.previous_alerts(acct)
    assert r["status"] == "AVAILABLE", r
    assert r["prior_count"] >= 1, r


def test_device_unavailable():
    from app.services import evidence_retrieval as ret
    d = ret.device_evidence()
    lo = ret.location_evidence()
    assert d["status"] == "UNAVAILABLE" and "reason" in d, d
    assert lo["status"] == "UNAVAILABLE" and "reason" in lo, lo


def test_contradicting_legitimate_set():
    from app.services import evidence_retrieval as ret
    from app.services import evidence_scoring as sc
    df = _hist([5000, 5200, 4800, 5100] * 5, cp="ALICE")
    b = ret.behavioral_deviation(df, 5000)
    assert sc.assign_direction("BEHAVIORAL_DEVIATION", b) == "CONTRADICTING", b
    ben = ret.beneficiary_history(df, "ALICE")
    assert sc.assign_direction("BENEFICIARY_HISTORY", ben) == "CONTRADICTING", ben
    vel = ret.velocity_evidence({"day_count": 1, "is_new_beneficiary": False}, df, daily_avg=1.0)
    assert sc.assign_direction("VELOCITY", vel) == "CONTRADICTING", vel
    prof = ret.profile_consistency({"holder_profile": "normal", "n_debit": 50, "n_credit": 5, "total_debit": 250000, "total_credit": 300000}, 5000, 20000)
    assert prof["status"] == "AVAILABLE" and prof.get("post_hoc_aggregate") is True, prof
    assert sc.assign_direction("PROFILE_CONSISTENCY", prof) == "CONTRADICTING", prof
    rule = ret.rule_evidence(_a2(high=False))
    assert sc.assign_direction("RULE", rule) == "CONTRADICTING", rule
    mod = ret.model_evidence(_a2(high=False))
    assert sc.assign_direction("MODEL", mod) == "CONTRADICTING", mod


def test_corroboration_ge2():
    from app.services import evidence_scoring as sc
    items = [{"finding_key": "amount_deviation", "type": "BEHAVIORAL_DEVIATION"},
             {"finding_key": "amount_deviation", "type": "PROFILE_CONSISTENCY"}]
    assert sc.corroboration_count(items, "amount_deviation") >= 2
    inv_id = _e2e_inv("corrob")
    from app.agents import a3_evidence
    pack = a3_evidence.gather(inv_id)
    d = pack.model_dump() if hasattr(pack, "model_dump") else dict(pack)
    ev = d["evidence"]
    fk = []
    for it in ev:
        dd = it.model_dump() if hasattr(it, "model_dump") else dict(it)
        if dd["type"] in ("BEHAVIORAL_DEVIATION", "PROFILE_CONSISTENCY", "RULE", "MODEL") and dd["direction"] == "SUPPORTING":
            fk.append(dd["type"])
    assert len(fk) >= 2, f"expected >=2 supporting deviation signals, got {fk}"


def test_partial_on_source_failure():
    from app.services import evidence_retrieval as ret
    inv_id = _e2e_inv("partial")
    orig = ret.behavioral_deviation
    def _boom(*a, **k):
        raise RuntimeError("injected source failure")
    ret.behavioral_deviation = _boom
    try:
        from app.agents import a3_evidence
        pack = a3_evidence.gather(inv_id)
        d = pack.model_dump() if hasattr(pack, "model_dump") else dict(pack)
        assert d["status"] == "PARTIAL", d["status"]
        unav = [i for i in d["evidence"] if (i.model_dump() if hasattr(i, "model_dump") else dict(i))["status"] == "UNAVAILABLE"]
        assert len(unav) >= 1, "expected UNAVAILABLE item on failure"
    finally:
        ret.behavioral_deviation = orig


_TESTS = [test_high_deviation, test_new_beneficiary, test_known_beneficiary_contradicting,
          test_high_velocity, test_previous_alerts_present, test_device_unavailable,
          test_contradicting_legitimate_set, test_corroboration_ge2, test_partial_on_source_failure]


if __name__ == "__main__":
    fails = 0
    for fn in _TESTS:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception as e:
            fails += 1
            print(f"FAIL {fn.__name__}: {e}")
            import traceback
            traceback.print_exc()
    print(f"{len(_TESTS)-fails}/{len(_TESTS)} passed")
    sys.exit(1 if fails else 0)
