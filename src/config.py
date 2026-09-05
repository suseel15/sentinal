"""SENTINEL central configuration. All thresholds tunable, no hardcoding in logic."""
from pathlib import Path

RANDOM_STATE = 42
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR
SRC_DIR = BASE_DIR / "src"
ARTIFACTS_DIR = BASE_DIR / "artifacts"
ARTIFACTS_DIR.mkdir(exist_ok=True)

# Input files (actual SENTINEL schema)
LABELED_CSV = DATA_DIR / "labeled_transactions.csv"
RAW_CSV = DATA_DIR / "raw_transactions.csv"
PROFILES_CSV = DATA_DIR / "account_profiles.csv"

# Population prior for accounts with no history (median abs amount, labeled set).
# Fixed constant: leakage-free, matches training-batch fillna behavior.
POPULATION_MEDIAN_AMOUNT = 4183.82

# Column mapping layer - adapt here if government schema changes
COLS = {
    "account_id": "account_id",
    "counterparty": "counterparty_name",
    "transaction_id": "transaction_id",
    "timestamp": "date",
    "amount": "amount",
    "type": "type",
    "category": "category",
    "label": "is_suspicious",
    "typology": "typology",
}

# Chronological split (no shuffling to prevent leakage)
SPLIT = {"train_end": "2025-10-31", "valid_end": "2025-11-20"}

# Rules thresholds (tune on validation, starting points only)
RULES = {
    "large_amount_ratio": 5.0,
    "new_beneficiary_ratio": 3.0,
    "high_velocity_day": 10,
    "high_velocity_7d": 25,
    "rapid_days": 1,
    "passthrough_ratio": 0.8,
    "structuring_count": 3,
    "structuring_window_days": 7,
    "structuring_min": 40000,
    "structuring_max": 50000,
    "fan_in_threshold": 5,
    "fan_out_threshold": 5,
    "gather_scatter_ratio": 4.0,
    "roundtrip_days": 7,
    "dormant_days": 30,
    "burst_z": 3.0,
    "high_risk_amount": 1000000,
    "stack_hops": 3,
    "stack_value_tol": 0.15,
    "crypto_keywords": ["CRYPTO", "VAULD", "WAZIRX", "BINANCE", "COIN", "BTC"],
    "shell_keywords": ["INFRA", "TRADERS", "ENTERPRISES", "CONSTRUCTION", "SUPPLIERS"],
    "trade_categories": ["TRADE", "INVOICE", "IMPORT", "EXPORT"],
}

# Isolation Forest
ISOLATION_FOREST = {"n_estimators": 300, "contamination": 0.10, "n_jobs": -1}

# Graph
GRAPH = {"embedding_dim": 64, "hidden_dim": 128, "epochs": 30, "lr": 0.01}

# XGBoost (PR-AUC focus, imbalanced)
XGB_PARAMS = {
    "n_estimators": 1000,
    "max_depth": 6,
    "learning_rate": 0.03,
    "subsample": 0.8,
    "colsample_bytree": 0.8,
    "min_child_weight": 5,
    "gamma": 0.1,
    "objective": "binary:logistic",
    "eval_metric": "aucpr",
    "tree_method": "hist",
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}

# Risk bands (calibrate on validation + investigator capacity)
RISK_BANDS = {"low": 30, "medium": 60, "high": 80}

ANOMALY_FEATURES = [
    "abs_amount", "log_amount", "amount_ratio",
    "txns_last_day", "txns_last_7d", "days_since_prev",
    "new_beneficiary", "velocity_score", "passthrough_ratio",
    "flow_ratio", "pagerank", "in_degree", "out_degree",
    "fan_in_7d", "fan_out_7d", "burst_score",
]
