"""Train and score the Isolation Forest stage outside Jupyter."""
from __future__ import annotations

import pandas as pd
from sklearn.metrics import confusion_matrix

from src import config
from src.anomaly_detector import AnomalyDetector


def main() -> None:
    train = pd.read_csv(config.ARTIFACTS_DIR / "train_fe.csv")
    valid = pd.read_csv(config.ARTIFACTS_DIR / "valid_fe.csv")
    test = pd.read_csv(config.ARTIFACTS_DIR / "test_fe.csv")

    feats = [c for c in config.ANOMALY_FEATURES if c in train.columns]
    if not feats:
        raise SystemExit("No anomaly features found. Run feature engineering first.")
    if "is_suspicious" not in train.columns:
        raise SystemExit("Missing is_suspicious column in artifacts/train_fe.csv.")

    print("anomaly feats:", feats)
    det = AnomalyDetector().fit(train[feats], train["is_suspicious"])
    print("fit on normal-only n=", int((train["is_suspicious"] == 0).sum()))

    for name, df in [("train", train), ("valid", valid), ("test", test)]:
        sc = det.score(df.reindex(columns=feats, fill_value=0))
        df[["anomaly_score", "anomaly_flag"]] = sc[["anomaly_score", "anomaly_flag"]]
        print(name, df.groupby("is_suspicious")["anomaly_score"].mean().to_dict())
        print(name, "confusion\n", confusion_matrix(df["is_suspicious"], df["anomaly_flag"]))

    det.save(config.ARTIFACTS_DIR / "anomaly_detector.joblib")
    train.to_csv(config.ARTIFACTS_DIR / "train_fe.csv", index=False)
    valid.to_csv(config.ARTIFACTS_DIR / "valid_fe.csv", index=False)
    test.to_csv(config.ARTIFACTS_DIR / "test_fe.csv", index=False)
    print("saved anomaly_detector.joblib + *_fe.csv -> used by 05_graph_construction.ipynb")


if __name__ == "__main__":
    main()
