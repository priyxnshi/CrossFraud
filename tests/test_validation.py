import pandas as pd

from crossfraud.data.validation import validate_all
from crossfraud.io import RAW_TABLES, write_tables, load_tables


def _roundtrip(data, tmp_path):
    raw, _ = data
    write_tables(raw, tmp_path)
    return load_tables(tmp_path, [*RAW_TABLES, "user_profiles"])


def test_clean_data_passes(data, tmp_path):
    rep = validate_all(_roundtrip(data, tmp_path))
    assert rep.ok and rep.issues == [], rep.summary()


def _corrupt(data, tmp_path, fn):
    r = _roundtrip(data, tmp_path)
    fn(r)
    return validate_all(r)


def test_missing_value(data, tmp_path):
    def f(r): r["messages"].loc[0, "message"] = None
    rep = _corrupt(data, tmp_path, f)
    assert "missing_values" in rep.checks() and not rep.ok


def test_invalid_timestamp(data, tmp_path):
    def f(r): r["transactions"].loc[0, "timestamp"] = "not-a-date"
    assert "invalid_timestamp" in _corrupt(data, tmp_path, f).checks()


def test_timestamp_out_of_range(data, tmp_path):
    def f(r): r["transactions"].loc[0, "timestamp"] = "1999-01-01 00:00:00"
    assert "timestamp_out_of_range" in _corrupt(data, tmp_path, f).checks()


def test_invalid_amounts(data, tmp_path):
    def f(r):
        r["transactions"].loc[0, "amount"] = "-50"
        r["transactions"].loc[1, "amount"] = "abc"
    assert {"non_positive_amount", "non_numeric_amount"} <= _corrupt(data, tmp_path, f).checks()


def test_amount_cap_is_warning(data, tmp_path):
    def f(r): r["transactions"].loc[0, "amount"] = "999999"
    rep = _corrupt(data, tmp_path, f)
    assert "amount_above_cap" in rep.checks() and rep.ok


def test_duplicate_ids_and_records(data, tmp_path):
    def f(r):
        r["transactions"] = pd.concat([r["transactions"], r["transactions"].iloc[[0]]], ignore_index=True)
    c = _corrupt(data, tmp_path, f).checks()
    assert "duplicate_id" in c and "duplicate_record" in c


def test_inconsistent_identifiers(data, tmp_path):
    def f(r):
        r["messages"].loc[0, "sender_id"] = "tg_u9999"
        r["transactions"].loc[0, "sender_id"] = "ghost@ybl"
    c = _corrupt(data, tmp_path, f).checks()
    assert {"participants_inconsistent", "unknown_sender_id"} <= c


def test_unknown_conversation_and_label(data, tmp_path):
    def f(r):
        r["messages"].loc[0, "conversation_id"] = "C99999"
        r["transactions"].loc[0, "fraud_label"] = "2"
    c = _corrupt(data, tmp_path, f).checks()
    assert {"unknown_conversation_id", "invalid_label"} <= c


def test_schema_error(data, tmp_path):
    rep = _corrupt(data, tmp_path, lambda r: r.__setitem__("transactions", r["transactions"].drop(columns=["amount"])))
    assert "schema_missing_columns" in rep.checks() and not rep.ok
