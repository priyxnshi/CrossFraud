import numpy as np
import pandas as pd

from crossfraud.features.conversation_features import build_conversation_features
from crossfraud.features.text_features import enrich_messages
from crossfraud.features.transaction_features import build_transaction_features


def test_instructed_upi_recovered_in_conversation_features(data):
    raw, truth = data
    cf = build_conversation_features(enrich_messages(raw["messages"]), raw["conversations"])
    j = cf.merge(truth["conversation_truth"].query("instructed_upi != '__NOT_APPLICABLE__'"), on="conversation_id")
    assert len(j) > 0
    assert (j["first_payment_request_upi"] == j["instructed_upi"]).all()
    assert (cf["n_messages"] >= 2).all()


def test_transaction_features_no_lookahead(data):
    raw, _ = data
    tf = build_transaction_features(raw["transactions"])
    assert tf.isna().sum().sum() == 0
    sender = tf.groupby("sender_id").size().idxmax()
    g = tf[tf.sender_id == sender].reset_index(drop=True)
    for i in [5, 10, 20]:
        prior = g.loc[:i - 1, "amount"]
        assert np.isclose(g.loc[i, "sender_prior_mean_amount"], prior.mean())
        assert g.loc[i, "sender_prior_txn_count"] == i
        win = g[(g.timestamp < g.loc[i, "timestamp"]) & (g.timestamp >= g.loc[i, "timestamp"] - pd.Timedelta("24h"))]
        assert g.loc[i, "txn_count_24h"] >= 0 and g.loc[i, "txn_count_24h"] <= len(win) + 1


def test_new_beneficiary_logic(data):
    raw, _ = data
    tf = build_transaction_features(raw["transactions"])
    first = tf.groupby(["sender_id", "receiver_id"]).head(1).index
    assert (tf.loc[first, "is_new_beneficiary"] == 1).all()
    assert tf["is_new_beneficiary"].sum() == len(first)


def test_payee_distinct_senders_matches_manual_count(data):
    """Correctness check only. Whether this feature is PREDICTIVE is evaluated in Phase 3."""
    raw, _ = data
    tf = build_transaction_features(raw["transactions"])
    payee = tf.groupby("receiver_id").size().idxmax()
    g = tf[tf.receiver_id == payee].reset_index(drop=True)
    for i in [0, 3, 10, len(g) - 1]:
        expected = g.loc[:i - 1, "sender_id"].nunique() if i > 0 else 0
        assert g.loc[i, "payee_distinct_senders_prior"] == expected
