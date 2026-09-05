"""XGBoost classifier with PR-AUC focus, early stopping, threshold tuning."""
import json
import logging
from pathlib import Path
import numpy as np
from sklearn.metrics import precision_recall_curve
from xgboost import XGBClassifier
from . import config

log = logging.getLogger(__name__)
MODEL_PATH = config.ARTIFACTS_DIR / "xgb.json"
THR_PATH = config.ARTIFACTS_DIR / "thresholds.json"


def train_xgb(X_train, y_train, X_valid, y_valid, params=None):
    try:
        pos = float((y_train == 1).sum())
        neg = float((y_train == 0).sum())
        spw = neg / max(pos, 1)
        p = dict(params or config.XGB_PARAMS)
        p["scale_pos_weight"] = spw
        m = XGBClassifier(**p)
        m.fit(X_train, y_train, eval_set=[(X_valid, y_valid)], verbose=False)
        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        m.save_model(str(MODEL_PATH))
        log.info("xgb saved %s spw=%.2f", MODEL_PATH, spw)
        return m
    except Exception:
        log.exception("train_xgb failed")
        raise


def load_model(path=None):
    m = XGBClassifier()
    m.load_model(str(path or MODEL_PATH))
    return m


def predict_proba(model, X):
    try:
        return np.asarray(model.predict_proba(X)[:, 1])
    except Exception:
        log.exception("predict_proba failed")
        raise


def _thr_at_recall(prec, rec, thr, target):
    c = np.where(rec >= target)[0]
    return float(thr[c[-1]]) if len(c) else 0.3


def _thr_at_prec(prec, rec, thr, target):
    c = np.where(prec[:-1] >= target)[0]
    return float(thr[c[0]]) if len(c) else 0.7


def tune_thresholds(y_valid, probs):
    try:
        prec, rec, thr = precision_recall_curve(y_valid, probs)
        f1 = 2 * prec * rec / (prec + rec + 1e-9)
        med = float(thr[int(np.argmax(f1[:-1]))]) if len(thr) else 0.5
        out = {"LOW": _thr_at_recall(prec, rec, thr, 0.90),
               "MEDIUM": med,
               "HIGH": _thr_at_prec(prec, rec, thr, 0.80),
               "CRITICAL": _thr_at_prec(prec, rec, thr, 0.90)}
        vals = sorted(out.values())
        out = {"LOW": vals[0], "MEDIUM": vals[1], "HIGH": vals[2], "CRITICAL": vals[3]}
        THR_PATH.parent.mkdir(parents=True, exist_ok=True)
        THR_PATH.write_text(json.dumps(out, indent=2))
        return out
    except Exception:
        log.exception("tune_thresholds failed")
        return {"LOW": 0.3, "MEDIUM": 0.5, "HIGH": 0.8, "CRITICAL": 0.9}


def get_risk_level(score: float, thresholds: dict | None = None) -> str:
    t = thresholds or (json.loads(THR_PATH.read_text()) if THR_PATH.exists()
                       else {"LOW": 0.3, "MEDIUM": 0.6, "HIGH": 0.8, "CRITICAL": 0.9})
    if score >= t["CRITICAL"]: return "CRITICAL"
    if score >= t["HIGH"]: return "HIGH"
    if score >= t["MEDIUM"]: return "MEDIUM"
    if score >= t["LOW"]: return "LOW"
    return "LOW"
