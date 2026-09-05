"""Print confusion matrices for all SENTINEL model evaluators."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
METRICS_PATH = ROOT / "artifacts" / "evaluation_metrics.json"


def _load_metrics(refresh: bool, limit: int) -> dict:
    if refresh or not METRICS_PATH.exists():
        from app.evaluation import evaluate_all

        return evaluate_all(limit=limit)
    return json.loads(METRICS_PATH.read_text(encoding="utf-8"))


def _print_matrix(name: str, metrics: dict) -> None:
    cm = metrics.get("confusion_matrix") or {}
    tn = cm.get("tn", 0)
    fp = cm.get("fp", 0)
    fn = cm.get("fn", 0)
    tp = cm.get("tp", 0)

    print(f"\n{name}")
    print("-" * len(name))
    print("                 Pred 0    Pred 1")
    print(f"Actual 0 (normal) {tn:7} {fp:9}")
    print(f"Actual 1 (fraud)  {fn:7} {tp:9}")
    print(
        "precision={:.3f} recall={:.3f} f1={:.3f}".format(
            float(metrics.get("precision") or 0),
            float(metrics.get("recall") or 0),
            float(metrics.get("f1") or 0),
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="rerun evaluation before printing")
    parser.add_argument("--limit", type=int, default=2000, help="rows to evaluate when using --refresh")
    args = parser.parse_args()

    data = _load_metrics(refresh=args.refresh, limit=args.limit)
    if data.get("error"):
        raise SystemExit(data["error"])

    dataset = data.get("dataset") or {}
    split = dataset.get("split") or {}
    print(f"Metrics file: {METRICS_PATH}")
    print(f"Generated at: {data.get('generated_at', 'unknown')}")
    print(
        "Dataset: {rows} rows, {fraud} fraud, {normal} normal; test={test}".format(
            rows=dataset.get("rows", "?"),
            fraud=dataset.get("fraud", "?"),
            normal=dataset.get("normal", "?"),
            test=split.get("test", "?"),
        )
    )

    for name, metrics in (data.get("models") or {}).items():
        if isinstance(metrics, dict) and "confusion_matrix" in metrics:
            _print_matrix(name, metrics)


if __name__ == "__main__":
    main()
