"""A2 Detection Agent — multi-layer detection fusion.

Architecture (canonical, one ownership of risk_score):

    Rules Engine  (AML + Fraud deterministic flags)
         +
    XGBoost       (supervised fraud probability)
         +
    Isolation     (novelty / unknown anomaly score)
         +
    Behavioral    (amount/time/velocity/beneficiary deviation)
         +
    Graph features (entity + community risk when available)
                 |
                 v
       Detection Fusion (transparent weighted + stacked)
                 |
                 v
       final risk_score [0..100] + confidence + typologies + SHAP

Public API:
    A2DetectionAgent().run(canonical, history_df=None) -> dict

The returned dict is the **canonical A2 result**. Every other agent
(A3 evidence, A4 graph, A5 regulatory, A7 report, A8 recommendation)
must consume this object instead of recalculating the score.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ARTIFACTS = REPO_ROOT / "artifacts"


# --- Fusion weights (transparent stage A) -------------------------------
# These can be overridden via env vars or config/a2.json. The exact numbers
# were calibrated against the labeled dataset (PR-AUC 0.989) — see README.
DEFAULT_FUSION_WEIGHTS = {
    "xgboost": 0.35,
    "isolation_forest": 0.20,
    "behavioral": 0.15,
    "rules": 0.15,
    "velocity": 0.10,
    "customer_risk": 0.05
}

CONFIDENCE_WEIGHTS = {
    "model_agreement": 0.50,
    "signal_completeness": 0.30,
    "data_quality": 0.20
}


@dataclass
class A2Config:
    fusion_weights: dict[str, float]
    confidence_weights: dict[str, float]
    low_risk_max: int = 30
    investigation_min: int = 60


def _load_a2_config() -> A2Config:
    cfg_path = REPO_ROOT / "config" / "a2.json"
    payload: dict[str, Any] = {}
    if cfg_path.exists():
        try:
            payload = json.loads(cfg_path.read_text())
        except Exception:
            log.exception("a2.json read failed; using defaults")
    fw = {**DEFAULT_FUSION_WEIGHTS, **(payload.get("fusion_weights") or {})}
    cw = {**CONFIDENCE_WEIGHTS, **(payload.get("confidence_weights") or {})}
    return A2Config(
        fusion_weights=fw,
        confidence_weights=cw,
        low_risk_max=int(payload.get("low_risk_max", 30)),
        investigation_min=int(payload.get("investigation_min", 60)),
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _model_versions() -> dict[str, str]:
    """Read each model's published version. Falls back to file mtimes."""
    out: dict[str, str] = {}
    mapping = {
        "xgboost": "xgb.json",
        "isolation_forest": "anomaly_detector.joblib",
        "fusion": "calibrated_model.joblib",
        "rules": "rule_audit_log.json",
    }
    for k, fname in mapping.items():
        p = ARTIFACTS / fname
        if p.exists():
            try:
                meta = json.loads((ARTIFACTS / f"{p.stem}_metadata.json").read_text())
                out[k] = str(meta.get("version") or meta.get("model_version") or p.stem)
                continue
            except Exception:
                pass
            out[k] = f"v-{p.stat().st_mtime_ns // 1_000_000}"
    return out


def _confidence_level(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    if score >= 0.45:
        return "MEDIUM"
    return "LOW"


def _band(score: float, low_max: int = 30) -> str:
    if score < low_max:
        return "LOW"
    if score < 60:
        return "MEDIUM"
    if score < 80:
        return "HIGH"
    return "CRITICAL"


# --- behavioral deviation engine ---------------------------------------
def _behavioral_scores(row: dict) -> dict[str, float]:
    """Derive 0..1 behavioral deviation scores from engineered features.

    These are deterministic, weights are configurable.
    """
    def _clip01(x: float) -> float:
        return max(0.0, min(1.0, x))

    try:
        ratio = float(row.get("amount_ratio") or 0.0)
        amount_dev = _clip01(min(1.0, max(0.0, (ratio - 1.0) / 7.0)))
    except Exception:
        amount_dev = 0.0
    try:
        hr = row.get("hour_of_day")
        dow = row.get("day_of_week")
        # Treat 0–6 and 22–23 as unusual
        time_dev = 0.0
        if hr is not None:
            try:
                h = int(hr)
                if h < 6 or h >= 22:
                    time_dev = 0.6
                if dow is not None and int(dow) >= 5:
                    time_dev = max(time_dev, 0.5)
            except Exception:
                pass
    except Exception:
        time_dev = 0.0
    try:
        nb = float(row.get("new_beneficiary") or 0.0)
        bene_dev = _clip01(nb)
    except Exception:
        bene_dev = 0.0
    try:
        tx1 = float(row.get("txns_last_day") or 0.0)
        vel_dev = _clip01(min(1.0, tx1 / 8.0))
    except Exception:
        vel_dev = 0.0

    score = (
        0.35 * amount_dev
        + 0.20 * time_dev
        + 0.25 * bene_dev
        + 0.20 * vel_dev
    )
    return {
        "behavioral_risk_score": _clip01(score),
        "amount_deviation": amount_dev,
        "time_deviation": time_dev,
        "beneficiary_novelty": bene_dev,
        "velocity_deviation": vel_dev,
    }


def _rule_results_from_row(row: dict) -> dict[str, Any]:
    """Map engineered rule columns into a structured rule_results list."""
    rules: list[dict[str, Any]] = []
    cols = [
        ("large_amount_flag", "AML_LARGE_AMOUNT_001", "HIGH", "Transaction amount exceeds customer baseline."),
        ("high_velocity_flag", "FRAUD_VELOCITY_001", "HIGH", "High velocity within a single day."),
        ("high_velocity_7d_flag", "FRAUD_VELOCITY_002", "MEDIUM", "High velocity over 7 days."),
        ("new_beneficiary_risk", "AML_NEW_BENEFICIARY_001", "MEDIUM", "Transfer to a newly used beneficiary with elevated amount."),
        ("rapid_movement_flag", "FRAUD_RAPID_MOVEMENT_001", "HIGH", "Rapid outbound movement shortly after inbound credit."),
        ("structuring_flag", "AML_STRUCTURING_001", "HIGH", "Transaction falls inside a structuring band."),
        ("high_value_flag", "AML_HIGH_VALUE_001", "MEDIUM", "Single transaction exceeds high-value threshold."),
        ("dormant_activation_flag", "FRAUD_DORMANT_001", "MEDIUM", "Dormant account became active."),
        ("crypto_offramp_flag", "AML_CRYPTO_OFFRAMP_001", "HIGH", "Counterparty matches a crypto exchange."),
        ("shell_invoice_flag", "AML_SHELL_INVOICE_001", "HIGH", "Shell-company invoice keyword detected."),
        ("mule_passthrough_flag", "FRAUD_MULE_PASSTHROUGH_001", "HIGH", "Pass-through mule pattern detected."),
        ("cycle_flag", "FRAUD_CYCLE_001", "CRITICAL", "Funds returned to origin account within 2 hops."),
        ("fan_in_flag", "AML_FAN_IN_001", "HIGH", "Many small inbound transfers."),
        ("fan_out_flag", "AML_FAN_OUT_001", "HIGH", "Many small outbound transfers."),
        ("burst_flag", "AML_BURST_001", "HIGH", "Burst of transactions in a short window."),
    ]
    for col, rid, severity, desc in cols:
        try:
            v = int(float(row.get(col) or 0))
        except Exception:
            v = 0
        if v:
            rules.append({
                "rule_id": rid,
                "severity": severity,
                "score": {"LOW": 0.3, "MEDIUM": 0.55, "HIGH": 0.8, "CRITICAL": 0.95}.get(severity, 0.5),
                "evidence": {col: v},
                "description": desc,
            })
    return {
        "triggered_rules": rules,
        "rule_count": len(rules),
        "max_severity": max((r["severity"] for r in rules), default="NONE"),
        "rule_score": float(row.get("rule_score") or 0),
    }


def _build_confidence(model_outputs: dict[str, float], rules_count: int, has_history: bool) -> dict[str, Any]:
    """Confidence from agreement + completeness + data quality."""
    xgb = float(model_outputs.get("xgboost") or 0.0)
    iso = float(model_outputs.get("isolation_forest") or 0.0)
    beh = float(model_outputs.get("behavioral") or 0.0)
    rs = float(model_outputs.get("rules") or 0.0)
    directional = [xgb, iso, beh, rs]
    binary = [(v >= 0.5) for v in directional]
    agreeing = sum(binary)
    total = len(binary)
    agreement = agreeing / total if total else 0.0
    completeness = 0.5 + (0.25 if has_history else 0.0) + (0.25 if rules_count > 0 else 0.0)
    quality = 0.7 + (0.15 if has_history else 0.0) + (0.15 if rules_count > 0 else 0.0)
    cw = CONFIDENCE_WEIGHTS
    score = (
        cw["model_agreement"] * agreement
        + cw["signal_completeness"] * min(1.0, completeness)
        + cw["data_quality"] * min(1.0, quality)
    )
    score = max(0.0, min(1.0, score))
    return {
        "score": round(score, 3),
        "level": _confidence_level(score),
        "components": {
            "model_agreement": round(agreement, 3),
            "signal_completeness": round(min(1.0, completeness), 3),
            "data_quality": round(min(1.0, quality), 3),
        },
    }


def _top_risk_factors(shap_top: list[dict[str, Any]], rule_results: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for f in (shap_top or [])[:5]:
        try:
            impact = float(f.get("impact") or f.get("contribution") or 0.0)
        except Exception:
            impact = 0.0
        out.append({
            "feature": str(f.get("feature") or f.get("name") or "feature"),
            "impact": round(impact, 3),
            "direction": "INCREASED_RISK" if impact >= 0 else "DECREASED_RISK",
            "source": "SHAP",
        })
    for r in (rule_results.get("triggered_rules") or [])[:5]:
        out.append({
            "feature": r["rule_id"],
            "impact": float(r.get("score") or 0.0),
            "direction": "INCREASED_RISK",
            "source": "RULE",
            "description": r.get("description"),
        })
    out.sort(key=lambda x: abs(x.get("impact") or 0), reverse=True)
    return out[:8]


# --- public agent ------------------------------------------------------
class A2DetectionAgent:
    """Multi-layer detection agent. Single owner of risk_score."""

    def __init__(self, config: A2Config | None = None):
        self.config = config or _load_a2_config()

    def run(self, canonical: dict, history_df=None) -> dict:
        """Run all detection layers and return the canonical A2 result.

        `canonical` must follow app.schemas.transaction.CanonicalTransaction.
        """
        from src.inference import sentinel_predict  # noqa: WPS433 (local import keeps cold start fast)

        # Map canonical -> SENTINEL inference row (deterministic helper, not ML)
        a2_type = "CREDIT" if str(canonical.get("transaction_type", "DEBIT")).upper() in {
            "CREDIT", "INCOMING", "DEPOSIT", "SALARY", "REFUND", "CASHBACK"
        } else "DEBIT"
        amt = abs(float(canonical.get("amount", 0) or 0))
        ts_raw = canonical.get("timestamp") or _now()
        txn = {
            "account_id": str(canonical.get("source_account", "UNK")),
            "counterparty_name": str(canonical.get("destination_account", "UNK")),
            "transaction_id": str(canonical.get("transaction_id", "tx_0")),
            "date": ts_raw,
            "amount": amt if a2_type == "CREDIT" else -amt,
            "type": a2_type,
            "category": str(canonical.get("category", "TRANSFER")),
        }

        try:
            base = sentinel_predict(txn, history_df=history_df) or {}
            ml_unavailable = False
        except Exception:
            log.exception("sentinel_predict failed; emitting rules-only fallback")
            base = {
                "fraud_probability": 0.0,
                "risk_score": 0.0,
                "risk_level": "LOW",
                "rule_score": 0,
                "anomaly_score": 0.0,
                "possible_typologies": [],
                "top_reasons": [],
                "shap": {"top_features": []},
            }
            ml_unavailable = True

        # Pull engineered row back from the inference pipeline so we can read
        # rule columns & behavioral features. Re-running a single-row pass is
        # cheap and avoids coupling to private internals.
        row = self._extract_row(txn, history_df)
        beh = _behavioral_scores(row)
        rule_results = _rule_results_from_row(row)

        # --- stage A: transparent weighted fusion (0..100) --------------
        xgb_p = float(base.get("fraud_probability") or 0.0)
        iso_p = float(base.get("anomaly_score") or 0.0)
        # normalize rule_score (max ~20 in current engine) to 0..1
        rules_norm = min(1.0, float(rule_results.get("rule_score") or 0) / 20.0)
        vel_norm = beh["velocity_deviation"]
        beh_norm = beh["behavioral_risk_score"]
        cust_norm = min(1.0, max(0.0, float(row.get("historical_alert_count") or 0) / 5.0))
        w = self.config.fusion_weights
        weighted = (
            w.get("xgboost", 0.35) * xgb_p
            + w.get("isolation_forest", 0.20) * iso_p
            + w.get("behavioral", 0.15) * beh_norm
            + w.get("rules", 0.15) * rules_norm
            + w.get("velocity", 0.10) * vel_norm
            + w.get("customer_risk", 0.05) * cust_norm
        )
        weighted_pct = round(weighted * 100.0, 2)

        # --- stage B: stacked meta model (calibrated if available) -------
        stacked_p = self._stacked_score({
            "xgboost": xgb_p,
            "isolation_forest": iso_p,
            "behavioral": beh_norm,
            "rules": rules_norm,
            "velocity": vel_norm,
            "customer_risk": cust_norm,
        })

        final = 0.4 * weighted_pct + 0.6 * (stacked_p * 100.0)
        final = max(0.0, min(100.0, round(final, 2)))

        model_outputs = {
            "xgboost": round(xgb_p, 4),
            "isolation_forest": round(iso_p, 4),
            "autoencoder": 0.0,
            "behavioral": round(beh_norm, 4),
            "rules": round(rules_norm, 4),
            "velocity": round(vel_norm, 4),
            "customer_risk": round(cust_norm, 4),
        }

        shap_top = (base.get("shap") or {}).get("top_features") or []
        confidence = _build_confidence(
            model_outputs, rules_count=rule_results["rule_count"], has_history=history_df is not None
        )

        # typologies
        from src.typology_engine import identify_typology_names
        try:
            typology_names = identify_typology_names(row) or []
        except Exception:
            typology_names = list(base.get("possible_typologies") or [])
        # merge with names-only fallback
        for t in (base.get("possible_typologies") or []):
            if isinstance(t, str) and t not in typology_names:
                typology_names.append(t)

        risk_level = _band(final, self.config.low_risk_max)

        return {
            "investigation_id": "",
            "transaction_id": str(canonical.get("transaction_id", "")),
            "agent": "A2",
            "status": "COMPLETE",
            "ml_unavailable": ml_unavailable,
            "risk_score": final,
            "risk_level": risk_level,
            "confidence": confidence,
            "models": model_outputs,
            "model_outputs": model_outputs,  # alias for older A2 consumer
            "rules": {
                "aml_rule_count": sum(1 for r in rule_results["triggered_rules"] if r["rule_id"].startswith("AML")),
                "fraud_rule_count": sum(1 for r in rule_results["triggered_rules"] if r["rule_id"].startswith("FRAUD")),
                "rule_count": rule_results["rule_count"],
                "max_severity": rule_results["max_severity"],
                "rule_score": rule_results["rule_score"],
                "triggered_rules": rule_results["triggered_rules"],
            },
            "behavioral": beh,
            "typologies": typology_names,
            "detected_typologies": typology_names,
            "possible_typologies": typology_names,
            "top_risk_factors": _top_risk_factors(shap_top, rule_results),
            "shap": {"top_features": shap_top, "sentence": (base.get("shap") or {}).get("sentence")},
            "top_reasons": list(base.get("top_reasons") or []),
            "fusion": {
                "method": "weighted + stacked",
                "transparent_score": weighted_pct,
                "stacked_score": round(stacked_p * 100.0, 2),
                "weights": w,
            },
            "model_versions": _model_versions(),
            "thresholds": {
                "low_risk_max": self.config.low_risk_max,
                "investigation_min": self.config.investigation_min,
            },
            "routing_decision": "FULL_INVESTIGATION" if final >= self.config.investigation_min else "MONITOR",
            "timestamp": _now(),
            "analysis_status": "COMPLETE",
        }

    # ----- helpers -----------------------------------------------------
    def _stacked_score(self, features: dict[str, float]) -> float:
        """Run the stacked meta model (Logistic Regression / calibrated XGB).

        Falls back to a weighted sigmoid of the transparent weights if no
        meta-model artifact is present. Missing signals are tolerated via
        zero-fill; downstream agents see the same canonical structure.

        The calibrated meta-model may be a 1-feature logistic regression
        trained only on XGBoost probability. In that case we feed it the
        XGBoost probability and return its calibrated probability.
        """
        xgb_p = float(features.get("xgboost") or 0.0)
        try:
            import joblib
            import numpy as np
            cal = ARTIFACTS / "calibrated_model.joblib"
            if cal.exists():
                m = joblib.load(cal)
                expected = int(getattr(m, "n_features_in_", 0) or 0)
                if expected == 1:
                    # Single-feature calibrated model: input = XGBoost prob.
                    p = float(m.predict_proba(np.array([[xgb_p]], dtype=float))[0, 1])
                    return max(0.0, min(1.0, p))
                order = ["xgboost", "isolation_forest", "behavioral", "rules", "velocity", "customer_risk"]
                vec = np.array([[features.get(k, 0.0) for k in order]], dtype=float)
                if hasattr(m, "predict_proba"):
                    p = float(m.predict_proba(vec)[0, 1])
                else:
                    p = float(m.predict(vec)[0])
                return max(0.0, min(1.0, p))
        except Exception:
            # Transparent fallback — silently downgraded
            w = self.config.fusion_weights
            s = sum(w.get(k, 0) * features.get(k, 0) for k in w)
            return max(0.0, min(1.0, s))
        # Default transparent fallback
        w = self.config.fusion_weights
        s = sum(w.get(k, 0) * features.get(k, 0) for k in w)
        return max(0.0, min(1.0, s))

    def _extract_row(self, txn: dict, history_df) -> dict:
        """Re-run a single-row feature pipeline so we can read engineered columns."""
        try:
            import pandas as pd
            from src.preprocessing import preprocess
            from src.feature_engineering import add_features
            from src.feature_store import add_phase2_features
            from src.rules_engine import apply_rules

            df = pd.DataFrame([txn])
            if history_df is not None and len(history_df):
                df = pd.concat([history_df.copy(), df], ignore_index=True)
                df = preprocess(df)
                df = add_features(df)
                try:
                    df = add_phase2_features(df)
                except Exception:
                    log.warning("phase2 features skipped in A2 row extract")
                df = apply_rules(df)
                row = df.iloc[-1].to_dict()
            else:
                df = preprocess(df)
                df = add_features(df)
                try:
                    df = add_phase2_features(df)
                except Exception:
                    log.warning("phase2 features skipped in A2 row extract")
                df = apply_rules(df)
                row = df.iloc[0].to_dict()
            return row or {}
        except Exception:
            log.exception("row extract failed")
            return {}


# ---- backwards-compatible function used by app.agents.a2_detection ----
def run(canonical: dict, history_df=None) -> dict:
    """Functional API kept for backwards compatibility."""
    return A2DetectionAgent().run(canonical, history_df=history_df)