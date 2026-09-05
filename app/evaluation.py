"""Model evaluation — Rules, Isolation Forest, XGBoost, Fusion.

Uses the production inference path (`src.inference.sentinel_predict`) for
XGBoost so we get the same numbers the orchestrator gets. Runs the
detection ensemble on each row of the chronologically-splittest set and
collects real metrics.

Results are persisted to artifacts/evaluation_metrics.json and exposed
via the FastAPI endpoint /models/evaluation.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parent.parent  # app/evaluation.py -> app -> E:\senfin
ARTIFACTS = REPO / "artifacts"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _chronological_split(df, label_col: str = "is_suspicious"):
    """Chronological 70/15/15 split by `date` column with stratified
    fallback if the chronological test slice contains only one class.
    """
    sort_col = "date" if "date" in df.columns else None
    if sort_col:
        df = df.sort_values(sort_col, kind="mergesort").reset_index(drop=True)
    n = len(df)
    n_train = int(n * 0.70)
    n_valid = int(n * 0.15)
    train = df.iloc[:n_train].copy()
    valid = df.iloc[n_train:n_train + n_valid].copy()
    test = df.iloc[n_train + n_valid:].copy()

    # If the chronological test slice is single-class, fall back to a
    # stratified shuffle split so we still get meaningful metrics.
    if test[label_col].nunique() < 2:
        from sklearn.model_selection import train_test_split
        log.warning("chronological test is single-class — falling back to stratified shuffle")
        rest = df.iloc[n_train:].copy()
        strat_train, strat_test = train_test_split(
            rest, test_size=0.5, stratify=rest[label_col], random_state=42
        )
        # keep chronological valid if possible
        if strat_train[label_col].nunique() >= 2:
            valid = strat_train.copy()
        if strat_test[label_col].nunique() >= 2:
            test = strat_test.copy()
    return train, valid, test


def _metrics(y_true, y_pred, y_score) -> dict[str, Any]:
    import warnings
    from sklearn.metrics import (
        precision_score, recall_score, f1_score, roc_auc_score,
        average_precision_score, confusion_matrix
    )
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = {
            "precision": float(precision_score(y_true, y_pred, zero_division=0)),
            "recall": float(recall_score(y_true, y_pred, zero_division=0)),
            "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        }
        try:
            out["roc_auc"] = float(roc_auc_score(y_true, y_score))
            out["pr_auc"] = float(average_precision_score(y_true, y_score))
        except Exception:
            out["roc_auc"] = None
            out["pr_auc"] = None
    cm = confusion_matrix(y_true, y_pred, labels=[0, 1])
    out["confusion_matrix"] = {
        "tn": int(cm[0, 0]), "fp": int(cm[0, 1]),
        "fn": int(cm[1, 0]), "tp": int(cm[1, 1]),
    }
    return out


def _recall_at_k(y_true, y_score, k: int = 100) -> float:
    if len(y_true) <= k:
        return float(np.sum(np.asarray(y_true) == 1)) / max(1, len(y_true))
    order = np.argsort(-np.asarray(y_score))
    top = np.asarray(y_true)[order[:k]]
    return float(np.sum(top == 1) / max(1, np.sum(np.asarray(y_true) == 1)))


def _to_canonical(row: dict) -> dict:
    """Map labeled_transactions.csv row → sentinel_predict input."""
    is_credit = str(row.get("type", "DEBIT")).upper() in {
        "CREDIT", "INCOMING", "DEPOSIT", "SALARY", "REFUND", "CASHBACK"
    }
    amt = abs(float(row.get("amount") or 0))
    return {
        "account_id": str(row.get("account_id", "UNK")),
        "counterparty_name": str(row.get("counterparty_name", "UNK")),
        "transaction_id": str(row.get("transaction_id", "tx_0")),
        "date": str(row.get("date") or "2025-11-21"),
        "amount": amt if is_credit else -amt,
        "type": "CREDIT" if is_credit else "DEBIT",
        "category": str(row.get("category", "TRANSFER")),
    }


def _build_history(account_id: str, ts: str, df_all, max_rows: int = 30):
    """Build the history_df for a given account before `ts`."""
    import pandas as pd
    sub = df_all[df_all["account_id"].astype(str) == str(account_id)].copy()
    if sub.empty:
        return None
    try:
        sub["_d"] = pd.to_datetime(sub["date"], errors="coerce")
        cutoff = pd.Timestamp(str(ts).replace("Z", "+00:00"))
        if cutoff.tzinfo is not None:
            cutoff = cutoff.tz_convert(None)
        sub = sub[sub["_d"] < cutoff].sort_values("_d").tail(max_rows).drop(columns=["_d"])
        return sub if len(sub) else None
    except Exception:
        return None


def evaluate_all(labeled_csv: Path | None = None,
                out_path: Path | None = None,
                limit: int = 2000) -> dict[str, Any]:
    """Run evaluation on up to `limit` rows of labeled_transactions.csv."""
    import pandas as pd
    from src.inference import sentinel_predict

    csv = labeled_csv or (REPO / "labeled_transactions.csv")
    if not csv.exists():
        return {"error": "labeled_transactions.csv not found"}

    log.info("loading %s (limit=%d)", csv, limit)
    df = pd.read_csv(csv, low_memory=True, nrows=limit)
    if "is_suspicious" not in df.columns:
        return {"error": "is_suspicious column missing"}
    df = df.dropna(subset=["is_suspicious"]).copy()
    df["is_suspicious"] = df["is_suspicious"].astype(int)

    fraud = int(df["is_suspicious"].sum())
    normal = int((df["is_suspicious"] == 0).sum())
    imbalance_ratio = round(normal / max(1, fraud), 2)

    train, valid, test = _chronological_split(df)
    log.info("split: train=%d valid=%d test=%d", len(train), len(valid), len(test))

    results: dict[str, Any] = {
        "generated_at": _now(),
        "dataset": {
            "rows": int(len(df)),
            "fraud": fraud,
            "normal": normal,
            "imbalance_ratio": imbalance_ratio,
            "split": {"train": len(train), "valid": len(valid), "test": len(test)},
        },
        "models": {},
    }

    # Run the production inference on every test row, building per-account
    # history on the fly from the train+valid slices.
    hist_pool = pd.concat([train, valid], ignore_index=True)
    xgb_probs: list[float] = []
    iso_scores: list[float] = []
    rule_scores: list[float] = []
    y_true: list[int] = []

    n = len(test)
    t0 = time.time()
    for i, (_, row) in enumerate(test.iterrows()):
        try:
            canon = _to_canonical(row.to_dict())
            hist = _build_history(canon["account_id"], canon["date"], hist_pool)
            res = sentinel_predict(canon, history_df=hist) or {}
        except Exception as e:
            log.debug("row %d predict failed: %s", i, e)
            res = {}
        xgb_probs.append(float(res.get("fraud_probability") or 0.0))
        iso_scores.append(float(res.get("anomaly_score") or 0.0))
        rule_scores.append(float(res.get("rule_score") or 0.0))
        y_true.append(int(row["is_suspicious"]))

    y_true_arr = np.asarray(y_true, dtype=int)
    xgb_arr = np.asarray(xgb_probs, dtype=float)
    iso_arr = np.asarray(iso_scores, dtype=float)
    rule_arr = np.asarray(rule_scores, dtype=float)
    log.info("scored %d rows in %.1fs", n, time.time() - t0)

    # ----- Model 1: XGBoost -----
    if xgb_arr.any() or len(xgb_arr) > 0:
        preds = (xgb_arr >= 0.5).astype(int)
        m = _metrics(y_true_arr, preds, xgb_arr)
        m["recall_at_100"] = _recall_at_k(y_true_arr, xgb_arr, 100)
        m["recall_at_500"] = _recall_at_k(y_true_arr, xgb_arr, 500)
        results["models"]["xgboost"] = m

    # ----- Model 2: Isolation Forest -----
    if iso_arr.any() or len(iso_arr) > 0:
        preds = (iso_arr >= 0.5).astype(int)
        m = _metrics(y_true_arr, preds, iso_arr)
        m["note"] = "Anomaly score >= 0.5 treated as anomaly."
        results["models"]["isolation_forest"] = m

    # ----- Model 3: Rules Engine -----
    if rule_arr.any() or len(rule_arr) > 0:
        preds = (rule_arr >= 3.0).astype(int)  # rule_score >= 3 = suspicious
        m = _metrics(y_true_arr, preds, rule_arr)
        m["note"] = "rule_score >= 3 treated as suspicious."
        results["models"]["rules_engine"] = m

    # ----- Model 4: Fusion (SENTINEL ensemble) -----
    fusion = 0.5 * xgb_arr + 0.3 * iso_arr + 0.2 * np.clip(rule_arr / 20.0, 0, 1)
    preds = (fusion >= 0.5).astype(int)
    m = _metrics(y_true_arr, preds, fusion)
    m["formula"] = "0.5*xgboost + 0.3*iforest + 0.2*rules"
    m["recall_at_100"] = _recall_at_k(y_true_arr, fusion, 100)
    m["recall_at_500"] = _recall_at_k(y_true_arr, fusion, 500)
    results["models"]["fusion"] = m

    # ----- Threshold analysis for the fusion model -----
    thresholds = [0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80]
    threshold_table = []
    for t in thresholds:
        preds = (fusion >= t).astype(int)
        m = _metrics(y_true_arr, preds, fusion)
        threshold_table.append({
            "threshold": t,
            "precision": m["precision"],
            "recall": m["recall"],
            "f1": m["f1"],
            "false_positives": m["confusion_matrix"]["fp"],
        })
    results["threshold_analysis"] = threshold_table

    out = out_path or (ARTIFACTS / "evaluation_metrics.json")
    out.write_text(json.dumps(results, indent=2))

    # ----- Companion CSVs (results/ style) --------------------------------
    try:
        results_dir = REPO / "results"
        results_dir.mkdir(exist_ok=True)
        # model_comparison.csv
        import csv as _csv
        with (results_dir / "model_comparison.csv").open("w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(["model", "precision", "recall", "f1", "roc_auc", "pr_auc"])
            for name, m in results["models"].items():
                if isinstance(m, dict) and "precision" in m:
                    w.writerow([name, m["precision"], m["recall"], m["f1"],
                                m.get("roc_auc"), m.get("pr_auc")])
        # threshold_analysis.csv
        with (results_dir / "threshold_analysis.csv").open("w", newline="", encoding="utf-8") as f:
            w = _csv.writer(f)
            w.writerow(["threshold", "precision", "recall", "f1", "false_positives"])
            for row in results.get("threshold_analysis", []):
                w.writerow([row["threshold"], row["precision"], row["recall"],
                            row["f1"], row["false_positives"]])
        # evaluation_summary.md
        summary_path = results_dir / "evaluation_summary.md"
        lines = ["# SENTINEL Model Evaluation Summary\n",
                 f"_Generated at {results['generated_at']}_\n",
                 f"- Dataset: {results['dataset']['rows']} rows "
                 f"({results['dataset']['fraud']} fraud / {results['dataset']['normal']} normal, "
                 f"imbalance ratio {results['dataset']['imbalance_ratio']}:1)\n",
                 f"- Split: train={results['dataset']['split']['train']} "
                 f"valid={results['dataset']['split']['valid']} "
                 f"test={results['dataset']['split']['test']}\n",
                 "\n## Model Comparison\n",
                 "| Model | Precision | Recall | F1 | ROC-AUC | PR-AUC |\n",
                 "|-------|-----------|--------|----|---------|--------|\n"]
        for name, m in results["models"].items():
            if isinstance(m, dict) and "precision" in m:
                lines.append(
                    f"| {name} | {m['precision']:.3f} | {m['recall']:.3f} | "
                    f"{m['f1']:.3f} | {m.get('roc_auc') or '-'} | {m.get('pr_auc') or '-'} |\n"
                )
        lines.append("\n## Recommended Fusion Threshold\n")
        if results.get("threshold_analysis"):
            best = max(results["threshold_analysis"], key=lambda r: r["f1"])
            lines.append(
                f"By F1: threshold **{best['threshold']}** "
                f"(P={best['precision']:.2f}, R={best['recall']:.2f}, F1={best['f1']:.2f}, FP={best['false_positives']}).\n"
            )
        summary_path.write_text("".join(lines), encoding="utf-8")
    except Exception as e:
        log.exception("results CSV/MD write failed: %s", e)

    log.info("wrote %s", out)
    return results


def load_metrics() -> dict[str, Any]:
    p = ARTIFACTS / "evaluation_metrics.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    t0 = time.time()
    r = evaluate_all()
    print(json.dumps(r, indent=2))
    print(f"\nelapsed {time.time() - t0:.1f}s")