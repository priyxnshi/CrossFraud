import pandas as pd

from crossfraud.data.synthetic import SynthConfig, generate


def test_deterministic():
    (a, ta), (b, tb) = generate(SynthConfig(seed=7)), generate(SynthConfig(seed=7))
    for k in a:
        pd.testing.assert_frame_equal(a[k], b[k])
    for k in ta:
        pd.testing.assert_frame_equal(ta[k], tb[k])


def test_all_rows_labelled_synthetic(data):
    raw, truth = data
    for t in [*raw.values(), *truth.values()]:
        assert (t["data_source"] == "synthetic").all()


def test_sizes_and_labels(data):
    raw, truth = data
    assert len(raw["users"]) == 300
    assert truth["conversation_truth"]["is_scam"].value_counts().to_dict() == {0: 450, 1: 300}


def test_scenarios_present(data):
    _, truth = data
    s = set(truth["conversation_truth"]["scenario"])
    assert {"task_job", "investment", "kyc_bank", "prize", "smalltalk", "urgent_nonpayment",
            "benign_link", "p2p_split", "benign_rent"} <= s


def test_lifecycle_stages_cover_fraud_chain(data):
    _, truth = data
    scam = truth["conversation_truth"].query("is_scam == 1")["conversation_id"]
    st = truth["message_stages"][truth["message_stages"]["conversation_id"].isin(scam)]
    assert {"contact", "grooming", "payment_request"} <= set(st["stage"])


def test_scam_payments_hit_instructed_upi_after_request(data):
    raw, truth = data
    j = (truth["links"].query("link_type == 'scam_payment'")
         .merge(truth["conversation_truth"], on="conversation_id")
         .merge(raw["transactions"], on="transaction_id").merge(
         truth["transaction_truth"][["transaction_id", "fraud_label"]], on="transaction_id"))
    assert len(j) > 0
    assert (j["receiver_id"] == j["instructed_upi"]).all()
    assert (j["fraud_label"] == 1).all() and (j["delay_minutes"] > 0).all()


def test_hard_negatives_exist(data):
    raw, truth = data
    j = truth["links"].query("link_type == 'benign_p2p'").merge(raw["transactions"], on="transaction_id").merge(
         truth["transaction_truth"][["transaction_id", "fraud_label"]], on="transaction_id")
    assert len(j) > 0 and (j["fraud_label"] == 0).all()


def test_txn_only_fraud_has_no_link(data):
    _, truth = data
    only = truth["transaction_truth"].query("scenario == 'txn_only_fraud'")
    assert len(only) == 40
    assert not set(only["transaction_id"]) & set(truth["links"]["transaction_id"])


def test_obfuscated_upi_written_in_messages(data):
    _, truth = data
    ct = truth["conversation_truth"].query("upi_as_written != '__NOT_APPLICABLE__'")
    assert (ct["upi_as_written"] != ct["instructed_upi"]).any()
