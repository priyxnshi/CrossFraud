"""Phase 1 batch ingestion. Publish cleaned observations only after validation."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import pandas as pd

from crossfraud.data.validation import ValidationReport, _ts, validate_all
from crossfraud.features.text_features import URL_RE
from crossfraud.io import TRUTH_TABLES, dirs, write_tables
from crossfraud.schemas import TABLES

VERSION = "phase1-clean-v2"
EVENT_TIMES = {"messages": ("timestamp",), "transactions": ("timestamp",),
               "conversations": ("start_ts", "end_ts")}
TRUTH_FIELDS = {
    "scammers": "scammer_id telegram_id upi_id display_name",
    "conversation_truth": ("conversation_id scenario is_scam instructed_upi upi_as_written "
                           "instructed_amount paid campaign_id attempt_outcome label_status"),
    "message_stages": "message_id conversation_id stage",
    "transaction_truth": "transaction_id scenario outcome fraud_label label_status",
    "links": "conversation_id transaction_id link_type delay_minutes link_evidence",
}
TRUTH_METADATA = {"data_source", "source_version", "label_source", "label_confidence"}
LABEL_STATUS = {"confirmed", "suspected", "legitimate", "unknown"}


def read_inputs(paths, report):
    tables = {}
    for name, path in paths.items():
        try:
            with path.open(encoding="utf-8-sig", newline="") as source:
                rows = csv.reader(source, strict=True)
                header = next(rows, [])
                if not header or len(set(header)) != len(header) or "" in header:
                    report.add("error", name, "invalid_csv_header", 1)
                    continue
                valid, bad_lines = [], []
                for row in rows:
                    if len(row) != len(header):
                        bad_lines.append(rows.line_num)
                    else:
                        valid.append(row)
                report.row_counts[name] = len(valid) + len(bad_lines)
                report.add("error", name, "malformed_csv_row", len(bad_lines),
                           f"first line numbers: {bad_lines[:10]}")
                tables[name] = pd.DataFrame(valid, columns=header).replace("", pd.NA)
        except (OSError, UnicodeError, csv.Error) as exc:
            report.add("error", name, "unreadable_csv", 1, type(exc).__name__)
    return tables


def normalized_text(value):
    return " ".join(unicodedata.normalize("NFKC", value).split())


def normalized_id(value):
    return re.sub(r"\s*@\s*", "@", normalized_text(value).lower())


def normalized_urls(text):
    urls = []
    for token in URL_RE.findall(text):
        url = token.rstrip(".,);!?")
        try:
            parsed = urlsplit(url if "://" in url else "https://" + url)
            if parsed.hostname and not parsed.username and not parsed.password:
                urls.append(urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(),
                                        parsed.path, parsed.query, "")))
        except ValueError:
            continue
    return json.dumps(urls, ensure_ascii=False)


def validate_truth(raw, truth, report):
    for name, fields in TRUTH_FIELDS.items():
        missing = (set(fields.split()) | TRUTH_METADATA) - set(truth[name])
        report.add("error", name, "truth_missing_columns", len(missing), str(sorted(missing)))
    if not report.ok:
        return
    for name, frame in truth.items():
        report.add("error", name, "unsupported_source", (~frame["data_source"].isin(["synthetic"])).sum())
        report.add("error", name, "missing_source_version", frame["source_version"].isna().sum())
        confidence = pd.to_numeric(frame["label_confidence"], errors="coerce")
        report.add("error", name, "invalid_label_confidence", (~confidence.between(0, 1)).sum())
        report.add("error", name, "missing_label_source", frame["label_source"].isna().sum())
    for table, key, binary, observation in (
        ("conversation_truth", "conversation_id", "is_scam", "conversations"),
        ("transaction_truth", "transaction_id", "fraud_label", "transactions"),
        ("message_stages", "message_id", None, "messages"),
    ):
        frame = truth[table]
        report.add("error", table, "duplicate_truth_key", frame[key].duplicated().sum())
        report.add("error", table, "truth_reference_mismatch", len(set(frame[key]) ^ set(raw[observation][key])))
        if binary:
            label = pd.to_numeric(frame[binary], errors="coerce")
            status = frame["label_status"]
            invalid = (~status.isin(LABEL_STATUS) | (status.eq("confirmed") & label.ne(1)) |
                       (status.eq("legitimate") & label.ne(0)) |
                       (status.isin(["suspected", "unknown"]) & ~frame[binary].isin(["__UNKNOWN__"])))
            report.add("error", table, "inconsistent_truth_label", invalid.sum())
    if not report.ok:
        return

    messages = raw["messages"]
    users = raw["users"]
    actors = truth["scammers"]
    conversations = raw["conversations"]
    report.add("error", "scammers", "duplicate_actor_account", actors["upi_id"].duplicated().sum())
    report.add("error", "conversations", "unknown_focal_participant",
               (~conversations["participant_a"].isin(users["telegram_id"])).sum())
    known = set(users["telegram_id"]) | set(actors["telegram_id"])
    report.add("error", "conversations", "unknown_counterpart",
               (~conversations["participant_b"].isin(known)).sum())
    allowed_stages = {"contact", "grooming", "urgency", "payment_request", "victim_response", "chat"}
    report.add("error", "message_stages", "invalid_stage",
               (~truth["message_stages"]["stage"].isin(allowed_stages)).sum())
    stages = truth["message_stages"].merge(messages, on="message_id", suffixes=("", "_observed"))
    report.add("error", "message_stages", "inconsistent_stage_conversation",
               stages["conversation_id"].ne(stages["conversation_id_observed"]).sum())
    attempts = truth["transaction_truth"].merge(raw["transactions"], on="transaction_id")
    valid_status = ((attempts["outcome"].eq("failed") & attempts["status_at_event"].eq("failed")) |
                    (attempts["outcome"].isin(["settled", "reversed"]) &
                     attempts["status_at_event"].eq("accepted")))
    report.add("error", "transaction_truth", "inconsistent_outcome", (~valid_status).sum())

    links = truth["links"]
    report.add("error", "links", "duplicate_link", links.duplicated(["conversation_id", "transaction_id"]).sum())
    missing = (~links["conversation_id"].isin(raw["conversations"]["conversation_id"]) |
               ~links["transaction_id"].isin(raw["transactions"]["transaction_id"]))
    report.add("error", "links", "broken_link_reference", missing.sum())
    requests = stages[stages["stage"].eq("payment_request")].assign(
        request_ts=lambda frame: _ts(frame["timestamp"])).groupby("conversation_id")["request_ts"].max()
    joined = links.loc[~missing].merge(attempts[["transaction_id", "timestamp", "fraud_label", "outcome", "receiver_id"]],
                                      on="transaction_id").merge(
        truth["conversation_truth"][["conversation_id", "is_scam", "instructed_upi", "attempt_outcome", "paid"]],
        on="conversation_id")
    delay = (_ts(joined["timestamp"]) - joined["conversation_id"].map(requests)).dt.total_seconds() / 60
    report.add("error", "links", "inconsistent_link_delay",
               (~delay.gt(0) | delay.ne(pd.to_numeric(joined["delay_minutes"], errors="coerce"))).sum())
    expected_type = joined["is_scam"].map({"1": "scam_payment", "0": "benign_p2p"})
    paid = pd.to_numeric(joined["paid"], errors="coerce")
    invalid = (joined["link_type"].ne(expected_type) | joined["is_scam"].ne(joined["fraud_label"]) |
               joined["instructed_upi"].ne(joined["receiver_id"].map(normalized_id)) |
               joined["attempt_outcome"].ne(joined["outcome"]) |
               paid.ne(joined["outcome"].isin(["settled", "reversed"]).astype(int)))
    report.add("error", "links", "inconsistent_link_evidence", invalid.sum())


def load_observations(data_dir):
    """Validate and normalize observations without opening truth or profile inputs."""
    d = dirs(data_dir)
    report = ValidationReport()
    paths = {name: d["raw"] / f"{name}.csv" for name in TABLES if name != "user_profiles"}
    raw = read_inputs(paths, report)
    for name, frame in raw.items():
        forbidden = set(frame) - (set(TABLES[name]) | {"source_version"})
        report.add("error", name, "unexpected_observation_columns", len(forbidden), str(sorted(forbidden)))
    view = {name: frame.copy() for name, frame in raw.items()}
    for name, columns in {"users": ("upi_id",), "transactions": ("sender_id", "receiver_id")}.items():
        if name in view:
            for col in columns:
                if col in view[name]:
                    view[name][col] = view[name][col].map(normalized_id, na_action="ignore")
    if "transactions" in view and "beneficiary_handle" in view["transactions"]:
        view["transactions"]["beneficiary_handle"] = view["transactions"]["beneficiary_handle"].str.strip().str.lower()
    for name, frame in raw.items():
        if "source_version" not in frame:
            report.add("error", name, "missing_source_version", 1)
        else:
            report.add("error", name, "missing_source_version", frame["source_version"].isna().sum())
        if "data_source" in frame:
            report.add("error", name, "unsupported_source", (~frame["data_source"].isin(["synthetic"])).sum())
    report.issues.extend(validate_all(view, require_profiles=False).issues)
    return raw, report


def clean_observations(raw, ingested_at):
    cleaned = {name: frame.copy() for name, frame in raw.items()}
    for name, frame in cleaned.items():
        frame["processing_version"] = VERSION
        frame["ingested_at_utc"] = ingested_at
        for col in EVENT_TIMES.get(name, ()):
            frame[f"{col}_utc"] = _ts(frame[col])
    messages = cleaned["messages"]
    messages["message_normalized"] = messages["message"].map(normalized_text)
    messages["urls_normalized"] = messages["message_normalized"].map(normalized_urls)
    transactions = cleaned["transactions"]
    transactions["amount_normalized"] = pd.to_numeric(transactions["amount"])
    transactions["currency_normalized"] = transactions["currency"].str.strip().str.upper()
    for col in ("sender_id", "receiver_id"):
        transactions[f"{col}_normalized"] = transactions[col].map(normalized_id)
    cleaned["users"]["upi_id_normalized"] = cleaned["users"]["upi_id"].map(normalized_id)
    return cleaned


def source_files(data_dir):
    d = dirs(data_dir)
    paths = {name: d["raw"] / f"{name}.csv" for name in TABLES if name != "user_profiles"}
    paths["user_profiles"] = d["profiles"] / "user_profiles.csv"
    paths.update({name: d["truth"] / f"{name}.csv" for name in TRUTH_TABLES})
    return paths


def _hashes(paths):
    return {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in paths.items()}


def verify_cleaned(data_dir):
    d = dirs(data_dir)
    try:
        manifest = json.loads((d["cleaned"] / "manifest.json").read_text(encoding="utf-8"))
        if manifest["processing_version"] == VERSION and manifest["ok"]:
            cleaned = {name: d["cleaned"] / f"{name}.csv" for name in EVENT_TIMES | {"users": ()}}
            if (manifest["source_sha256"] == _hashes(source_files(data_dir)) and
                    manifest["cleaned_sha256"] == _hashes(cleaned)):
                return
    except (OSError, KeyError, ValueError):
        pass
    raise ValueError("Cleaned data is missing or stale. Run ingestion before reusing it.")


def ingest(data_dir, ingested_at_utc=None):
    d = dirs(data_dir)
    raw, report = load_observations(data_dir)
    paths = {"user_profiles": d["profiles"] / "user_profiles.csv"}
    paths.update({name: d["truth"] / f"{name}.csv" for name in TRUTH_TABLES})
    supplements = read_inputs(paths, report)
    if report.ok:
        profile_report = validate_all({**raw, "user_profiles": supplements["user_profiles"]})
        report.issues.extend(issue for issue in profile_report.issues if issue.table == "user_profiles")
        validate_truth(raw, {name: supplements[name] for name in TRUTH_TABLES}, report)
    ingested_at = pd.Timestamp.now(tz="UTC").isoformat()
    if ingested_at_utc is not None:
        timestamp = pd.Timestamp(ingested_at_utc)
        if timestamp.tzinfo is None:
            raise ValueError("Ingestion timestamp requires an explicit timezone")
        ingested_at = timestamp.tz_convert("UTC").isoformat()
    output_counts = {}
    d["reports"].mkdir(parents=True, exist_ok=True)
    manifest = d["cleaned"] / "manifest.json"
    manifest.unlink(missing_ok=True)
    if report.ok:
        cleaned = clean_observations(raw, ingested_at)
        write_tables(cleaned, d["cleaned"])
        output_counts = {name: len(frame) for name, frame in cleaned.items()}
    provenance = {
        name: sorted(str(value) for value in frame["source_version"].dropna().unique())
        for name, frame in {**raw, **supplements}.items() if "source_version" in frame
    }
    report_data = {**report.to_dict(), "processing_version": VERSION,
                   "ingested_at_utc": ingested_at, "cleaned_observation_row_counts": output_counts,
                   "excluded_observation_rows": 0 if report.ok else sum(
                       report.row_counts.get(name, 0) for name in TABLES if name != "user_profiles"),
                   "batch_policy": "reject_on_error", "source_versions": provenance,
                   "source_types": {name: sorted(str(value) for value in frame["data_source"].dropna().unique())
                                    for name, frame in {**raw, **supplements}.items() if "data_source" in frame}}
    (d["reports"] / "validation_report.json").write_text(json.dumps(report_data, indent=2), encoding="utf-8")
    if report.ok:
        completion = {**report_data, "source_sha256": _hashes(source_files(data_dir)),
                      "cleaned_sha256": _hashes({name: d["cleaned"] / f"{name}.csv" for name in output_counts})}
        manifest.write_text(json.dumps(completion, indent=2), encoding="utf-8")
    return report
