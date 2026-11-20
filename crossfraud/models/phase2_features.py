"""Prediction-time observations and a deliberately simple Phase 2 link baseline."""
from __future__ import annotations

import pandas as pd

from crossfraud.data.ingestion import normalized_id, normalized_text
from crossfraud.data.validation import _ts
from crossfraud.features.text_features import enrich_messages
from crossfraud.models.messaging import build_model_frame


def observation_times(values):
    """Use source offsets, defaulting naive timestamps to India time."""
    return _ts(pd.Series(values))


def conversation_prefixes(messages, conversations, cutoffs):
    """cutoffs contains conversation_id and cutoff_utc. Empty prefixes yield no score row."""
    m = messages.copy()
    m["timestamp"] = observation_times(m["timestamp"])
    checkpoints = cutoffs.copy()
    checkpoints["cutoff_utc"] = observation_times(checkpoints["cutoff_utc"])
    m = m.merge(checkpoints, on="conversation_id", validate="many_to_one")
    m = m.loc[m["timestamp"].le(m["cutoff_utc"])].copy()
    if m.empty:
        return pd.DataFrame(columns=["conversation_id", "cutoff_utc"])
    m["message"] = m["message"].map(normalized_text)
    frame = build_model_frame(enrich_messages(m), conversations[["conversation_id"]])
    return frame.merge(checkpoints, on="conversation_id", validate="one_to_one")


def match_candidates(request, transactions, as_of, window_minutes=180, amount_tolerance=0.10):
    """Return exact normalized payee matches observed by as_of, ranked by amount and delay."""
    if window_minutes <= 0 or not 0 <= amount_tolerance <= 1:
        raise ValueError("Require a positive window and an amount tolerance between zero and one")
    payee = request.get("first_payment_request_upi")
    if not isinstance(payee, str) or not payee:
        return []
    requested, cutoff = observation_times([request.get("first_payment_request_ts"), as_of])
    if pd.isna(requested) or pd.isna(cutoff) or cutoff < requested:
        return []
    attempt_times = observation_times(transactions["timestamp"])
    elapsed = (attempt_times - requested).dt.total_seconds().div(60)
    candidates = transactions.loc[elapsed.between(0, window_minutes, inclusive="right") &
                                  attempt_times.le(cutoff)].copy()
    candidates = candidates.loc[candidates["receiver_id"].map(normalized_id).eq(normalized_id(payee))]
    if "sender_id" in request:
        candidates = candidates.loc[candidates["sender_id"].map(normalized_id).eq(
            normalized_id(request["sender_id"]))]
    amount = request.get("first_payment_request_amount")
    amount = pd.to_numeric(amount, errors="coerce")
    candidates["delay_minutes"] = elapsed
    candidates["amount_difference_inr"] = (
        pd.to_numeric(candidates["amount"], errors="coerce").sub(amount).abs()
        if pd.notna(amount) and amount > 0 else float("nan")
    )
    candidates["amount_within_tolerance"] = candidates["amount_difference_inr"].le(amount * amount_tolerance)
    candidates = candidates.sort_values(
        ["amount_within_tolerance", "delay_minutes", "transaction_id"], ascending=[False, True, True])
    return [
        {"transaction_id": row.transaction_id, "payee_match": "normalized_exact",
         "delay_minutes": row.delay_minutes,
         "amount_difference_inr": row.amount_difference_inr if pd.notna(row.amount_difference_inr) else None,
         "amount_within_tolerance": bool(row.amount_within_tolerance)}
        for row in candidates.itertuples(index=False)
    ]


def score_conversation_as_of(model, messages, as_of, entity_id="conversation"):
    """Score a timestamped observable prefix through the shared review contract."""
    from crossfraud.models.contract import InvalidInputError

    if not messages:
        raise InvalidInputError("At least one timestamped message is required")
    cutoff = observation_times([as_of]).iloc[0]
    times = observation_times([message.get("timestamp") for message in messages])
    if pd.isna(cutoff) or times.isna().any():
        raise InvalidInputError("A valid cutoff and message timestamps are required")
    prefix = [
        {**message, "timestamp": timestamp, "message": normalized_text(message["message"])}
        for message, timestamp in zip(messages, times) if timestamp <= cutoff
    ]
    if not prefix:
        raise InvalidInputError("No message is observable at the cutoff")
    result = model.predict(prefix, entity_id=entity_id)
    result["meta"].update({"scored_as_of_utc": cutoff.isoformat(), "review_only": True})
    return result


def score_payment_attempt(model, attempt, history=None, entity_id=None):
    """Score an attempt using the same local-time and ID normalization as training."""
    from crossfraud.models.contract import InvalidInputError

    updated = dict(attempt)
    current = observation_times([updated.get("timestamp")]).iloc[0]
    if pd.isna(current):
        raise InvalidInputError("Payment timestamp is required")
    updated["timestamp"] = current.tz_convert("Asia/Kolkata")
    for key in ("sender_id", "receiver_id"):
        if isinstance(updated.get(key), str):
            updated[key] = normalized_id(updated[key])
    if history is not None:
        history = history.copy()
        times = observation_times(history["timestamp"])
        if times.isna().any():
            raise InvalidInputError("History contains invalid timestamps")
        history["timestamp"] = times.dt.tz_convert("Asia/Kolkata")
        history = history.loc[history["timestamp"].lt(updated["timestamp"])].copy()
        for key in ("sender_id", "receiver_id"):
            history[key] = history[key].map(normalized_id)
    result = model.predict(updated, history, entity_id=entity_id)
    result["meta"].update({"scored_as_of_utc": current.isoformat(), "review_only": True})
    return result
