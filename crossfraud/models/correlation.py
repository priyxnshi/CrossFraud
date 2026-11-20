"""Auditable UPI link candidates using only observations at the decision cutoff."""
from __future__ import annotations

from dataclasses import dataclass
import re

import pandas as pd

from crossfraud.data.ingestion import normalized_id, normalized_text
from crossfraud.features.text_features import AMOUNT_RE
from crossfraud.models.phase2_features import observation_times

_ADDRESS = re.compile(r"\b([a-z0-9][a-z0-9._-]+)\s*(?:@|\bat\b|\[at\]|\(at\))\s*([a-z][a-z0-9]+)\b", re.I)


@dataclass(frozen=True)
class MatchConfig:
    window_minutes: float = 180
    amount_fraction: float = 0.10
    amount_floor_inr: float = 10
    minimum_confidence: float = 0.75
    ambiguity_margin: float = 0.06

    def __post_init__(self):
        if not (self.window_minutes > 0 and self.amount_floor_inr >= 0 and
                0 <= self.amount_fraction <= 1 and 0 <= self.minimum_confidence <= 1 and
                0 <= self.ambiguity_margin <= 1):
            raise ValueError("Invalid matching thresholds")


def _one_edit(left, right):
    if abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    short, long = sorted((left, right), key=len)
    first = next((i for i, (a, b) in enumerate(zip(short, long)) if a != b), len(short))
    return short == long[:first] + long[first + 1:]


def build_requests(messages, conversations):
    """Extract request evidence without using stages, truth links, or conversation end time."""
    participants = conversations.set_index("conversation_id")["participant_a"]
    timestamps = observation_times(messages["timestamp"])
    rows = []
    for msg, timestamp in zip(messages.itertuples(index=False), timestamps):
        text = normalized_text(msg.message)
        amount_match = AMOUNT_RE.search(text)
        amount = float(amount_match[1].replace(",", "")) if amount_match else None
        for identifier in _ADDRESS.finditer(text):
            written = identifier[0]
            canonical = f"{identifier[1].lower()}@{identifier[2].lower()}"
            rows.append({"conversation_id": msg.conversation_id, "message_id": msg.message_id,
                         "participant": participants[msg.conversation_id], "request_time": timestamp,
                         "payee": canonical, "written": written, "requested_amount": amount})
    fields = ["conversation_id", "message_id", "participant", "request_time", "payee",
              "written", "requested_amount"]
    return pd.DataFrame(rows, columns=fields)


def match_payment(attempt, requests, as_of, payer_participant=None, config=MatchConfig()):
    """Rank competing conversations for one observed attempt. Confidence is heuristic."""
    attempted, cutoff = observation_times([attempt["timestamp"], as_of])
    if pd.isna(attempted) or pd.isna(cutoff) or attempted > cutoff or requests.empty:
        return {"status": "no_match", "reason": "no observable payment and request pair",
                "selected": None, "candidates": []}
    requests = requests.reset_index(drop=True)
    elapsed = (attempted - requests["request_time"]).dt.total_seconds().div(60)
    eligible = requests.loc[elapsed.gt(0) & elapsed.le(config.window_minutes)]
    payee = normalized_id(attempt["receiver_id"])
    local, _, handle = payee.partition("@")
    best_by_conversation = {}
    for row in eligible.itertuples():
        original, _, bank = row.payee.partition("@")
        if row.payee == payee:
            style, base = ("exact", 0.67) if row.written == payee else ("normalized_exact", 0.64)
        elif bank == handle and min(len(original), len(local)) >= 6 and _one_edit(original, local):
            style, base = "one_edit_local_part", 0.40
        else:
            continue
        delay = float(elapsed.loc[row.Index])
        support = [style, "request_preceded_payment"]
        conflicts = []
        payer_agrees = payer_participant is not None and row.participant == payer_participant
        if payer_participant is None:
            conflicts.append("payer identity unavailable")
        elif payer_agrees:
            support.append("payer mapping agrees")
            base += 0.14
        else:
            conflicts.append("payer mapping conflicts")
            base -= 0.35
        difference = None
        if pd.isna(row.requested_amount):
            conflicts.append("requested amount unavailable")
        else:
            difference = abs(float(attempt["amount"]) - row.requested_amount)
            if difference <= max(config.amount_floor_inr, row.requested_amount * config.amount_fraction):
                support.append("amount within tolerance")
                base += 0.16
            else:
                conflicts.append("amount outside tolerance")
                base -= 0.05
        base += 0.06 * (1 - delay / config.window_minutes)
        confidence = min(1.0, max(0.0, base))
        candidate = {"conversation_id": row.conversation_id, "request_message_id": row.message_id,
                     "request_time_utc": row.request_time.isoformat(),
                     "payment_time_utc": attempted.isoformat(), "confidence": confidence,
                     "identifier_evidence": style, "amount_difference_inr": difference,
                     "delay_minutes": delay, "support": support, "conflicts": conflicts}
        prior = best_by_conversation.get(row.conversation_id)
        if prior is None or candidate["confidence"] > prior["confidence"]:
            best_by_conversation[row.conversation_id] = candidate
    candidates = sorted(best_by_conversation.values(), key=lambda x: (-x["confidence"], x["conversation_id"]))
    if not candidates or candidates[0]["confidence"] < config.minimum_confidence:
        status, reason = "no_match", "confidence below threshold or no eligible candidate"
    elif len(candidates) > 1 and candidates[0]["confidence"] - candidates[1]["confidence"] <= config.ambiguity_margin:
        status, reason = "ambiguous", "competing conversation within confidence margin"
    else:
        status, reason = "matched", "leading candidate cleared threshold and margin"
    return {"status": status, "reason": reason,
            "selected": candidates[0] if status == "matched" else None, "candidates": candidates}


def make_alert(kind, decision_time, score, threshold, entity_id, evidence, model_versions):
    timestamp = observation_times([decision_time]).iloc[0].isoformat()
    level = "high" if score >= threshold else ("medium" if score >= threshold * 0.5 else "low")
    return {"schema_version": "phase3-alert-v1", "kind": kind, "entity_id": entity_id,
            "event_time_utc": timestamp, "earliest_possible_alert_time_utc": timestamp,
            "risk_score": float(score), "threshold": float(threshold), "risk_level": level,
            "model_versions": model_versions, "evidence": evidence,
            "interpretation": "Review signal only. A reviewer must corroborate the evidence."}
