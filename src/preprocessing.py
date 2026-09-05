"""Preprocessing: clean, parse dates, dedupe, chronological split. No leakage."""
import logging
import pandas as pd
from . import config

log = logging.getLogger(__name__)
C = config.COLS

def preprocess(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[C['timestamp']] = pd.to_datetime(df[C['timestamp']], format="mixed")
    df = df.drop_duplicates(subset=[C['transaction_id']])
    df = df.sort_values(C['timestamp']).reset_index(drop=True)
    df['abs_amount'] = df[C['amount']].abs()
    df['is_credit'] = (df[C['type']] == 'CREDIT').astype(int)
    df['category'] = df[C['category']].fillna('UNKNOWN')
    df[C['counterparty']] = df[C['counterparty']].fillna('UNKNOWN')
    return df

def chronological_split(df: pd.DataFrame):
    te, ve = config.SPLIT['train_end'], config.SPLIT['valid_end']
    train = df[df[C['timestamp']] <= te].copy()
    valid = df[(df[C['timestamp']] > te) & (df[C['timestamp']] <= ve)].copy()
    test = df[df[C['timestamp']] > ve].copy()
    log.info("split train=%s valid=%s test=%s", len(train), len(valid), len(test))
    if not len(train) or not len(valid) or not len(test):
        raise ValueError("empty chronological split, check SPLIT dates")
    return train, valid, test
