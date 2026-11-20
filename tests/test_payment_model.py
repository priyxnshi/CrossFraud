import numpy as np
import pandas as pd
import pytest

from crossfraud.models.contract import InvalidInputError, validate_result
from crossfraud.models.payment import PAYMENT_FEATURES, PaymentModel, build_payment_frame
from crossfraud.models.training import temporal_split


@pytest.fixture(scope="module")
def frame(data):
    raw, truth = data
    return build_payment_frame(raw).merge(
        truth["transaction_truth"][["transaction_id", "fraud_label"]], on="transaction_id")


@pytest.fixture(scope="module")
def rf(frame):
    return PaymentModel("random_forest", threshold=0.5).fit(frame, frame["fraud_label"].astype(int))


@pytest.fixture(scope="module")
def lr(frame):
    return PaymentModel("logreg", threshold=0.9).fit(frame, frame["fraud_label"].astype(int))


@pytest.fixture(scope="module")
def raw_txn(data):
    return data[0]["transactions"]


@pytest.fixture(scope="module")
def scenario(raw_txn):
    sender = raw_txn.groupby("sender_id").size().idxmax()
    hist = raw_txn[raw_txn["sender_id"] == sender].sort_values("timestamp")
    last = hist["timestamp"].max().normalize() + pd.Timedelta(days=1)
    payee = hist["receiver_id"].value_counts().index[0]
    normal = {"transaction_id": "n", "sender_id": sender, "receiver_id": payee, "amount": float(hist["amount"].median()),
              "timestamp": str(last + pd.Timedelta(hours=14)), "transaction_type": "P2M", "beneficiary_type": "merchant"}
    suspicious = {"transaction_id": "s", "sender_id": sender, "receiver_id": "brandnewpayee9@ybl", "amount": 25000.0,
                  "timestamp": str(last + pd.Timedelta(hours=3, minutes=12)), "transaction_type": "P2P",
                  "beneficiary_type": "individual"}
    return normal, suspicious, raw_txn


def names(r):
    return {s["name"] for s in r["signals"] if s["source"] == "rule"}


def test_imbalance_handled_with_class_weight(rf, lr):
    assert rf.est.class_weight == "balanced_subsample"
    assert lr.est.named_steps["clf"].class_weight == "balanced"


def test_features_exclude_ids_labels_and_ground_truth():
    assert not {"transaction_id", "sender_id", "receiver_id", "timestamp", "fraud_label", "scenario"} & set(PAYMENT_FEATURES)


def test_normal_transaction_is_low_risk(rf, scenario):
    normal, _, hist = scenario
    r = rf.predict(normal, hist)
    assert validate_result(r) == []
    assert r["predicted_class"] == 0 and r["risk_level"] == "low" and r["risk_score"] < 0.1
    assert "new_beneficiary" not in names(r)


def test_suspicious_transaction_is_flagged_with_reasons(rf, scenario):
    _, suspicious, hist = scenario
    r = rf.predict(suspicious, hist)
    assert validate_result(r) == []
    assert r["predicted_class"] == 1 and r["risk_level"] == "high"
    assert {"new_beneficiary", "amount_far_above_usual", "night_time"} <= names(r)
    assert r["evidence"]["receiver_id"] == "brandnewpayee9@ybl"


def test_logreg_baseline_ranks_suspicious_above_normal_and_explains(lr, scenario):
    normal, suspicious, hist = scenario
    a, b = lr.predict(normal, hist), lr.predict(suspicious, hist)
    assert b["risk_score"] > a["risk_score"]
    assert any(s["source"] == "model" and s["weight"] > 0 for s in b["signals"])
    assert validate_result(a) == [] and validate_result(b) == []
    assert not any(s["source"] == "model" for s in a["signals"])  # nothing to explain for a low-risk txn


def test_no_history_is_reported_not_hidden(rf, scenario):
    _, suspicious, _ = scenario
    r = rf.predict(suspicious)
    assert r["meta"]["history_available"] is False and "limited_history" in names(r)


def test_inference_matches_training_frame(rf, frame, raw_txn):
    srt = raw_txn.sort_values(["timestamp", "transaction_id"]).reset_index(drop=True)
    for pos in (4000, 7000, int(srt.index[srt["transaction_id"].isin(frame.loc[frame["fraud_label"].eq(1), "transaction_id"])][60])):
        row = srt.iloc[pos]
        txn = {k: row[k] for k in ["sender_id", "receiver_id", "timestamp", "amount", "transaction_type", "beneficiary_type"]}
        got = rf.predict({**txn, "timestamp": str(row["timestamp"])}, srt.iloc[:pos])["risk_score"]
        exp = rf.predict_proba_frame(frame[frame["transaction_id"] == row["transaction_id"]])[0]
        assert abs(got - round(exp, 4)) < 1e-9, pos


BASE = {"sender_id": "a@ybl", "receiver_id": "b@ybl", "timestamp": "2025-03-01 10:00:00", "amount": 100.0}


@pytest.mark.parametrize("bad", [
    None, "text", [], {}, {k: v for k, v in BASE.items() if k != "amount"},
    {k: v for k, v in BASE.items() if k != "sender_id"}, {k: v for k, v in BASE.items() if k != "timestamp"},
    {**BASE, "amount": 0}, {**BASE, "amount": -5}, {**BASE, "amount": float("nan")}, {**BASE, "amount": float("inf")},
    {**BASE, "amount": "abc"}, {**BASE, "amount": True}, {**BASE, "timestamp": "not-a-date"},
    {**BASE, "receiver_id": "a@ybl"}, {**BASE, "sender_id": ""}, {**BASE, "transaction_type": "WIRE"},
    {**BASE, "beneficiary_type": "robot"},
])
def test_invalid_transaction_input_raises(rf, bad):
    with pytest.raises(InvalidInputError):
        rf.predict(bad)


def test_invalid_history_raises(rf):
    with pytest.raises(InvalidInputError):
        rf.predict(BASE, history=[1, 2, 3])
    with pytest.raises(InvalidInputError):
        rf.predict(BASE, history=pd.DataFrame({"sender_id": ["a@ybl"]}))
    with pytest.raises(InvalidInputError):
        rf.predict(BASE, history=pd.DataFrame({"sender_id": ["a@ybl"], "receiver_id": ["b@ybl"],
                                               "timestamp": ["garbage"], "amount": [10.0]}))


def test_temporal_split_has_no_future_leakage(frame):
    train, test = temporal_split(frame)
    assert train["timestamp"].max() <= test["timestamp"].min()
    assert not set(train["transaction_id"]) & set(test["transaction_id"])
    assert len(train) + len(test) == len(frame)


def test_save_load_roundtrip(rf, scenario, tmp_path):
    normal, _, hist = scenario
    rf.save(tmp_path / "p.joblib")
    assert PaymentModel.load(tmp_path / "p.joblib").predict(normal, hist)["risk_score"] == rf.predict(normal, hist)["risk_score"]
