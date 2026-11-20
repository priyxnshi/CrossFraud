"""Adapter for PUBLIC text datasets (optional, not part of the default pipeline).

adapt_sms_spam() maps the widely used 'SMS Spam Collection' layout (label ham/spam + text)
into the Phase 1 messages schema so the Phase 2 text classifier can optionally be
pre-trained/benchmarked on it. IMPORTANT LIMITS: that data has no timestamps, no
conversations and no payment link, so it can NOT be used for cross-platform correlation.
You must download the file yourself; nothing is downloaded or bundled here.
"""
from __future__ import annotations

import pandas as pd

from crossfraud.schemas import MESSAGE_COLS


def adapt_sms_spam(path: str, source_name: str = "public:sms_spam_collection") -> pd.DataFrame:
    if str(path).lower().endswith((".tsv", ".txt")):
        df = pd.read_csv(path, sep="\t", header=None, names=["label", "text"], encoding="latin-1")
    else:  # common CSV export: first two columns are label, text
        df = pd.read_csv(path, encoding="latin-1").iloc[:, :2]
        df.columns = ["label", "text"]
    df = df.dropna(subset=["label", "text"]).reset_index(drop=True)
    lab = df["label"].astype(str).str.strip().str.lower().map({"spam": 1, "ham": 0})
    out = pd.DataFrame({
        "message_id": [f"PM{i:06d}" for i in range(len(df))],
        "conversation_id": [f"PC{i:06d}" for i in range(len(df))],  # 1 message == 1 pseudo-conversation
        "sender_id": [f"sms_sender_{i}" for i in range(len(df))],
        "receiver_id": "sms_receiver",
        "timestamp": pd.NaT,  # not available in this dataset
        "message": df["text"].astype(str),
        "message_type": "text",
        "spam_label": lab.astype("Int64"),
        "data_source": source_name,
    })
    return out[[*MESSAGE_COLS, "spam_label"]]
