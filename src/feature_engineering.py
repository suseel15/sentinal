"""Feature engineering with strict no-leakage rolling history (past-only)."""
import numpy as np
import pandas as pd
from . import config
C = config.COLS

def add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df[C['timestamp']] = pd.to_datetime(df[C['timestamp']], format="mixed")
    df = df.sort_values([C['account_id'], C['timestamp']], kind='mergesort').reset_index(drop=True)
    df['log_amount'] = np.log1p(df['abs_amount'])
    # Past-only customer stats: expanding mean shifted by 1
    df['customer_avg_amount'] = df.groupby(C['account_id'])['abs_amount'].transform(
        lambda s: s.expanding().mean().shift(1))
    # No-history fallback: population prior (matches training semantics; self-median would force ratio=1)
    df['customer_avg_amount'] = df['customer_avg_amount'].fillna(config.POPULATION_MEDIAN_AMOUNT)
    df['amount_ratio'] = df['abs_amount'] / (df['customer_avg_amount'] + 1)
    df['amount_deviation'] = df['abs_amount'] - df['customer_avg_amount']
    # Time since previous txn per account (days; date granularity)
    df['days_since_prev'] = df.groupby(C['account_id'])[C['timestamp']].diff().dt.days.fillna(999).astype(float)
    df['time_since_prev'] = df['days_since_prev']
    # Velocity: past counts only (day-granularity per-account loop)
    df['txns_last_day'] = 0.0
    df['txns_last_7d'] = 0.0
    df['passthrough_ratio'] = 0.0
    for _, idx in df.groupby(C['account_id']).groups.items():
        sub = df.loc[idx].sort_values(C['timestamp'], kind='mergesort')
        dates = sub[C['timestamp']].values.astype('datetime64[D]').astype(int)
        c1, c7, pt = [], [], []
        sgn = sub[C['amount']].fillna(0).values.astype(float)
        typ = sub[C['type']].values if C['type'] in sub.columns else np.where(sgn < 0, 'DEBIT', 'CREDIT')
        for i, d in enumerate(dates):
            mask1 = (dates[:i] >= d - 1)
            c1.append(int(mask1.sum()))
            c7.append(int((dates[:i] >= d - 7).sum()))
            if typ[i] == 'DEBIT':
                prior_credit = np.abs(sgn[:i][(typ[:i] == 'CREDIT') & mask1]).sum()
                out = abs(float(sgn[i]))
                pt.append(float(min(prior_credit, out) / max(prior_credit, out, 1.0)))
            else:
                pt.append(0.0)
        df.loc[sub.index, 'txns_last_day'] = c1
        df.loc[sub.index, 'txns_last_7d'] = c7
        df.loc[sub.index, 'passthrough_ratio'] = pt
    df['velocity_score'] = df['txns_last_day'] + 0.3 * df['txns_last_7d']
    # New beneficiary: first time account sees counterparty (past-only)
    df['_seen'] = df.groupby([C['account_id'], C['counterparty']]).cumcount()
    df['new_beneficiary'] = (df['_seen'] == 0).astype(int)
    # Signed amount retained for downstream use
    df['signed'] = df[C['amount']]
    # Unusual hour not available (date only); weekend flag
    df['is_weekend'] = (pd.to_datetime(df[C['timestamp']], format="mixed").dt.weekday >= 5).astype(int)
    df['is_debit'] = (df[C['type']] == 'DEBIT').astype(int)
    return df.drop(columns=['_seen', '_date'], errors='ignore')
