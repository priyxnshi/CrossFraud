"""Model output contract shared by the messaging and payment models (consumed by Phase 3).

Every model returns a plain dict (JSON-serialisable):
{
  "contract_version": "1.0",
  "entity_id": "C00038",            # conversation_id or transaction_id
  "entity_type": "conversation" | "transaction",
  "risk_score": 0.97,               # model score in [0, 1]; NOT a calibrated probability
  "risk_level": "low" | "medium" | "high",
  "predicted_class": 0 | 1,
  "predicted_label": "legitimate" | "fraud",
  "threshold": 0.5,                 # decision threshold used for predicted_class
  "model": "messaging_combined_logreg_v1",
  "event_time": "2025-02-09T20:33:06" | None,   # last message time / transaction time
  "signals": [ {"name", "source": "rule"|"model", "detail", "weight"} ],
  "evidence": {...},                # fields Phase 3 matches on (UPI IDs, amounts, times, parties)
  "meta": {...}                     # input-quality notes (assumed defaults, history availability)
}
risk_level is relative to the model's own threshold, so it always agrees with predicted_class:
  high   : score >= threshold          (predicted_class == 1)
  medium : score >= threshold / 2
  low    : otherwise
"""
from __future__ import annotations

import math

CONTRACT_VERSION = "1.0"
ENTITY_TYPES = ("conversation", "transaction")
RISK_LEVELS = ("low", "medium", "high")
REQUIRED_KEYS = ("contract_version", "entity_id", "entity_type", "risk_score", "risk_level",
                 "predicted_class", "predicted_label", "threshold", "model", "event_time",
                 "signals", "evidence", "meta")


class InvalidInputError(ValueError):
    """Raised when a model is given missing or malformed input."""


def risk_level(score: float, threshold: float) -> str:
    if score >= threshold:
        return "high"
    if score >= threshold / 2:
        return "medium"
    return "low"


def signal(name: str, source: str, detail: str = "", weight: float | None = None) -> dict:
    assert source in ("rule", "model")
    return {"name": name, "source": source, "detail": detail,
            "weight": None if weight is None else round(float(weight), 4)}


def make_result(entity_id, entity_type, score, threshold, model, signals,
                evidence=None, event_time=None, meta=None) -> dict:
    score = float(score)
    pred = int(score >= threshold)
    return {
        "contract_version": CONTRACT_VERSION,
        "entity_id": str(entity_id),
        "entity_type": entity_type,
        "risk_score": round(score, 4),
        "risk_level": risk_level(score, threshold),
        "predicted_class": pred,
        "predicted_label": "fraud" if pred else "legitimate",
        "threshold": round(float(threshold), 4),
        "model": model,
        "event_time": event_time,
        "signals": list(signals),
        "evidence": evidence or {},
        "meta": meta or {},
    }


def validate_result(r: dict) -> list[str]:
    """Return a list of contract violations (empty list == valid)."""
    problems = []
    if not isinstance(r, dict):
        return ["result is not a dict"]
    for k in REQUIRED_KEYS:
        if k not in r:
            problems.append(f"missing key: {k}")
    if problems:
        return problems
    s = r["risk_score"]
    if not isinstance(s, (int, float)) or isinstance(s, bool) or math.isnan(s) or not 0.0 <= s <= 1.0:
        problems.append("risk_score must be a number in [0, 1]")
    if r["entity_type"] not in ENTITY_TYPES:
        problems.append("invalid entity_type")
    if r["risk_level"] not in RISK_LEVELS:
        problems.append("invalid risk_level")
    if r["predicted_class"] not in (0, 1):
        problems.append("predicted_class must be 0 or 1")
    if not isinstance(r["signals"], list) or not all(
            isinstance(x, dict) and {"name", "source", "detail", "weight"} <= set(x) for x in r["signals"]):
        problems.append("signals must be a list of {name, source, detail, weight}")
    if not problems and (r["predicted_class"] == 1) != (r["risk_level"] == "high"):
        problems.append("risk_level and predicted_class disagree")
    return problems
