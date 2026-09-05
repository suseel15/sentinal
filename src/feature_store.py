"""SENTINEL Phase 2: advanced feature store. Past-only, no future leakage."""
import json
import logging
import numpy as np
import pandas as pd
from pathlib import Path
from . import config
from .feature_engineering import add_features

log = logging.getLogger(__name__)
C = config.COLS


def load_feat_config(path=None):
    p = Path(path or config.BASE_DIR / "config" / "features.yaml")
    cfg = {}
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            k, v = line.split(":", 1)
            v = v.strip()
            try:
                cfg[k.strip()] = json.loads(v) if v.startswith("[") else float(v) if "." in v else int(v)
            except Exception:
                cfg[k.strip()] = v
    cfg.setdefault("structuring_band", [40000, 50000])
    cfg.setdefault("structuring_window_days", 7)
    cfg.setdefault("night_hours", [0, 1, 2, 3, 4, 5])
    return cfg


def add_phase2_features(df: pd.DataFrame, cfg=None) -> pd.DataFrame:
    df = df.copy()
    cfg = cfg or load_feat_config()
    lo, hi = cfg["structuring_band"]
    df = df.sort_values([C["account_id"], C["timestamp"]], kind='mergesort').reset_index(drop=True)
    g = df.groupby(C["account_id"])["abs_amount"]
    df["hist_std"] = g.transform(lambda s: s.expanding().std().shift(1)).fillna(0)
    df["hist_median"] = g.transform(lambda s: s.expanding().median().shift(1)).fillna(df["abs_amount"].median())
    df["amount_zscore"] = (df["abs_amount"] - df["customer_avg_amount"]) / (df["hist_std"] + 1e-9)
    df["amount_zscore"] = df["amount_zscore"].clip(-50, 50).fillna(0)
    df["robust_amount_score"] = (df["abs_amount"] - df["hist_median"]) / (df["hist_median"] + 1)
    # Velocity amounts (past-only same-day inclusive)
    df["amt_sent_1d"] = 0.0
    df["amt_sent_7d"] = 0.0
    df["near_threshold_cnt_7d"] = 0
    for _, idx in df.groupby(C["account_id"]).groups.items():
        sub = df.loc[idx].sort_values(C["timestamp"], kind='mergesort')
        dates = sub[C["timestamp"]].values.astype("datetime64[D]").astype(int)
        amts = sub["abs_amount"].values.astype(float)
        a1, a7, nt = [], [], []
        for i, d in enumerate(dates):
            m1 = dates[:i] >= d - 1
            m7 = dates[:i] >= d - 7
            a1.append(float(amts[:i][m1].sum()))
            a7.append(float(amts[:i][m7].sum()))
            nt.append(int((((amts[:i] >= lo) & (amts[:i] <= hi)) & m7).sum()))
        df.loc[sub.index, "amt_sent_1d"] = a1
        df.loc[sub.index, "amt_sent_7d"] = a7
        df.loc[sub.index, "near_threshold_cnt_7d"] = nt
    # Beneficiary history (past-only)
    df["prev_txns_to_beneficiary"] = df.groupby([C["account_id"], C["counterparty"]]).cumcount()
    _uniq, _rcount = [], []
    for _, idx in df.groupby(C["account_id"]).groups.items():
        seen, u = set(), []
        for v in df.loc[df.loc[idx].sort_values(C["timestamp"], kind='mergesort').index, C["counterparty"]]:
            seen.add(v)
            u.append(len(seen))
        _uniq.extend(u)
    df["_uniq_tmp"] = 0
    pos = 0
    for _, idx in df.groupby(C["account_id"]).groups.items():
        sidx = df.loc[idx].sort_values(C["timestamp"], kind='mergesort').index
        df.loc[sidx, "_uniq_tmp"] = _uniq[pos:pos + len(sidx)]
        pos += len(sidx)
    df["beneficiary_diversity"] = (df["_uniq_tmp"] - 1).clip(lower=0) / (df.groupby(C["account_id"]).cumcount() + 1)
    df["beneficiary_diversity"] = df["beneficiary_diversity"].fillna(0)
    df = df.drop(columns=["_uniq_tmp"], errors="ignore")
    # Account behavior
    df["total_prev_txns"] = df.groupby(C["account_id"]).cumcount()
    df["account_age_days"] = df.groupby(C["account_id"])[C["timestamp"]].transform(
        lambda s: (s - s.min()).dt.days).fillna(0)
    # Receiver fan-in (past-only: running distinct-sender count per counterparty)
    df["receiver_prev_txns"] = df.groupby(C["counterparty"]).cumcount()
    _rs = []
    for _, idx in df.groupby(C["counterparty"]).groups.items():
        seen, u = set(), []
        for v in df.loc[df.loc[idx].sort_values(C["timestamp"], kind='mergesort').index, C["account_id"]]:
            seen.add(v)
            u.append(len(seen) - 1)  # past-only: exclude current
        _rs.extend(u)
    df["_rs_tmp"] = 0
    pos = 0
    for _, idx in df.groupby(C["counterparty"]).groups.items():
        sidx = df.loc[idx].sort_values(C["timestamp"], kind='mergesort').index
        df.loc[sidx, "_rs_tmp"] = _rs[pos:pos + len(sidx)]
        pos += len(sidx)
    df["receiver_unique_senders"] = df["_rs_tmp"].clip(lower=0)
    df = df.drop(columns=["_rs_tmp"], errors="ignore")
    # Pattern change: recent 1d vs 30d average count
    df["pattern_change_ratio"] = df["txns_last_day"] / (df["txns_last_7d"] / 7 + 0.1)
    # Temporal: day-granularity -> weekend only + unusual gap
    df["is_night_txn"] = 0  # no hour data (date only); kept for schema compat
    df["unusual_gap_flag"] = (df["days_since_prev"] > 30).astype(int)
    # Geo/currency: conditional (absent in current schema -> neutral)
    df["is_new_country"] = 0
    df["cross_border_flag"] = 0
    df["is_new_currency"] = 0
    if "country" in df.columns:
        df["is_new_country"] = (df.groupby([C["account_id"], "country"]).cumcount() == 0).astype(int)
    return df


FEATURE_DICT = {
    "amount_ratio": ("Behavioral", "current/historical average; large = unusual", "Rule+IF+XGB"),
    "amount_zscore": ("Behavioral", "(amount-mean)/std past-only; spike = anomaly", "IF+XGB"),
    "robust_amount_score": ("Behavioral", "median-based deviation, extreme-value safe", "XGB"),
    "txns_last_day": ("Velocity", "prior-day count; burst = urgency/laundering", "Rule+IF"),
    "txns_last_7d": ("Velocity", "prior-7d count", "Rule+XGB"),
    "amt_sent_1d": ("Velocity", "prior-day outflow sum", "XGB"),
    "new_beneficiary": ("Beneficiary", "first-time receiver", "Rule+XGB"),
    "prev_txns_to_beneficiary": ("Beneficiary", "history depth with receiver", "XGB"),
    "beneficiary_diversity": ("Behavior", "unique receivers/total; scatter = suspicious", "IF+XGB"),
    "passthrough_ratio": ("AML", "outgoing/recent incoming; ~1 = mule pass-through", "Rule+XGB"),
    "near_threshold_cnt_7d": ("Structuring", "count of band amounts in 7d; >=3 = smurfing", "Rule+XGB"),
    "receiver_unique_senders": ("Network", "distinct senders to receiver; fan-in", "Graph+XGB"),
    "pattern_change_ratio": ("Change", "1d vs 30d pace; takeover/compromise", "IF+XGB"),
    "account_age_days": ("Behavior", "tenure; new + large = risk", "XGB"),
}


def build_feature_store(df: pd.DataFrame, out_dir=None, cfg=None):
    out = Path(out_dir or config.ARTIFACTS_DIR)
    out.mkdir(exist_ok=True)
    cfg = cfg or load_feat_config()
    t0 = pd.Timestamp.now()
    df = add_features(df)
    df = add_phase2_features(df, cfg)
    log.info("features built %s in %.1fs", df.shape, (pd.Timestamp.now() - t0).total_seconds())
    # IF candidates: numeric, non-constant, finite
    cands = ["amount_ratio", "amount_zscore", "robust_amount_score", "txns_last_day",
             "txns_last_7d", "amt_sent_1d", "amt_sent_7d", "days_since_prev",
             "beneficiary_diversity", "pattern_change_ratio", "passthrough_ratio",
             "near_threshold_cnt_7d", "receiver_unique_senders"]
    cands = [c for c in cands if c in df.columns and df[c].nunique() > 1
             and np.isfinite(df[c].replace([np.inf, -np.inf], np.nan).dropna()).all()]
    manifest = {
        "transaction_features": ["abs_amount", "log_amount", "is_debit", "is_credit", "is_weekend"],
        "behavior_features": ["amount_ratio", "amount_deviation", "amount_zscore", "robust_amount_score",
                              "beneficiary_diversity", "account_age_days", "total_prev_txns"],
        "velocity_features": ["txns_last_day", "txns_last_7d", "amt_sent_1d", "amt_sent_7d", "velocity_score",
                              "days_since_prev", "pattern_change_ratio"],
        "aml_features": ["passthrough_ratio", "near_threshold_cnt_7d", "new_beneficiary",
                         "prev_txns_to_beneficiary"],
        "temporal_features": ["is_weekend", "is_night_txn", "unusual_gap_flag"],
        "geographical_features": ["is_new_country", "cross_border_flag"],
        "graph_features": ["receiver_prev_txns", "receiver_unique_senders"],
    }
    # Quality report
    lines = ["# Feature Quality Report", ""]
    for col in sorted({c for v in manifest.values() for c in v if c in df.columns}):
        s = df[col]
        lines.append(f"## {col}: miss={s.isna().mean():.3f} min={s.min():.2f} max={s.max():.2f} "
                     f"mean={s.mean():.2f} median={s.median():.2f} uniq={s.nunique()} "
                     f"inf={np.isinf(s).sum()} const={s.nunique() == 1}")
    (out / "feature_quality_report.md").write_text("\n".join(lines))
    fdict = {k: {"description": v[1], "category": v[0], "consumers": v[2]} for k, v in FEATURE_DICT.items()}
    (out / "feature_dictionary.json").write_text(json.dumps(fdict, indent=1))
    (out / "feature_manifest.json").write_text(json.dumps(manifest, indent=1))
    (out / "isolation_forest_features.json").write_text(json.dumps(cands, indent=1))
    # Graph-ready tables
    nodes = pd.DataFrame({"node_id": pd.unique(df[[C["account_id"], C["counterparty"]]].values.ravel())})
    nodes.to_csv(out / "graph_nodes.csv", index=False)
    df[[C["account_id"], C["counterparty"], "abs_amount", C["timestamp"], C["type"]]].rename(
        columns={C["account_id"]: "sender", C["counterparty"]: "receiver",
                 "abs_amount": "amount", C["timestamp"]: "timestamp",
                 C["type"]: "transaction_type"}).to_csv(out / "graph_edges.csv", index=False)
    df.to_csv(out / "transaction_features.csv", index=False)
    print("PHASE 2 COMPLETE: features", df.shape, "| IF cands", len(cands),
          "| NEXT: 03_rules_engine_and_isolation_forest.ipynb")
    return df
