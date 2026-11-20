"""Paths and CSV helpers shared by all phases."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_TABLES = ["users", "conversations", "messages", "transactions"]
TRUTH_TABLES = ["scammers", "conversation_truth", "message_stages",
                "transaction_truth", "links"]
PROCESSED_TABLES = ["messages_enriched", "conversation_features", "transaction_features"]


def dirs(data_dir: str | Path) -> dict[str, Path]:
    root = Path(data_dir)
    return {"raw": root / "raw", "truth": root / "ground_truth",
            "processed": root / "processed", "reports": root / "reports",
            "external": root / "external", "profiles": root / "profiles", "cleaned": root / "cleaned"}


def write_tables(tables: dict[str, pd.DataFrame], folder: str | Path) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    for name, df in tables.items():
        df.to_csv(folder / f"{name}.csv", index=False)


def load_tables(folder: str | Path, names: list[str]) -> dict[str, pd.DataFrame]:
    """Read CSVs as strings so the validator can see malformed values."""
    return {n: pd.read_csv(Path(folder) / f"{n}.csv", dtype=str, keep_default_na=False,
                           na_values=[""]) for n in names}


def to_typed(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out = {k: v.copy() for k, v in raw.items()}
    m = out["messages"]
    m["timestamp"] = pd.to_datetime(m["timestamp"], errors="coerce")
    if "scam_label" in m:
        m["scam_label"] = pd.to_numeric(m["scam_label"], errors="coerce").astype("Int64")
    c = out["conversations"]
    for col in ("start_ts", "end_ts"):
        c[col] = pd.to_datetime(c[col], errors="coerce")
    if "scam_label" in c:
        c["scam_label"] = pd.to_numeric(c["scam_label"], errors="coerce").astype("Int64")
    t = out["transactions"]
    t["timestamp"] = pd.to_datetime(t["timestamp"], errors="coerce")
    t["amount"] = pd.to_numeric(t["amount"], errors="coerce")
    if "fraud_label" in t:
        t["fraud_label"] = pd.to_numeric(t["fraud_label"], errors="coerce").astype("Int64")
    return out
