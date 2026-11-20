"""Interpretable transaction features. Every history-based feature uses ONLY transactions that
happened strictly before the current one (no look-ahead leakage)."""
from __future__ import annotations

import numpy as np
import pandas as pd

MIN_HISTORY = 3  # prior transactions needed before z-score style features are trusted


def build_transaction_features(txn: pd.DataFrame) -> pd.DataFrame:
    df = txn.sort_values(["timestamp", "transaction_id"], kind="stable").reset_index(drop=True)
    amt = df["amount"].astype(float)
    ts = df["timestamp"]
    df["_t"] = (ts - ts.min()).dt.total_seconds() / 60.0

    out = pd.DataFrame({"transaction_id": df["transaction_id"], "sender_id": df["sender_id"],
                        "receiver_id": df["receiver_id"], "timestamp": ts,
                        "transaction_type": df["transaction_type"], "amount": amt})
    out["log_amount"] = np.log1p(amt)
    out["is_collect_request"] = (df["transaction_type"] == "COLLECT").astype(int)
    out["is_merchant_payment"] = (df["transaction_type"] == "P2M").astype(int)
    out["beneficiary_is_individual"] = (df["beneficiary_type"] == "individual").astype(int)

    # time-based
    out["hour"] = ts.dt.hour
    out["day_of_week"] = ts.dt.dayofweek
    out["is_night"] = ts.dt.hour.isin([0, 1, 2, 3, 4, 5]).astype(int)
    out["is_weekend"] = (ts.dt.dayofweek >= 5).astype(int)

    # Use the earliest positional state for every row sharing the same event time.
    sender_slot = df.groupby(["sender_id", "timestamp"], sort=False).ngroup()
    payee_slot = df.groupby(["receiver_id", "timestamp"], sort=False).ngroup()
    pair_slot = df.groupby(["sender_id", "receiver_id", "timestamp"], sort=False).ngroup()

    def before_slot(values, slots):
        first = df.index.to_series().groupby(slots).transform("min")
        return pd.Series(np.asarray(values)[first], index=df.index)

    # Sender history.
    g = df.groupby("sender_id", sort=False)
    n_prior = g.cumcount()
    s1 = g["amount"].cumsum() - amt
    s2 = (amt ** 2).groupby(df["sender_id"], sort=False).cumsum() - amt ** 2
    n_prior = before_slot(n_prior, sender_slot)
    s1, s2 = before_slot(s1, sender_slot), before_slot(s2, sender_slot)
    mean = s1 / n_prior.replace(0, np.nan)
    var = (s2 / n_prior.replace(0, np.nan) - mean ** 2).clip(lower=0)
    std = np.sqrt(var)
    prior_max = g["amount"].cummax().groupby(df["sender_id"], sort=False).shift(1)
    prior_max = before_slot(prior_max, sender_slot)
    has_hist = n_prior >= MIN_HISTORY
    out["sender_prior_txn_count"] = n_prior
    out["has_history"] = has_hist.astype(int)
    out["sender_prior_mean_amount"] = mean.fillna(0.0)
    out["sender_prior_std_amount"] = std.fillna(0.0)
    out["amount_zscore"] = np.where(has_hist & (std > 0), (amt - mean) / std, 0.0)
    out["amount_ratio_to_prior_mean"] = np.where(has_hist & (mean > 0), amt / mean, 1.0)
    out["amount_over_prior_max"] = np.where(has_hist & (prior_max > 0), amt / prior_max, 1.0)

    # velocity / frequency per sender (windows exclude the current transaction)
    c1, c24, s24, gap = (np.zeros(len(df)) for _ in range(4))
    for _, idx in df.groupby("sender_id", sort=False).indices.items():
        t = df["_t"].to_numpy()[idx]
        a = amt.to_numpy()[idx]
        cs = np.concatenate([[0.0], np.cumsum(a)])
        pos = np.searchsorted(t, t, side="left")
        l1 = np.searchsorted(t, t - 60, side="left")
        l24 = np.searchsorted(t, t - 1440, side="left")
        c1[idx], c24[idx] = pos - l1, pos - l24
        s24[idx] = cs[pos] - cs[l24]
        gap[idx] = np.where(pos == 0, 43200.0, np.minimum(t - t[np.maximum(pos - 1, 0)], 43200.0))
    out["txn_count_1h"], out["txn_count_24h"] = c1.astype(int), c24.astype(int)
    out["amount_sum_24h"] = s24
    out["minutes_since_last_txn"] = gap

    # recipient / beneficiary behaviour
    pair_prior = df.groupby(["sender_id", "receiver_id"], sort=False).cumcount()
    first_pair = (pair_prior == 0).astype(int)
    rg = df.groupby("receiver_id", sort=False)
    out["is_new_beneficiary"] = before_slot(pair_prior, pair_slot).eq(0).astype(int)
    out["pair_prior_txn_count"] = before_slot(pair_prior, pair_slot)
    out["payee_prior_txn_count"] = before_slot(rg.cumcount(), payee_slot)
    distinct_prior = first_pair.groupby(df["receiver_id"], sort=False).cumsum() - first_pair
    out["payee_distinct_senders_prior"] = before_slot(distinct_prior, payee_slot)
    out["new_beneficiary_high_amount"] = ((out["is_new_beneficiary"] == 1) & has_hist & (amt > 3 * mean.fillna(np.inf))).astype(int)

    if "fraud_label" in df:
        out["fraud_label"] = df["fraud_label"]
    return out
