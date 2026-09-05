"""IsolationForest anomaly detector with MinMax scaling. Train on normal-only."""
import logging
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler
from . import config

log = logging.getLogger(__name__)


class AnomalyDetector:
    def __init__(self, params: dict | None = None):
        p = params or config.ISOLATION_FOREST
        self.model = IsolationForest(
            n_estimators=p.get("n_estimators", 300),
            contamination=p.get("contamination", 0.10),
            random_state=config.RANDOM_STATE,
            n_jobs=p.get("n_jobs", -1),
        )
        self.scaler = MinMaxScaler()
        self.features: list[str] | None = None

    def fit(self, X: pd.DataFrame, y: pd.Series | None = None):
        try:
            self.features = list(X.columns)
            X = X.replace([np.inf, -np.inf], np.nan)
            Xa = X
            if y is not None:
                Xa = X[np.asarray(y) == 0]
                if len(Xa) == 0:
                    log.warning("no normal samples, using all data")
                    Xa = X
            Xs = self.scaler.fit_transform(Xa.fillna(0).values)
            self.model.fit(Xs)
            raw = -self.model.score_samples(Xs).reshape(-1, 1)
            self.score_scaler_ = MinMaxScaler().fit(raw)
            log.info("anomaly fit n=%s normal=%s", len(X), len(Xa))
            return self
        except Exception:
            log.exception("AnomalyDetector.fit failed")
            raise

    def score(self, X: pd.DataFrame) -> pd.DataFrame:
        try:
            X = X.replace([np.inf, -np.inf], np.nan)
            if self.features:
                X = X.reindex(columns=self.features, fill_value=0)
            Xs = self.scaler.transform(X.fillna(0).values)
            raw = -self.model.score_samples(Xs)
            norm = self.score_scaler_.transform(raw.reshape(-1, 1)).ravel().clip(0, 1)
            flag = (self.model.predict(Xs) == -1).astype(int)
            return pd.DataFrame({"anomaly_score": norm, "anomaly_flag": flag}, index=X.index)
        except Exception:
            log.exception("AnomalyDetector.score failed")
            raise

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        return self.score(X)

    def save(self, path: str | Path | None = None):
        path = Path(path or config.ARTIFACTS_DIR / "anomaly_detector.joblib")
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"model": self.model, "scaler": self.scaler, "score_scaler": self.score_scaler_, "features": self.features}, path)
        log.info("saved %s", path)
        return path

    @classmethod
    def load(cls, path: str | Path | None = None):
        path = Path(path or config.ARTIFACTS_DIR / "anomaly_detector.joblib")
        d = joblib.load(path)
        obj = cls()
        obj.model, obj.scaler, obj.score_scaler_, obj.features = d["model"], d["scaler"], d["score_scaler"], d["features"]
        return obj
