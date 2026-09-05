"""Fuse tabular + rules + anomaly + graph + embeddings. Aligned by transaction_id."""
import logging
import numpy as np
import pandas as pd
from . import config

log = logging.getLogger(__name__)
C = config.COLS
EMB_DIM = config.GRAPH["embedding_dim"]

BASE = ["abs_amount", "log_amount", "amount_ratio", "amount_deviation", "txns_last_day",
        "txns_last_7d", "days_since_prev", "velocity_score", "new_beneficiary",
        "passthrough_ratio", "is_weekend", "is_debit", "is_credit"]
RULES_COLS = ["large_amount_flag", "high_velocity_flag", "high_velocity_7d_flag", "new_beneficiary_risk",
              "rapid_movement_flag", "structuring_flag", "structuring_window_flag", "high_value_flag",
              "fan_in_flag", "fan_out_flag", "gather_scatter_flag", "crypto_offramp_flag",
              "shell_invoice_flag", "trade_ml_flag", "weekend_burst_flag", "dormant_reactivation_flag",
              "mule_passthrough_flag", "burst_flag", "rule_score", "rule_score_weighted"]
ANOM = ["anomaly_score", "anomaly_flag"]
GRAPH = ["in_degree", "out_degree", "w_in", "w_out", "flow_ratio", "pagerank", "hits_hub",
         "hits_auth", "kcore", "fan_in_7d", "fan_out_7d", "two_hop_reach", "neighbor_risk",
         "burst_score", "gather_scatter_score", "cycle_flag", "community_size"]


def fuse_features(df: pd.DataFrame, graph_emb_dict: dict | None = None):
    try:
        if C["transaction_id"] not in df.columns:
            raise KeyError("transaction_id missing, cannot align")
        if df[C["transaction_id"]].duplicated().any():
            raise ValueError("duplicate transaction_id")
        d = df.copy()
        graph_emb_dict = graph_emb_dict or {}
        for c in BASE + RULES_COLS + ANOM + GRAPH:
            if c not in d.columns:
                d[c] = 0.0
        emb_cols = [f"emb_{i}" for i in range(EMB_DIM)]
        embs = []
        for _, r in d.iterrows():
            v = graph_emb_dict.get(str(r[C["account_id"]]))
            if v is None:
                v = np.zeros(EMB_DIM)
            embs.append(np.asarray(v, dtype=float).ravel()[:EMB_DIM])
        emb_mat = np.vstack(embs) if len(embs) else np.zeros((0, EMB_DIM))
        for i, c in enumerate(emb_cols):
            d[c] = emb_mat[:, i]
        feature_names = BASE + RULES_COLS + ANOM + GRAPH + emb_cols
        X = d[feature_names].fillna(0).astype(float)
        X.index = pd.Index(d[C["transaction_id"]].to_numpy())  # type: ignore
        log.info("fused X=%s feats=%s", X.shape, len(feature_names))
        return X, feature_names
    except Exception:
        log.exception("fuse_features failed")
        raise
