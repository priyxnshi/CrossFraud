import json

import pandas as pd
import pytest

from crossfraud.data.ingestion import ingest
from crossfraud.features.pipeline import run_features
from crossfraud.io import dirs, write_tables


@pytest.fixture
def dataset(data, tmp_path):
    observations, truth = data
    d = dirs(tmp_path)
    write_tables({name: frame for name, frame in observations.items() if name != "user_profiles"}, d["raw"])
    write_tables({"user_profiles": observations["user_profiles"]}, d["profiles"])
    write_tables(truth, d["truth"])
    return d


def test_ingestion_preserves_source_and_normalizes(dataset, tmp_path):
    path = dataset["raw"] / "messages.csv"
    frame = pd.read_csv(path, dtype=str)
    frame.loc[0, "message"] = "  Ｈi\tthere  https://DOCS.EXAMPLE/test#topic "
    frame.to_csv(path, index=False)
    original = path.read_bytes()
    report = ingest(tmp_path)
    assert report.ok, report.summary()
    assert path.read_bytes() == original
    cleaned = pd.read_csv(dataset["cleaned"] / "messages.csv", dtype=str)
    assert cleaned.loc[0, "message"] == frame.loc[0, "message"]
    assert cleaned.loc[0, "message_normalized"] == "Hi there https://DOCS.EXAMPLE/test#topic"
    assert json.loads(cleaned.loc[0, "urls_normalized"]) == ["https://docs.example/test"]
    observed = pd.Timestamp(frame.loc[0, "timestamp"], tz="Asia/Kolkata").tz_convert("UTC")
    assert pd.Timestamp(cleaned.loc[0, "timestamp_utc"]) == observed


def test_broken_link_rejects_batch(dataset, tmp_path):
    path = dataset["truth"] / "links.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "transaction_id"] = "missing"
    frame.to_csv(path, index=False)
    report = ingest(tmp_path)
    assert "broken_link_reference" in report.checks()
    assert not (dataset["cleaned"] / "manifest.json").exists()


def test_bad_csv_is_reported(dataset, tmp_path):
    path = dataset["raw"] / "transactions.csv"
    with path.open("a", encoding="utf-8") as stream:
        stream.write("missing,columns\n")
    assert "malformed_csv_row" in ingest(tmp_path).checks()
    with pytest.raises(SystemExit, match="Refusing"):
        run_features(tmp_path)


def test_features_never_open_truth_or_profiles(dataset, tmp_path):
    for layer in ("truth", "profiles"):
        for path in dataset[layer].glob("*.csv"):
            path.unlink()
    features = run_features(tmp_path)
    for frame in features.values():
        assert not {"is_scam", "scam_label", "fraud_label", "scenario", "state_ut",
                    "campaign_id", "stage", "outcome"} & set(frame)
    path = dataset["raw"] / "messages.csv"
    frame = pd.read_csv(path).assign(scam_label=0)
    frame.to_csv(path, index=False)
    with pytest.raises(SystemExit, match="unexpected_observation_columns"):
        run_features(tmp_path)


def test_population_groups_include_both_conversation_classes(data):
    raw, truth = data
    profiles = raw["user_profiles"]
    participants = raw["users"][["user_id", "telegram_id"]]
    examples = (raw["conversations"].merge(participants, left_on="participant_a", right_on="telegram_id")
                .merge(profiles, on="user_id").merge(truth["conversation_truth"], on="conversation_id"))
    for attribute in profiles.columns.difference(["user_id", "data_source", "source_version"]):
        assert examples.groupby(attribute)["is_scam"].nunique().eq(2).all()


def test_mixed_offsets_and_normalized_payment_identifiers(dataset, tmp_path):
    path = dataset["raw"] / "transactions.csv"
    frame = pd.read_csv(path, dtype=str)
    source = frame.loc[0, "timestamp"]
    frame.loc[0, "timestamp"] = pd.Timestamp(source, tz="Asia/Kolkata").tz_convert("UTC").isoformat()
    frame.loc[0, "sender_id"] = frame.loc[0, "sender_id"].upper().replace("@", " @ ")
    frame.loc[0, "currency"] = " inr "
    frame.to_csv(path, index=False)
    report = ingest(tmp_path)
    assert report.ok, report.summary()
    cleaned = pd.read_csv(dataset["cleaned"] / "transactions.csv", dtype=str)
    assert cleaned.loc[0, "sender_id"] == frame.loc[0, "sender_id"]
    assert cleaned.loc[0, "sender_id_normalized"] == frame.loc[0, "sender_id"].lower().replace(" ", "")
    assert cleaned.loc[0, "currency_normalized"] == "INR"
    assert pd.Timestamp(cleaned.loc[0, "timestamp_utc"]) == pd.Timestamp(frame.loc[0, "timestamp"])


def test_inconsistent_truth_removes_prior_completion_manifest(dataset, tmp_path):
    assert ingest(tmp_path).ok
    path = dataset["truth"] / "transaction_truth.csv"
    frame = pd.read_csv(path)
    frame.loc[0, "label_status"] = "confirmed" if frame.loc[0, "fraud_label"] == 0 else "legitimate"
    frame.to_csv(path, index=False)
    report = ingest(tmp_path)
    assert not report.ok and "inconsistent_truth_label" in report.checks()
    assert not (dataset["cleaned"] / "manifest.json").exists()
    quality = json.loads((dataset["reports"] / "validation_report.json").read_text())
    assert quality["excluded_observation_rows"] > 0
    assert quality["cleaned_observation_row_counts"] == {}
