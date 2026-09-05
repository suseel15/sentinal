"""A3 retrieval functions. Each returns dict with status AVAILABLE/UNAVAILABLE."""
import logging

log = logging.getLogger(__name__)


def behavioral_deviation(history_df, amount) -> dict:
    try:
        import pandas as pd
        if history_df is None or len(history_df) == 0:
            return {"status": "UNAVAILABLE", "reason": "no transaction history available"}
        if "amount" not in history_df.columns:
            return {"status": "UNAVAILABLE", "reason": "history missing amount column"}
        vals = pd.to_numeric(history_df["amount"], errors="coerce").abs().dropna()
        vals = vals[vals > 0]
        if len(vals) == 0:
            return {"status": "UNAVAILABLE", "reason": "no usable history amounts"}
        amt = abs(float(amount or 0))
        mean_v = float(vals.mean())
        median_v = float(vals.median())
        max_v = float(vals.max())
        count = int(len(vals))
        r_mean = round(amt / mean_v, 3) if mean_v > 0 else 0.0
        r_med = round(amt / median_v, 3) if median_v > 0 else 0.0
        r_max = round(amt / max_v, 3) if max_v > 0 else 0.0
        is_dev = bool(r_mean >= 2.5 or r_med >= 2.5)
        return {
            "status": "AVAILABLE", "amount": amt, "mean": round(mean_v, 2),
            "median": round(median_v, 2), "max": round(max_v, 2), "count": count,
            "ratio_to_mean": r_mean, "ratio_to_median": r_med, "ratio_to_max": r_max,
            "is_deviation": is_dev, "finding_key": "amount_deviation",
        }
    except Exception as e:
        log.exception("behavioral_deviation failed")
        return {"status": "UNAVAILABLE", "reason": f"behavioral error: {e}"}


def beneficiary_history(history_df, dest) -> dict:
    try:
        import pandas as pd
        d = str(dest or "").strip()
        if not d:
            return {"status": "UNAVAILABLE", "reason": "missing destination account"}
        if history_df is None:
            return {"status": "UNAVAILABLE", "reason": "no history source available"}
        col = None
        for c in ("counterparty_name", "destination_account", "counterparty"):
            if c in history_df.columns:
                col = c
                break
        if col is None:
            return {"status": "UNAVAILABLE", "reason": "history missing counterparty column"}
        series = history_df[col].astype(str).str.strip()
        mask = series == d
        count = int(mask.sum())
        sub = history_df[mask]
        total = 0.0
        if "amount" in sub.columns and len(sub):
            total = round(float(pd.to_numeric(sub["amount"], errors="coerce").abs().sum()), 2)
        first_seen = None
        for dc in ("date", "timestamp", "transaction_date"):
            if dc in history_df.columns and len(sub):
                try:
                    first_seen = str(pd.to_datetime(sub[dc], errors="coerce").min())
                except Exception:
                    first_seen = None
                break
        return {
            "status": "AVAILABLE", "destination": d, "is_new": bool(count == 0),
            "match_count": count, "total_with_beneficiary": total,
            "first_seen": first_seen, "finding_key": "beneficiary",
        }
    except Exception as e:
        log.exception("beneficiary_history failed")
        return {"status": "UNAVAILABLE", "reason": f"beneficiary error: {e}"}


def velocity_evidence(velocity, history_df=None, daily_avg=None) -> dict:
    try:
        if velocity is None or not isinstance(velocity, dict):
            return {"status": "UNAVAILABLE", "reason": "no velocity data available"}
        day_count = int(velocity.get("day_count", 0) or 0)
        avg = daily_avg
        if avg is None and history_df is not None and len(history_df):
            try:
                import pandas as pd
                date_col = next((c for c in ("date", "timestamp") if c in history_df.columns), None)
                if date_col is not None:
                    dd = pd.to_datetime(history_df[date_col], errors="coerce").dropna()
                    ndays = max(int(dd.dt.date.nunique()), 1) if len(dd) else 1
                    avg = round(len(history_df) / ndays, 3)
                else:
                    avg = round(float(len(history_df)) / 30.0, 3)
            except Exception:
                avg = None
        is_high = False
        if day_count >= 5:
            is_high = True
        elif avg is not None and avg > 0 and day_count > 2 * float(avg):
            is_high = True
        return {
            "status": "AVAILABLE", "day_count": day_count,
            "is_new_beneficiary": bool(velocity.get("is_new_beneficiary", False)),
            "daily_avg": avg, "is_high_velocity": bool(is_high),
            "finding_key": "velocity",
        }
    except Exception as e:
        log.exception("velocity_evidence failed")
        return {"status": "UNAVAILABLE", "reason": f"velocity error: {e}"}


def _old_profile_result(profile_row: dict, amount: float, recent_volume=None) -> dict:
    try:
        holder = str(profile_row.get("holder_profile", "unknown"))
        amt = abs(float(amount or 0))
        def _f(k, default=0.0):
            try:
                return float(profile_row.get(k, default) or default)
            except (TypeError, ValueError):
                return float(default)
        n_db, n_cr = _f("n_debit", 0), _f("n_credit", 0)
        n_debits = _f("n_debits", n_db)
        n_credits = _f("n_credits", n_cr)
        t_db = _f("total_debit", _f("total_debit_amount", 0))
        t_cr = _f("total_credit", _f("total_credit_amount", 0))
        n_all = n_debits + n_credits
        avg_txn = round((t_db + t_cr) / n_all, 2) if n_all > 0 else None
        ratio = round(amt / avg_txn, 3) if avg_txn else None
        inconsistent = bool(ratio is not None and ratio >= 3.0)
        hp = holder.lower()
        if any(k in hp for k in ("mule", "shell", "suspicious", "high_risk", "high-risk")):
            inconsistent = True
        return {
            "status": "AVAILABLE", "holder_profile": holder, "avg_txn": avg_txn,
            "amount": amt, "ratio_to_avg": ratio, "recent_volume": recent_volume,
            "is_inconsistent": inconsistent, "post_hoc_aggregate": True,
            "finding_key": "profile",
        }
    except Exception as e:
        log.exception("profile_consistency failed")
        return {"status": "UNAVAILABLE", "reason": f"profile error: {e}"}


def _new_profile_result(prof: dict, amount: float, recent_volume=None) -> dict:
    amt = abs(float(amount or 0))
    risk_cat = str(prof.get("risk_category") or prof.get("account_risk_level") or "unknown")
    kyc = str(prof.get("kyc_status") or "unknown")
    def _i(k):
        try:
            return int(float(prof.get(k, 0) or 0))
        except (TypeError, ValueError):
            return 0
    fraud_ct, alert_ct = _i("previous_fraud_count"), _i("previous_alert_count")
    try:
        pep = bool(int(float(prof.get("pep_flag", 0) or 0)))
    except (TypeError, ValueError):
        pep = bool(prof.get("pep_flag"))
    avg_txn = None
    try:
        if prof.get("average_transaction_amount") not in (None, ""):
            avg_txn = round(float(prof.get("average_transaction_amount") or 0), 2) or None
    except (TypeError, ValueError):
        avg_txn = None
    ratio = round(amt / avg_txn, 3) if avg_txn else None
    signals = []
    if risk_cat.upper() in ("HIGH", "HIGH_RISK", "HIGH-RISK"):
        signals.append("account risk_category HIGH")
    if kyc.upper() not in ("VERIFIED",):
        signals.append(f"kyc_status={kyc}")
    if fraud_ct > 0:
        signals.append(f"previous_fraud_count={fraud_ct}")
    if alert_ct > 0:
        signals.append(f"previous_alert_count={alert_ct}")
    if pep:
        signals.append("pep_flag set")
    if ratio is not None and ratio >= 3.0:
        signals.append(f"amount {ratio}x avg txn")
    return {
        "status": "AVAILABLE", "holder_profile": risk_cat,
        "risk_category": risk_cat, "kyc_status": kyc,
        "previous_fraud_count": fraud_ct, "previous_alert_count": alert_ct,
        "pep_flag": pep, "avg_txn": avg_txn, "amount": amt,
        "ratio_to_avg": ratio, "recent_volume": recent_volume,
        "is_inconsistent": bool(signals), "signals": signals,
        "source": "CUSTOMER_KYC", "profile_source": "accounts.csv+customers.csv",
        "finding_key": "profile",
    }


def profile_consistency(profile_row, amount, recent_volume=None) -> dict:
    try:
        acct_id = None
        if isinstance(profile_row, str):
            acct_id = profile_row.strip() or None
        elif isinstance(profile_row, dict):
            acct_id = str(profile_row.get("account_id") or "").strip() or None
        elif hasattr(profile_row, "to_dict"):
            try:
                profile_row = dict(profile_row.to_dict())
                acct_id = str(profile_row.get("account_id") or "").strip() or None
            except Exception:
                pass
        if acct_id:
            try:
                from app.services import datasets as ds
                prof = ds.load_account_profile(acct_id)
                if prof:
                    return _new_profile_result(prof, amount, recent_volume)
            except Exception:
                log.exception("datasets profile load failed")
        if profile_row is None:
            return {"status": "UNAVAILABLE", "reason": "no account profile available"}
        if hasattr(profile_row, "to_dict"):
            try:
                profile_row = dict(profile_row.to_dict())
            except Exception:
                profile_row = dict(profile_row)
        if not isinstance(profile_row, dict):
            try:
                profile_row = dict(profile_row)
            except Exception:
                return {"status": "UNAVAILABLE", "reason": "no account profile available"}
        if any(k in profile_row for k in ("risk_category", "kyc_status",
                                          "previous_fraud_count", "previous_alert_count")):
            return _new_profile_result(profile_row, amount, recent_volume)
        return _old_profile_result(profile_row, float(amount or 0), recent_volume)
    except Exception as e:
        log.exception("profile_consistency failed")
        return {"status": "UNAVAILABLE", "reason": f"profile error: {e}"}


def device_evidence() -> dict:
    return {
        "status": "UNAVAILABLE",
        "reason": "No device data in labeled_transactions.csv or account_profiles.csv; device source unavailable by design, never fabricated.",
    }


def location_evidence() -> dict:
    return {
        "status": "UNAVAILABLE",
        "reason": "No location data in labeled_transactions.csv or account_profiles.csv; location source unavailable by design, never fabricated.",
    }


def previous_alerts(account_id) -> dict:
    try:
        if not account_id or not str(account_id).strip():
            return {"status": "UNAVAILABLE", "reason": "missing account_id"}
        from app.services import evidence_store as es
        rows = es.find_account_investigations(str(account_id))
        count = len(rows)
        outcomes: list[str] = []
        for r in rows:
            try:
                outcomes.append(f"{r.get('inv_id')}:{r.get('status')}:risk={r.get('risk_score')}")
            except Exception:
                continue
        return {
            "status": "AVAILABLE", "account_id": str(account_id),
            "prior_count": count, "outcomes": outcomes,
            "investigations": rows, "has_prior": bool(count > 0),
            "finding_key": "previous_alerts",
        }
    except Exception as e:
        log.exception("previous_alerts failed")
        return {"status": "UNAVAILABLE", "reason": f"previous_alerts error: {e}"}


def rule_evidence(a2result) -> dict:
    try:
        if not isinstance(a2result, dict) or not a2result:
            return {"status": "UNAVAILABLE", "reason": "no stored A2 result"}
        if "rule_score" not in a2result:
            return {"status": "UNAVAILABLE", "reason": "stored A2 result missing rule_score"}
        return {
            "status": "AVAILABLE",
            "rule_score": a2result.get("rule_score"),
            "top_reasons": list(a2result.get("top_reasons", []) or [])[:6],
            "possible_typologies": list(a2result.get("possible_typologies", []) or []),
            "finding_key": "rule",
        }
    except Exception as e:
        log.exception("rule_evidence failed")
        return {"status": "UNAVAILABLE", "reason": f"rule error: {e}"}


def model_evidence(a2result) -> dict:
    try:
        if not isinstance(a2result, dict) or not a2result:
            return {"status": "UNAVAILABLE", "reason": "no stored A2 result"}
        if "risk_score" not in a2result:
            return {"status": "UNAVAILABLE", "reason": "stored A2 result missing risk_score"}
        shap = a2result.get("shap") or {}
        top_feats: list = []
        try:
            if isinstance(shap, dict):
                top_feats = list(shap.get("top_features", []) or [])[:5]
        except Exception:
            top_feats = []
        return {
            "status": "AVAILABLE",
            "risk_score": a2result.get("risk_score"),
            "risk_level": a2result.get("risk_level"),
            "anomaly_score": a2result.get("anomaly_score"),
            "possible_typologies": list(a2result.get("possible_typologies", []) or []),
            "shap_top": top_feats,
            "transaction_id": a2result.get("transaction_id"),
            "finding_key": "model",
        }
    except Exception as e:
        log.exception("model_evidence failed")
        return {"status": "UNAVAILABLE", "reason": f"model error: {e}"}
