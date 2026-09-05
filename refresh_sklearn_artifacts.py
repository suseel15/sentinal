"""Re-fit sklearn artifacts with the LOCAL sklearn version (kills unpickle warnings)."""
import logging
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss
import joblib

from src.preprocessing import preprocess
from src.feature_engineering import add_features
from src.graph_builder import build_graph, graph_features
from src.rules_engine import apply_rules
from src.anomaly_detector import AnomalyDetector
from src.feature_fusion import fuse_features
from src.xgboost_model import load_model, predict_proba
from src import config

logging.basicConfig(level=logging.WARNING)
import sklearn
print("local sklearn:", sklearn.__version__)

tr = preprocess(pd.read_csv("artifacts/train.csv").sample(8000, random_state=3))
va = preprocess(pd.read_csv("artifacts/valid.csv").sample(3000, random_state=4))
full = pd.concat([tr, va], ignore_index=True)
full = add_features(full)
G = build_graph(full.iloc[:8000])
full = graph_features(full, G, full.iloc[:8000])
full = apply_rules(full)

af = [c for c in config.ANOMALY_FEATURES if c in full.columns]
ad = AnomalyDetector()
ad.fit(full.iloc[:8000][af], full.iloc[:8000][config.COLS["label"]])
ad.save("artifacts/anomaly_detector.joblib")
print("saved anomaly_detector.joblib")

sc = ad.score(full[af])
full[["anomaly_score", "anomaly_flag"]] = sc[["anomaly_score", "anomaly_flag"]]
X, _ = fuse_features(full, joblib.load("artifacts/graph_emb.joblib"))
y = full[config.COLS["label"]].values
m = load_model("artifacts/xgb.json")
pv = predict_proba(m, X.iloc[8000:])
lr = LogisticRegression()
lr.fit(pv.reshape(-1, 1), y[8000:])
joblib.dump(lr, "artifacts/calibrated_model.joblib")
print("brier:", round(float(brier_score_loss(y[8000:], lr.predict_proba(pv.reshape(-1, 1))[:, 1])), 4))
print("saved calibrated_model.joblib — restart backend to load them")
