"""Runs enrichment + conversation + transaction feature builders and writes data/processed/."""
from __future__ import annotations

from crossfraud.data.ingestion import clean_observations, load_observations
from crossfraud.features.conversation_features import build_conversation_features
from crossfraud.features.text_features import enrich_messages
from crossfraud.features.transaction_features import build_transaction_features
from crossfraud.io import dirs, write_tables


def run_features(data_dir: str = "data") -> dict:
    d = dirs(data_dir)
    raw_str, rep = load_observations(data_dir)
    if not rep.ok:
        raise SystemExit("Refusing to build features from invalid data:\n" + rep.summary())
    raw = clean_observations(raw_str, None)
    for name, frame in raw.items():
        for column in raw_str[name]:
            if f"{column}_utc" in frame:
                frame[column] = frame[f"{column}_utc"]
    raw["messages"]["message"] = raw["messages"]["message_normalized"]
    raw["messages"] = raw["messages"][list(raw_str["messages"])]
    for column in ("amount", "sender_id", "receiver_id"):
        raw["transactions"][column] = raw["transactions"][f"{column}_normalized"]

    msgs = enrich_messages(raw["messages"])
    conv = build_conversation_features(msgs, raw["conversations"])
    txn = build_transaction_features(raw["transactions"])
    out = {"messages_enriched": msgs, "conversation_features": conv, "transaction_features": txn}
    write_tables(out, d["processed"])

    # TF-IDF sanity check only (NOT persisted: Phase 2 must fit TF-IDF on the training split only).
    from sklearn.feature_extraction.text import TfidfVectorizer
    X = TfidfVectorizer(min_df=2, ngram_range=(1, 2)).fit_transform(conv["conversation_text"])
    print(f"TF-IDF representation check: {X.shape[0]} conversations x {X.shape[1]} terms (not saved)")
    return out
