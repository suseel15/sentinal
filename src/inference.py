"""Full inference pipeline: features->rules->anomaly->graph->fusion->xgb->risk->typology->shap."""
import json
import logging
from pathlib import Path
import joblib
import pandas as pd
from . import config
from .preprocessing import preprocess
from .feature_engineering import add_features
from .rules_engine import apply_rules
from .anomaly_detector import AnomalyDetector
from .feature_fusion import fuse_features
from .xgboost_model import load_model, predict_proba, get_risk_level
from .typology_engine import identify_typology
from .explainability import ShapExplainer

log = logging.getLogger(__name__)
C = config.COLS


def _load_artifacts(artifacts=None):
    a = Path(artifacts or config.ARTIFACTS_DIR)
    anom = AnomalyDetector.load(a / "anomaly_detector.joblib") if (a / "anomaly_detector.joblib").exists() else None
    xgb = load_model(a / "xgb.json") if (a / "xgb.json").exists() else None
    thr = json.loads((a / "thresholds.json").read_text()) if (a / "thresholds.json").exists() else None
    emb = joblib.load(a / "graph_emb.joblib") if (a / "graph_emb.joblib").exists() else {}
    feats = json.loads((a / "feature_names.json").read_text()) if (a / "feature_names.json").exists() else None
    return anom, xgb, thr, emb, feats


def sentinel_predict(transaction_dict: dict, artifacts=None, history_df=None) -> dict:
    try:
        from .feature_fusion import GRAPH as GRAPH_COLS
        anom, xgb, thr, emb_dict, _ = _load_artifacts(artifacts)
        if xgb is None:
            raise FileNotFoundError("artifacts/xgb.json missing, train first")
        df = pd.DataFrame([transaction_dict])
        for k, v in [(C["transaction_id"], "tx_0"), (C["account_id"], "UNK"),
                     (C["counterparty"], "UNK"), (C["timestamp"], "2025-11-21"),
                     (C["amount"], 0), (C["type"], "DEBIT"), (C["category"], "UNKNOWN")]:
            if k not in df.columns:
                df[k] = v
        # History-aware: prepend account history so rolling features are real
        if history_df is not None and len(history_df):
            h = history_df.copy()
            df = pd.concat([h, df], ignore_index=True)
            single = False
        else:
            single = True
        df = preprocess(df)
        df = add_features(df)
        from .feature_store import add_phase2_features
        try:
            df = add_phase2_features(df)
        except Exception:
            log.warning("phase2 features unavailable, continuing with base", exc_info=True)
        df = apply_rules(df)
        if not single:
            df = df.iloc[[-1]].copy()
        if anom is not None:
            feats_a = [f for f in (anom.features or config.ANOMALY_FEATURES) if f in df.columns]
            if not feats_a:
                df[["anomaly_score", "anomaly_flag"]] = 0.0, 0
            else:
                sc = anom.score(df[feats_a])  # intersected: never KeyError on missing cols
                df[["anomaly_score", "anomaly_flag"]] = sc[["anomaly_score", "anomaly_flag"]]
        else:
            df[["anomaly_score", "anomaly_flag"]] = 0.0, 0
        for g in GRAPH_COLS:
            if g not in df.columns:
                df[g] = 0.0
        X, names = fuse_features(df, emb_dict)
        probs = predict_proba(xgb, X[names])
        prob = float(probs[0])
        level = get_risk_level(prob, thr)
        row = df.iloc[0].to_dict()
        row.update(X.iloc[0].to_dict())
        typos = identify_typology(row)
        try:
            ex = ShapExplainer(xgb, names).explain_one(X.iloc[0])
        except Exception:
            ex = {"top_features": [], "sentence": "Explanation unavailable."}
        reasons = list(df.iloc[0].get("rule_reasons", []) or []) + [ex.get("sentence", "")]
        return {"transaction_id": str(df.iloc[0][C["transaction_id"]]),
                "fraud_probability": prob, "risk_score": round(prob * 100, 2),
                "risk_level": level, "rule_score": int(df.iloc[0].get("rule_score", 0)),
                "anomaly_score": float(df.iloc[0].get("anomaly_score", 0.0)),
                "possible_typologies": typos, "top_reasons": reasons[:6],
                "shap": ex}
    except Exception:
        log.exception("sentinel_predict failed")
        raise
