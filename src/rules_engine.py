"""Rules engine v2: ~20 deterministic AML flags, past-only, day granularity."""
import logging
import numpy as np
import pandas as pd
from . import config

log = logging.getLogger(__name__)
C = config.COLS
R = config.RULES


def _col(df: pd.DataFrame, name: str, default: float = 0.0) -> pd.Series:
    if name in df.columns:
        return pd.Series(df[name]).fillna(default).reset_index(drop=True)
    return pd.Series(np.full(len(df), default), index=df.index)


def _kw_hit(s: str, kws) -> bool:
    su = str(s).upper()
    return any(k in su for k in kws)


def apply_rules(df_in: pd.DataFrame) -> pd.DataFrame:
    df = df_in.copy()
    df[C["timestamp"]] = pd.to_datetime(df[C["timestamp"]], format="mixed")
    df = df.sort_values([C["account_id"], C["timestamp"]], kind='mergesort').reset_index(drop=True)
    if C["amount"] in df.columns:
        df["abs_amount"] = pd.Series(df[C["amount"]]).abs().fillna(0)
    else:
        df["abs_amount"] = _col(df, "abs_amount", 0.0)
    ratio = _col(df, "amount_ratio", 0.0)
    tx1 = _col(df, "txns_last_day", 0.0)
    tx7 = _col(df, "txns_last_7d", 0.0)
    new_b = _col(df, "new_beneficiary", 0.0)
    dsp = _col(df, "days_since_prev", 999.0)
    if "is_debit" not in df.columns:
        if C["type"] in df.columns:
            df["is_debit"] = (df[C["type"]] == "DEBIT").astype(int)
        else:
            df["is_debit"] = 0
    fan_in = _col(df, "fan_in_7d", 0.0)
    fan_out = _col(df, "fan_out_7d", 0.0)

    df["large_amount_flag"] = (ratio > R["large_amount_ratio"]).astype(int)
    df["high_velocity_flag"] = (tx1 >= R["high_velocity_day"]).astype(int)
    df["high_velocity_7d_flag"] = (tx7 >= R["high_velocity_7d"]).astype(int)
    df["new_beneficiary_risk"] = ((new_b == 1) & (ratio > R["new_beneficiary_ratio"])).astype(int)
    df["rapid_movement_flag"] = ((np.asarray(dsp) <= R["rapid_days"]) & (np.asarray(df["is_debit"]) == 1) & (np.asarray(ratio) > 2.0)).astype(int)
    df["structuring_flag"] = ((df["abs_amount"] >= R["structuring_min"]) & (df["abs_amount"] <= R["structuring_max"])).astype(int)
    df["high_value_flag"] = (df["abs_amount"] >= R["high_risk_amount"]).astype(int)
    df["fan_in_flag"] = (fan_in >= R["fan_in_threshold"]).astype(int)
    df["fan_out_flag"] = (fan_out >= R["fan_out_threshold"]).astype(int)
    df["gather_scatter_flag"] = (((fan_in + 1) / (fan_out + 1) >= R["gather_scatter_ratio"]) | ((fan_out + 1) / (fan_in + 1) >= R["gather_scatter_ratio"])).astype(int)
    if C["counterparty"] in df.columns:
        cp = df[C["counterparty"]].astype(str)  # type: ignore
    else:
        cp = pd.Series([""] * len(df), index=df.index)
    if C["category"] in df.columns:
        cat = df[C["category"]].astype(str).str.upper()  # type: ignore
    else:
        cat = pd.Series([""] * len(df), index=df.index)
    if "description" in df.columns:
        desc = df["description"].astype(str)  # type: ignore
    else:
        desc = cp
    df["crypto_offramp_flag"] = (cp + " " + desc).apply(lambda s: _kw_hit(str(s), R["crypto_keywords"])).astype(int)
    df["shell_invoice_flag"] = (cp.apply(lambda s: _kw_hit(str(s), R["shell_keywords"])) & (cat.str.contains("INVOICE|TRADE|SERVICE", na=False) | (np.asarray(new_b) == 1))).astype(int)
    df["trade_ml_flag"] = (cat.apply(lambda s: any(k in str(s) for k in R["trade_categories"])) & ((np.asarray(df["abs_amount"]) % 10000 == 0) | (np.asarray(new_b) == 1))).astype(int)
    wk = _col(df, "is_weekend", 0.0)
    df["weekend_burst_flag"] = ((np.asarray(wk) == 1) & (np.asarray(tx1) >= 3)).astype(int)
    # Windowed structuring count: N prior txns in band within window (past-only per account)
    sc, dorm = [], []
    for _, idx in df.groupby(C["account_id"]).groups.items():
        sub = df.loc[idx].sort_values(C["timestamp"], kind='mergesort')
        dates = sub[C["timestamp"]].values.astype("datetime64[D]").astype(int)
        inband = ((sub["abs_amount"] >= R["structuring_min"]) & (sub["abs_amount"] <= R["structuring_max"])).values
        for i, d in enumerate(dates):
            mask = (dates[:i] >= d - R["structuring_window_days"])
            sc.append(int(mask.sum() + int(inband[i]) >= R["structuring_count"] and inband[i]))
            dorm.append(int((d - dates[i - 1] >= R["dormant_days"]) if i > 0 else 0))
    # Map back in sorted order
    df["_sc_tmp"] = 0
    df["_dorm_tmp"] = 0
    pos = 0
    for _, idx in df.groupby(C["account_id"]).groups.items():
        n = len(idx)
        df.loc[df.loc[idx].sort_values(C["timestamp"], kind='mergesort').index, "_sc_tmp"] = sc[pos:pos + n]
        df.loc[df.loc[idx].sort_values(C["timestamp"], kind='mergesort').index, "_dorm_tmp"] = dorm[pos:pos + n]
        pos += n
    df["structuring_window_flag"] = df["_sc_tmp"].astype(int)
    df["dormant_reactivation_flag"] = df["_dorm_tmp"].astype(int)
    _pt = _col(df, "passthrough_ratio", 0.0)
    df["mule_passthrough_flag"] = (((np.asarray(_pt) >= R["passthrough_ratio"]) | (np.asarray(df["rapid_movement_flag"]) == 1)) & (np.asarray(tx1) >= 3)).astype(int)
    _bs = _col(df, "burst_score", 0.0)
    df["burst_flag"] = ((np.asarray(_bs) >= R["burst_z"]) | (np.asarray(tx1) >= R["high_velocity_day"])).astype(int)
    flags = ["large_amount_flag", "high_velocity_flag", "high_velocity_7d_flag", "new_beneficiary_risk",
             "rapid_movement_flag", "structuring_flag", "structuring_window_flag", "high_value_flag",
             "fan_in_flag", "fan_out_flag", "gather_scatter_flag", "crypto_offramp_flag",
             "shell_invoice_flag", "trade_ml_flag", "weekend_burst_flag", "dormant_reactivation_flag",
             "mule_passthrough_flag", "burst_flag"]
    df["rule_score"] = df[flags].sum(axis=1)
    w = {"large_amount_flag": 2, "structuring_window_flag": 3, "fan_in_flag": 2, "fan_out_flag": 2,
         "mule_passthrough_flag": 3, "crypto_offramp_flag": 2, "shell_invoice_flag": 2, "trade_ml_flag": 2}
    df["rule_score_weighted"] = sum(df[f] * w.get(f, 1) for f in flags)
    df["rules_triggered_count"] = df["rule_score"]
    df["rule_score_norm"] = (df["rule_score_weighted"] / 100.0).clip(upper=1.0)
    _sev_rank = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}
    _sev_of = {"large_amount_flag": "HIGH", "high_velocity_flag": "HIGH",
               "high_velocity_7d_flag": "MEDIUM", "new_beneficiary_risk": "CRITICAL",
               "rapid_movement_flag": "HIGH", "structuring_flag": "MEDIUM",
               "structuring_window_flag": "CRITICAL", "high_value_flag": "MEDIUM",
               "fan_in_flag": "HIGH", "fan_out_flag": "HIGH", "gather_scatter_flag": "MEDIUM",
               "crypto_offramp_flag": "HIGH", "shell_invoice_flag": "HIGH",
               "trade_ml_flag": "HIGH", "weekend_burst_flag": "LOW",
               "dormant_reactivation_flag": "MEDIUM", "mule_passthrough_flag": "CRITICAL",
               "burst_flag": "MEDIUM"}
    _names = list(_sev_rank.keys())
    df["max_rule_severity"] = df[flags].apply(
        lambda r: _names[max([_sev_rank[_sev_of[f]] for f in flags if r[f] == 1], default=0)], axis=1)
    reasons = []
    msg = {"large_amount_flag": f"Amount >{R['large_amount_ratio']}x customer average", "high_velocity_flag": "High 1d velocity",
           "high_velocity_7d_flag": "High 7d velocity", "new_beneficiary_risk": "First-time beneficiary + large amount",
           "rapid_movement_flag": "Rapid debit after credit", "structuring_flag": "Amount in structuring band",
           "structuring_window_flag": "Repeated structuring-band txns in window", "high_value_flag": "Very high value",
           "fan_in_flag": "Fan-in: many senders", "fan_out_flag": "Fan-out: many receivers",
           "gather_scatter_flag": "Gather-scatter imbalance", "crypto_offramp_flag": "Crypto off-ramp keyword",
           "shell_invoice_flag": "Shell/invoice keyword + new party", "trade_ml_flag": "Trade/invoice anomaly",
           "weekend_burst_flag": "Weekend burst", "dormant_reactivation_flag": "Reactivation after dormancy",
           "mule_passthrough_flag": "Mule pass-through", "burst_flag": "Burst activity"}
    for _, r in df.iterrows():
        reasons.append([m for f, m in msg.items() if r.get(f, 0) == 1])
    df["rule_reasons"] = reasons
    df = df.drop(columns=["_sc_tmp", "_dorm_tmp"], errors="ignore")
    log.info("rules v2 n=%s flagged=%s", len(df), int((df["rule_score"] > 0).sum()))
    return df


def build_audit_log(df: pd.DataFrame, max_rows=None) -> list:
    """Flatten triggered rules to audit records (masked IDs stay as-is; mask at report)."""
    sev_of = {"large_amount_flag": "HIGH", "high_velocity_flag": "HIGH",
              "high_velocity_7d_flag": "MEDIUM", "new_beneficiary_risk": "CRITICAL",
              "rapid_movement_flag": "HIGH", "structuring_flag": "MEDIUM",
              "structuring_window_flag": "CRITICAL", "high_value_flag": "MEDIUM",
              "fan_in_flag": "HIGH", "fan_out_flag": "HIGH", "gather_scatter_flag": "MEDIUM",
              "crypto_offramp_flag": "HIGH", "shell_invoice_flag": "HIGH",
              "trade_ml_flag": "HIGH", "weekend_burst_flag": "LOW",
              "dormant_reactivation_flag": "MEDIUM", "mule_passthrough_flag": "CRITICAL",
              "burst_flag": "MEDIUM"}
    out = []
    rows = df.iterrows() if max_rows is None else list(df.iterrows())[:max_rows]
    for _, r in rows:
        for f, sev in sev_of.items():
            if f in df.columns and r.get(f, 0) == 1:
                out.append({"transaction_id": str(r.get(C["transaction_id"], "")),
                            "rule_id": f.upper(), "rule_name": f, "severity": sev,
                            "timestamp": str(r.get(C["timestamp"], ""))})
    return out
