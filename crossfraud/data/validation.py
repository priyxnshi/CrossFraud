"""Data validation for the RAW layer: schema, missing values, timestamps, amounts,
duplicates and identifier consistency. Works on string-typed frames (as read from CSV)."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from crossfraud.schemas import (BENEFICIARY_TYPES, MESSAGE_TYPES, TABLES,
                                TRANSACTION_TYPES)

TG_ID_RE = re.compile(r"^tg_(?:u\d{4}|s\d{3})$")
UPI_RE = re.compile(r"^[a-z0-9._-]{2,}@[a-z]{2,}$")


@dataclass
class ValidationConfig:
    min_ts: str = "2020-01-01"
    max_ts: str = "2035-01-01"
    max_amount: float = 100000.0  # configurable per-transaction sanity cap (warning)


@dataclass
class Issue:
    severity: str  # "error" | "warning"
    table: str
    check: str
    count: int
    detail: str = ""


@dataclass
class ValidationReport:
    issues: list = field(default_factory=list)
    row_counts: dict = field(default_factory=dict)

    def add(self, severity, table, check, count, detail=""):
        count = int(count)
        if count > 0:
            self.issues.append(Issue(severity, table, check, count, detail))

    @property
    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def checks(self) -> set:
        return {i.check for i in self.issues}

    def to_dict(self):
        return {"ok": self.ok, "row_counts": self.row_counts,
                "n_errors": len(self.errors),
                "n_warnings": len(self.issues) - len(self.errors),
                "issues": [asdict(i) for i in self.issues]}

    def save(self, path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(self.to_dict(), indent=2))

    def summary(self) -> str:
        lines = [f"Validation: {'OK' if self.ok else 'FAILED'}  "
                 f"({len(self.errors)} errors, {len(self.issues) - len(self.errors)} warnings)"]
        for i in self.issues:
            lines.append(f"  [{i.severity.upper()}] {i.table}.{i.check}: {i.count} {i.detail}")
        return "\n".join(lines)


def _blank(s: pd.Series) -> pd.Series:
    return s.isna() | s.astype(str).str.strip().eq("")


def _ts(s: pd.Series) -> pd.Series:
    parts = s.astype("string").str.strip()
    offset = parts.str.contains(r"[T ].*(?:Z|[+-]\d{2}(?::?\d{2})?)$", case=False, na=False)
    local = pd.to_datetime(parts.where(~offset), errors="coerce", format="ISO8601")
    local = local.dt.tz_localize("Asia/Kolkata").dt.tz_convert("UTC")
    explicit = pd.to_datetime(parts.where(offset), errors="coerce", format="ISO8601", utc=True)
    return local.where(~offset, explicit)


def validate_all(raw: dict, cfg: ValidationConfig | None = None, *, require_profiles: bool = True) -> ValidationReport:
    cfg = cfg or ValidationConfig()
    rep = ValidationReport()
    usable = set()
    raw = raw.copy()
    legacy = {"messages": "scam_label", "conversations": "scam_label", "transactions": "fraud_label"}

    # ---- schema ----
    for t, cols in TABLES.items():
        if t == "user_profiles" and not require_profiles:
            continue
        if t not in raw:
            rep.add("error", t, "table_missing", 1)
            continue
        rep.row_counts[t] = len(raw[t])
        missing = [c for c in cols if c not in raw[t].columns]
        extra = [c for c in raw[t].columns if c not in {*cols, "source_version", legacy.get(t)}]
        if t in legacy and legacy[t] not in raw[t]:
            raw[t] = raw[t].assign(**{legacy[t]: pd.NA})
        rep.add("error", t, "schema_missing_columns", len(missing), str(missing))
        rep.add("warning", t, "schema_unexpected_columns", len(extra), str(extra))
        if not missing:
            usable.add(t)

    # ---- missing values (required columns only) ----
    for t in usable:
        for c in TABLES[t]:
            rep.add("error", t, "missing_values", _blank(raw[t][c]).sum(), f"column={c}")

    lo, hi = pd.Timestamp(cfg.min_ts, tz="UTC"), pd.Timestamp(cfg.max_ts, tz="UTC")

    def check_ts(table, col):
        s = raw[table][col]
        p = _ts(s)
        rep.add("error", table, "invalid_timestamp", (p.isna() & s.notna()).sum(), f"column={col}")
        rep.add("error", table, "timestamp_out_of_range", ((p < lo) | (p > hi)).sum(), f"column={col}")
        return p

    # ---- users ----
    if "users" in usable:
        u = raw["users"]
        rep.add("error", "users", "duplicate_id", u["user_id"].duplicated().sum())
        rep.add("error", "users", "duplicate_telegram_id", u["telegram_id"].duplicated().sum())
        rep.add("error", "users", "duplicate_upi_id", u["upi_id"].duplicated().sum())
        rep.add("error", "users", "identifier_format",
                (~u["upi_id"].astype(str).str.match(UPI_RE) |
                 ~u["telegram_id"].astype(str).str.match(TG_ID_RE)).sum())

    if "user_profiles" in usable:
        profiles = raw["user_profiles"]
        rep.add("error", "user_profiles", "duplicate_id", profiles["user_id"].duplicated().sum())
        if "users" in usable:
            expected = set(raw["users"]["user_id"])
            actual = set(profiles["user_id"])
            rep.add("error", "user_profiles", "profile_reference_mismatch", len(expected ^ actual))

    # ---- conversations ----
    if "conversations" in usable:
        c = raw["conversations"]
        rep.add("error", "conversations", "duplicate_id", c["conversation_id"].duplicated().sum())
        s, e = check_ts("conversations", "start_ts"), check_ts("conversations", "end_ts")
        rep.add("error", "conversations", "start_after_end", (s > e).sum())
        rep.add("error", "conversations", "same_participants", (c["participant_a"] == c["participant_b"]).sum())
        lab = pd.to_numeric(c["scam_label"], errors="coerce")
        rep.add("error", "conversations", "invalid_label", (c["scam_label"].notna() & ~lab.isin([0, 1])).sum())
        rep.add("error", "conversations", "invalid_platform", (~c["platform"].isin(["telegram", "whatsapp"])).sum())
        syn = c["data_source"] == "synthetic"
        bad = syn & ~(c["participant_a"].astype(str).str.match(TG_ID_RE) & c["participant_b"].astype(str).str.match(TG_ID_RE))
        rep.add("error", "conversations", "identifier_format", bad.sum(), "telegram id format")

    # ---- messages ----
    if "messages" in usable:
        m = raw["messages"]
        rep.add("error", "messages", "duplicate_id", m["message_id"].duplicated().sum())
        rep.add("warning", "messages", "duplicate_record",
                m.duplicated(["conversation_id", "sender_id", "timestamp", "message"]).sum())
        p = check_ts("messages", "timestamp")
        rep.add("error", "messages", "invalid_message_type", (~m["message_type"].isin(MESSAGE_TYPES)).sum())
        lab = pd.to_numeric(m["scam_label"], errors="coerce")
        rep.add("error", "messages", "invalid_label", (m["scam_label"].notna() & ~lab.isin([0, 1])).sum())
        rep.add("error", "messages", "sender_equals_receiver", (m["sender_id"] == m["receiver_id"]).sum())
        if "conversations" in usable:
            c = raw["conversations"]
            rep.add("error", "messages", "unknown_conversation_id",
                    (~m["conversation_id"].isin(c["conversation_id"])).sum())
            j = m.assign(_p=p).merge(
                c.assign(_s=_ts(c["start_ts"]), _e=_ts(c["end_ts"]))[
                    ["conversation_id", "participant_a", "participant_b", "_s", "_e", "scam_label"]],
                on="conversation_id", how="inner", suffixes=("", "_conv"))
            ok_pair = (((j["sender_id"] == j["participant_a"]) & (j["receiver_id"] == j["participant_b"])) |
                       ((j["sender_id"] == j["participant_b"]) & (j["receiver_id"] == j["participant_a"])))
            rep.add("error", "messages", "participants_inconsistent", (~ok_pair).sum(),
                    "sender/receiver not the conversation's two participants")
            rep.add("error", "messages", "timestamp_outside_conversation",
                    ((j["_p"] < j["_s"]) | (j["_p"] > j["_e"])).sum())
            both = j["scam_label"].notna() & j["scam_label_conv"].notna()
            rep.add("error", "messages", "label_mismatch_with_conversation",
                    (both & (j["scam_label"] != j["scam_label_conv"])).sum())
            rep.add("warning", "conversations", "conversation_without_messages",
                    (~c["conversation_id"].isin(m["conversation_id"])).sum())

    # ---- transactions ----
    if "transactions" in usable:
        t = raw["transactions"]
        rep.add("error", "transactions", "duplicate_id", t["transaction_id"].duplicated().sum())
        rep.add("warning", "transactions", "duplicate_record",
                t.duplicated(["sender_id", "receiver_id", "timestamp", "amount"]).sum())
        check_ts("transactions", "timestamp")
        a = pd.to_numeric(t["amount"], errors="coerce")
        rep.add("error", "transactions", "non_finite_amount", (a.notna() & ~np.isfinite(a)).sum())
        rep.add("error", "transactions", "invalid_currency", (~t["currency"].str.strip().str.upper().eq("INR")).sum())
        rep.add("error", "transactions", "invalid_status", (~t["status_at_event"].isin(["accepted", "failed"])).sum())
        rep.add("error", "transactions", "non_numeric_amount", (a.isna() & t["amount"].notna()).sum())
        rep.add("error", "transactions", "non_positive_amount", (a <= 0).sum())
        rep.add("warning", "transactions", "amount_above_cap", (a > cfg.max_amount).sum(),
                f"cap={cfg.max_amount}")
        rep.add("error", "transactions", "sender_equals_receiver", (t["sender_id"] == t["receiver_id"]).sum())
        rep.add("error", "transactions", "invalid_transaction_type", (~t["transaction_type"].isin(TRANSACTION_TYPES)).sum())
        rep.add("error", "transactions", "invalid_beneficiary_type", (~t["beneficiary_type"].isin(BENEFICIARY_TYPES)).sum())
        lab = pd.to_numeric(t["fraud_label"], errors="coerce")
        rep.add("error", "transactions", "invalid_label", (t["fraud_label"].notna() & ~lab.isin([0, 1])).sum())
        syn = t["data_source"] == "synthetic"
        rep.add("error", "transactions", "identifier_format",
                (syn & ~t["receiver_id"].astype(str).str.match(UPI_RE)).sum(), "receiver UPI format")
        handle = t["receiver_id"].astype(str).str.split("@").str[-1]
        rep.add("error", "transactions", "beneficiary_handle_mismatch", (handle != t["beneficiary_handle"]).sum())
        if "users" in usable:
            rep.add("error", "transactions", "unknown_sender_id",
                    (~t["sender_id"].isin(raw["users"]["upi_id"])).sum(),
                    "sender must be a known account holder")
    return rep
