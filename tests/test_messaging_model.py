import numpy as np
import pandas as pd
import pytest

from crossfraud.models.contract import InvalidInputError, validate_result
from crossfraud.models.demo import NORMAL_CONVERSATION, SCAM_CONVERSATION
from crossfraud.models.messaging import (ALL_STRUCT_COLS, MessagingModel, build_messaging_frame,
                                         is_credential_request)
from crossfraud.models.probes import PROBES
from crossfraud.models.training import benign_split, scenario_holdout_indices


@pytest.fixture(scope="module")
def frame(data):
    raw, truth = data
    f = build_messaging_frame(raw)
    return f.merge(truth["conversation_truth"][["conversation_id", "scenario", "is_scam"]],
                   on="conversation_id").rename(columns={"is_scam": "scam_label"})


@pytest.fixture(scope="module")
def model(frame):
    return MessagingModel("combined").fit(frame, frame["scam_label"].astype(int))


def names(r, source="rule"):
    return {s["name"] for s in r["signals"] if s["source"] == source}


def test_ground_truth_is_never_a_model_input():
    assert not {"scenario", "scam_label", "is_scam", "instructed_upi"} & set(ALL_STRUCT_COLS)


def test_imbalance_handled_with_class_weight(model):
    assert model.pipe.named_steps["clf"].class_weight == "balanced"


def test_normal_message_is_low_risk(model):
    r = model.predict(NORMAL_CONVERSATION, "n1")
    assert validate_result(r) == []
    assert r["predicted_class"] == 0 and r["risk_level"] == "low" and r["risk_score"] < 0.1
    assert names(r) == set()


def test_single_normal_message(model):
    r = model.predict("Hey, are we still meeting for coffee tomorrow?", "n2")
    assert r["predicted_class"] == 0 and validate_result(r) == []


def test_suspicious_conversation_is_flagged_with_indicators(model):
    r = model.predict(SCAM_CONVERSATION, "s1")
    assert validate_result(r) == []
    assert r["predicted_class"] == 1 and r["risk_level"] == "high" and r["risk_score"] > 0.9
    assert {"payment_request", "urgency", "suspicious_link"} <= names(r)
    assert r["evidence"]["upi_ids"] == ["helpline81@ybl"] and r["evidence"]["payment_request_amount"] == 2000.0
    assert r["evidence"]["payment_request_ts"] == "2025-03-01T11:45:00"
    assert any(s["source"] == "model" and s["weight"] > 0 for s in r["signals"])


def test_credential_request_rule():
    assert is_credential_request("Please share the OTP you just received")
    assert is_credential_request("Send me your card number and CVV to verify")
    assert not is_credential_request("Never share your OTP with anyone")
    assert not is_credential_request("see you at 5")


def test_credential_signal_in_output(model):
    r = model.predict("Dear customer, please share the OTP you just received to verify immediately.", "c1")
    assert "credential_request" in names(r) and validate_result(r) == []


def test_rule_signals_fire_on_every_out_of_template_scam(model):
    """Rules do not depend on templates, so they must fire even where the ML score is weak."""
    for p in PROBES:
        if p["label"] == 1:
            assert names(model.predict(p["conversation"], "p")), p["name"]


def test_inference_matches_training_frame(model, frame, data):
    raw, _ = data
    cid = frame.loc[frame["scam_label"].astype(int) == 1, "conversation_id"].iloc[0]
    msgs = raw["messages"][raw["messages"]["conversation_id"] == cid].sort_values(["timestamp", "message_id"])
    conv = [{"sender_id": r.sender_id, "timestamp": str(r.timestamp), "message": r.message} for r in msgs.itertuples()]
    expected = model.predict_proba_frame(frame[frame["conversation_id"] == cid])[0]
    assert abs(model.predict(conv, "x")["risk_score"] - round(expected, 4)) < 1e-9


@pytest.mark.parametrize("bad", [
    [], "", "   ", None, 42, [{"message": ""}], [{"message": 5}], [{"nomessage": "x"}], ["plain string in list"],
    [{"message": "hi", "timestamp": "not a date"}, {"message": "x", "timestamp": "2025-01-01"}],
    [{"message": "hi", "timestamp": "2025-01-01"}, {"message": "x"}],
    [{"message": "hi", "sender_id": "a"}, {"message": "x"}],
])
def test_invalid_conversation_input_raises(model, bad):
    with pytest.raises(InvalidInputError):
        model.predict(bad, "bad")


def test_missing_timestamps_are_never_invented_in_output(model):
    r = model.predict("Send Rs 999 to scam1@ybl now", "t")
    assert r["event_time"] is None and r["evidence"]["payment_request_ts"] is None
    assert "timestamps (1 minute apart)" in r["meta"]["assumed_inputs"]


def test_save_load_roundtrip(model, tmp_path):
    model.save(tmp_path / "m.joblib")
    again = MessagingModel.load(tmp_path / "m.joblib")
    assert again.predict(SCAM_CONVERSATION, "a")["risk_score"] == model.predict(SCAM_CONVERSATION, "a")["risk_score"]


def test_scenario_holdout_has_no_leakage(frame):
    b_tr, b_te = benign_split(frame)
    for held in ["investment", "kyc_bank", "prize", "task_job"]:
        tr, te = scenario_holdout_indices(frame, held, b_tr, b_te)
        assert not set(tr) & set(te)
        assert held not in set(frame.loc[tr, "scenario"])
        assert (frame.loc[te, "scenario"] == held).sum() > 0
    assert not set(b_tr) & set(b_te)
