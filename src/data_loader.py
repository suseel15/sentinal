"""Load government CSVs with schema mapping and validation."""
import logging
import pandas as pd
from . import config

log = logging.getLogger(__name__)

def load_labeled():
    try:
        df = pd.read_csv(config.LABELED_CSV)
        log.info("labeled shape=%s suspicious=%.3f", df.shape, df[config.COLS['label']].mean())
        return df
    except Exception as e:
        log.exception("failed loading labeled CSV")
        raise

def load_raw():
    return pd.read_csv(config.RAW_CSV)

def load_profiles():
    # WARNING: account_profiles.csv contains post-hoc aggregates (n_suspicious_txns,
    # final_balance, holder_profile). Do NOT join as training features - leakage.
    # Use only for EDA / holder_profile distribution analysis.
    return pd.read_csv(config.PROFILES_CSV)

def schema_report(df: pd.DataFrame) -> dict:
    return {"shape": df.shape, "columns": list(df.columns),
            "dtypes": {k: str(v) for k, v in df.dtypes.items()},
            "nulls": df.isna().sum().to_dict()}
