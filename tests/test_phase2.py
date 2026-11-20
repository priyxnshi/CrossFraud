import numpy as np
import pandas as pd

from crossfraud.features.transaction_features import build_transaction_features
from crossfraud.models.phase2 import choose_threshold
from crossfraud.models.phase2_features import (conversation_prefixes, match_candidates,
                                                score_conversation_as_of, score_payment_attempt)


def test_prefix_and_candidate_cutoffs():
    conversations = pd.DataFrame({"conversation_id": ["C1"]})
    messages = pd.DataFrame([
        {"conversation_id": "C1", "message_id": "M1", "sender_id": "a",
         "timestamp": "2025-01-01T10:00:00+05:30", "message": "Send Rs 850 to shop42 at demobank"},
        {"conversation_id": "C1", "message_id": "M2", "sender_id": "b",
         "timestamp": "2025-01-01T10:01:00+05:30", "message": "One minute"},
        {"conversation_id": "C1", "message_id": "M3", "sender_id": "a",
         "timestamp": "2025-01-01T10:02:00+05:30", "message": "Send your OTP"},
    ])
    cutoffs = pd.DataFrame({"conversation_id": ["C1"], "cutoff_utc": ["2025-01-01T04:31:00Z"]})
    prefix = conversation_prefixes(messages, conversations, cutoffs).iloc[0]
    assert prefix["n_messages"] == 2
    assert prefix["n_credential_request_msgs"] == 0
    attempts = pd.DataFrame([
        {"transaction_id": str(i), "receiver_id": " SHOP42 @ DEMOBANK ",
         "timestamp": f"2025-01-01T10:0{i}:00+05:30", "amount": amount}
        for i, amount in ((0, 850), (3, 540), (4, 850), (5, 850))
    ])
    matches = match_candidates(prefix, attempts, "2025-01-01T10:04:00+05:30")
    assert [match["transaction_id"] for match in matches] == ["4", "3"]
    assert matches[0]["amount_within_tolerance"]
    assert matches[0]["delay_minutes"] == 4


def test_payment_history_excludes_equal_timestamp():
    frame = pd.DataFrame([
        {"transaction_id": f"T{i}", "sender_id": sender, "receiver_id": "payee",
         "timestamp": pd.Timestamp(f"2025-01-01T10:0{minute}:00"), "amount": amount,
         "transaction_type": "P2P", "beneficiary_type": "individual"}
        for i, (sender, minute, amount) in enumerate([("a", 0, 100), ("a", 1, 500),
                                                       ("a", 1, 900), ("b", 1, 300), ("a", 2, 70)])
    ])
    result = build_transaction_features(frame)
    assert result["sender_prior_txn_count"].tolist() == [0, 1, 1, 0, 3]
    assert result["sender_prior_mean_amount"].iloc[1:3].tolist() == [100.0, 100.0]
    assert result["txn_count_1h"].tolist() == [0, 1, 1, 0, 3]
    assert result["payee_prior_txn_count"].tolist() == [0, 1, 1, 1, 4]
    assert result["payee_distinct_senders_prior"].tolist() == [0, 1, 1, 1, 2]


def test_threshold_respects_validation_budget():
    scores = np.array([0.95, 0.90, 0.85, 0.50])
    assert choose_threshold([1, 0, 1, 0], scores) == 0.95
    assert choose_threshold([1, 0, 1, 0], scores, max_fp_per_1000=250) == 0.85


def test_inference_wrappers_pass_only_available_evidence():
    class Reviewer:
        def predict(self, evidence, history=None, entity_id=None):
            return {"evidence": evidence, "history": history, "meta": {}}

    model = Reviewer()
    messages = [{"timestamp": "2025-01-01 10:00", "message": " Hi   there "},
                {"timestamp": "2025-01-01 10:01", "message": "later"}]
    result = score_conversation_as_of(model, messages, "2025-01-01T04:30:00Z")
    assert [message["message"] for message in result["evidence"]] == ["Hi there"]
    attempt = {"sender_id": "a @ demo", "receiver_id": "b@demo", "timestamp": "2025-01-01 10:01"}
    history = pd.DataFrame([attempt, {**attempt, "timestamp": "2025-01-01 10:00"}])
    result = score_payment_attempt(model, attempt, history)
    assert result["evidence"]["sender_id"] == "a@demo"
    assert len(result["history"]) == 1
    assert result["meta"]["review_only"]
