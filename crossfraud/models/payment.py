"""Phase 2 / Part B: UPI/payment fraud models.

Baseline: standardised Logistic Regression (interpretable coefficients).
Stronger: Random Forest. Both use class_weight to handle the ~1.4% fraud rate.
Both consume the Phase 1 transaction feature table (history features use earlier transactions only).
"""
from __future__ import annotations

from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from crossfraud.features.transaction_features import build_transaction_features
from crossfraud.models.contract import InvalidInputError, make_result, signal
from crossfraud.schemas import BENEFICIARY_TYPES, TRANSACTION_TYPES

KINDS = ("logreg", "random_forest")
PAYMENT_FEATURES = [
    "amount", "log_amount", "is_collect_request", "is_merchant_payment", "beneficiary_is_individual",
    "hour", "day_of_week", "is_night", "is_weekend",
    "sender_prior_txn_count", "has_history", "sender_prior_mean_amount", "sender_prior_std_amount",
    "amount_zscore", "amount_ratio_to_prior_mean", "amount_over_prior_max",
    "txn_count_1h", "txn_count_24h", "amount_sum_24h", "minutes_since_last_txn",
    "is_new_beneficiary", "pair_prior_txn_count", "payee_prior_txn_count",
    "payee_distinct_senders_prior", "new_beneficiary_high_amount",
]
# Heuristic (NOT learned) thresholds for the human-readable rule signals
RATIO_HIGH, VELOCITY_1H, VELOCITY_24H = 3.0, 3, 5


def build_payment_frame(raw_typed: dict, truth_dir: str | Path | None = None) -> pd.DataFrame:
    """Training frame from typed raw tables. `scenario` is attached only for reporting."""
    frame = build_transaction_features(raw_typed["transactions"])
    if truth_dir is not None:
        t = pd.read_csv(Path(truth_dir) / "transaction_truth.csv", dtype=str)
        frame = frame.merge(t, on="transaction_id", how="left")
    return frame


def make_estimator(kind: str, seed: int = 42):
    if kind == "logreg":
        return Pipeline([("scale", StandardScaler()),
                         ("clf", LogisticRegression(class_weight="balanced", max_iter=3000, random_state=seed))])
    if kind == "random_forest":
        # A fixed summation order makes exported scores byte-reproducible.
        return RandomForestClassifier(n_estimators=300, min_samples_leaf=3, class_weight="balanced_subsample",
                                      n_jobs=1, random_state=seed)
    raise ValueError(f"kind must be one of {KINDS}")


# ---- input validation ---------------------------------------------------------------------------
def _clean_txn(txn) -> tuple[dict, list]:
    if not isinstance(txn, dict):
        raise InvalidInputError("transaction must be a dict")
    for k in ("sender_id", "receiver_id", "timestamp", "amount"):
        if txn.get(k) in (None, ""):
            raise InvalidInputError(f"missing required field: {k}")
    for k in ("sender_id", "receiver_id"):
        if not isinstance(txn[k], str) or not txn[k].strip():
            raise InvalidInputError(f"{k} must be a non-empty string")
    if txn["sender_id"] == txn["receiver_id"]:
        raise InvalidInputError("sender_id and receiver_id must differ")
    amt = txn["amount"]
    if isinstance(amt, bool) or not isinstance(amt, (int, float, np.integer, np.floating)) \
            or not np.isfinite(amt) or amt <= 0:
        raise InvalidInputError("amount must be a finite number greater than 0")
    ts = pd.to_datetime(txn["timestamp"], errors="coerce")
    if pd.isna(ts):
        raise InvalidInputError("timestamp is not a valid date/time")
    assumed = []
    ttype = txn.get("transaction_type")
    if ttype is None:
        ttype = "P2P"
        assumed.append("transaction_type=P2P")
    elif ttype not in TRANSACTION_TYPES:
        raise InvalidInputError(f"transaction_type must be one of {sorted(TRANSACTION_TYPES)}")
    btype = txn.get("beneficiary_type")
    if btype is None:
        btype = "individual"
        assumed.append("beneficiary_type=individual")
    elif btype not in BENEFICIARY_TYPES:
        raise InvalidInputError(f"beneficiary_type must be one of {sorted(BENEFICIARY_TYPES)}")
    return {"transaction_id": "__new__", "sender_id": txn["sender_id"], "receiver_id": txn["receiver_id"],
            "timestamp": ts, "amount": float(amt), "transaction_type": ttype, "beneficiary_type": btype,
            "fraud_label": pd.NA}, assumed


def _clean_history(history, sender: str, receiver: str) -> pd.DataFrame:
    cols = ["transaction_id", "sender_id", "receiver_id", "timestamp", "amount", "transaction_type",
            "beneficiary_type", "fraud_label"]
    if history is None or len(history) == 0:
        return pd.DataFrame(columns=cols)
    if not isinstance(history, pd.DataFrame):
        raise InvalidInputError("history must be a DataFrame of earlier transactions")
    need = {"sender_id", "receiver_id", "timestamp", "amount"}
    if not need <= set(history.columns):
        raise InvalidInputError(f"history is missing columns: {sorted(need - set(history.columns))}")
    h = history.copy()
    # only the sender's own transactions and the payee's transactions can change this row's features
    h = h[(h["sender_id"] == sender) | (h["receiver_id"] == receiver)].copy()
    h["timestamp"] = pd.to_datetime(h["timestamp"], errors="coerce")
    h["amount"] = pd.to_numeric(h["amount"], errors="coerce")
    if h["timestamp"].isna().any() or h["amount"].isna().any():
        raise InvalidInputError("history contains invalid timestamps or amounts")
    if "transaction_id" not in h.columns:
        h["transaction_id"] = [f"H{i:07d}" for i in range(len(h))]
    for c, default in (("transaction_type", "P2P"), ("beneficiary_type", "individual"), ("fraud_label", pd.NA)):
        if c not in h.columns:
            h[c] = default
    return h[cols]


class PaymentModel:
    VERSION = "v1"

    def __init__(self, kind: str = "logreg", threshold: float = 0.5, seed: int = 42):
        self.kind, self.threshold, self.seed = kind, threshold, seed
        self.est = make_estimator(kind, seed)
        self.fitted = False

    @property
    def name(self) -> str:
        return f"payment_{self.kind}_{self.VERSION}"

    def fit(self, frame: pd.DataFrame, y) -> "PaymentModel":
        self.est.fit(frame[PAYMENT_FEATURES], np.asarray(y).astype(int))
        self.fitted = True
        return self

    def predict_proba_frame(self, frame: pd.DataFrame) -> np.ndarray:
        return self.est.predict_proba(frame[PAYMENT_FEATURES])[:, 1]

    def global_importance(self, k: int = 10) -> list:
        if self.kind == "logreg":
            vals = self.est.named_steps["clf"].coef_[0]
        else:
            vals = self.est.feature_importances_
        order = np.argsort(-np.abs(vals))[:k]
        return [{"feature": PAYMENT_FEATURES[i], "value": round(float(vals[i]), 4)} for i in order]

    @staticmethod
    def _rule_signals(r: pd.Series) -> list:
        sig = []
        if r["is_new_beneficiary"] == 1:
            sig.append(signal("new_beneficiary", "rule", "first payment from this sender to this payee"))
        if r["has_history"] == 1 and r["amount_ratio_to_prior_mean"] >= RATIO_HIGH:
            sig.append(signal("amount_far_above_usual", "rule",
                              f"{r['amount_ratio_to_prior_mean']:.1f}x the sender's usual amount"))
        if r["has_history"] == 1 and r["amount_over_prior_max"] > 1:
            sig.append(signal("amount_above_previous_max", "rule",
                              f"{r['amount_over_prior_max']:.1f}x the sender's previous maximum"))
        if r["new_beneficiary_high_amount"] == 1:
            sig.append(signal("new_beneficiary_high_amount", "rule", "new payee AND unusually large amount"))
        if r["txn_count_1h"] >= VELOCITY_1H or r["txn_count_24h"] >= VELOCITY_24H:
            sig.append(signal("high_velocity", "rule",
                              f"{int(r['txn_count_1h'])} txns in 1h, {int(r['txn_count_24h'])} in 24h"))
        if r["is_night"] == 1:
            sig.append(signal("night_time", "rule", f"hour={int(r['hour'])}"))
        if r["is_collect_request"] == 1:
            sig.append(signal("collect_request", "rule", "payment approved from a collect request"))
        if r["has_history"] == 0:
            sig.append(signal("limited_history", "rule", f"only {int(r['sender_prior_txn_count'])} prior txns"))
        return sig

    def _model_signals(self, row: pd.Series, top_k: int = 4, min_weight: float = 0.05) -> list:
        if self.kind != "logreg":
            return []
        scaler, clf = self.est.named_steps["scale"], self.est.named_steps["clf"]
        x = scaler.transform(row[PAYMENT_FEATURES].to_frame().T.astype(float))[0]
        contrib = x * clf.coef_[0]
        out = []
        for i in np.argsort(-contrib)[:top_k]:
            if contrib[i] < min_weight:
                break
            out.append(signal(f"model:{PAYMENT_FEATURES[i]}", "model",
                              f"{PAYMENT_FEATURES[i]}={row[PAYMENT_FEATURES[i]]:g}", contrib[i]))
        return out

    def predict(self, txn: dict, history: pd.DataFrame | None = None, entity_id: str | None = None) -> dict:
        """txn: {sender_id, receiver_id, timestamp, amount, [transaction_type], [beneficiary_type]}.
        history: earlier raw transactions (needed for history/velocity/new-beneficiary features)."""
        if not self.fitted:
            raise RuntimeError("model is not fitted")
        row, assumed = _clean_txn(txn)
        hist = _clean_history(history, row["sender_id"], row["receiver_id"])
        combined = pd.concat([hist, pd.DataFrame([row])], ignore_index=True)
        combined["timestamp"] = pd.to_datetime(combined["timestamp"])  # empty history -> object dtype otherwise
        combined["amount"] = combined["amount"].astype(float)
        feats = build_transaction_features(combined)
        r = feats[feats["transaction_id"] == "__new__"].iloc[0]
        score = float(self.predict_proba_frame(feats[feats["transaction_id"] == "__new__"])[0])
        # model-based reasons are only shown when there is something to explain (score >= threshold/2)
        signals = self._rule_signals(r) + (self._model_signals(r) if score >= self.threshold / 2 else [])
        meta = {"assumed_inputs": assumed, "history_rows_used": int(len(hist)),
                "history_available": bool(len(hist) > 0)}
        if self.kind != "logreg":
            meta["top_global_features"] = self.global_importance(5)
        return make_result(entity_id or txn.get("transaction_id") or "transaction", "transaction", score,
                           self.threshold, self.name, signals,
                           {"sender_id": row["sender_id"], "receiver_id": row["receiver_id"],
                            "amount": row["amount"], "timestamp": row["timestamp"].isoformat()},
                           row["timestamp"].isoformat(), meta)

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"kind": self.kind, "threshold": self.threshold, "seed": self.seed, "est": self.est}, path)

    @classmethod
    def load(cls, path: str | Path) -> "PaymentModel":
        d = joblib.load(path)
        m = cls(d["kind"], d["threshold"], d["seed"])
        m.est, m.fitted = d["est"], True
        return m
