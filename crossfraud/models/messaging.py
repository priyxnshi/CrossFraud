"""Phase 2 / Part A: interpretable messaging fraud model.

Pipeline: Phase 1 message features -> conversation features -> extra Phase 2 indicators
          -> [TF-IDF on cleaned text  +  scaled structured indicators] -> Logistic Regression.

Three variants exist so the contribution of each part can be measured honestly:
  text_only, structured_only, combined (the shipped default).
"""
from __future__ import annotations

import re
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy import sparse
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from crossfraud.features.conversation_features import build_conversation_features
from crossfraud.features.text_features import enrich_messages
from crossfraud.models.contract import InvalidInputError, make_result, signal

VARIANTS = ("text_only", "structured_only", "combined", "combined_with_timing")

# ---- credential / sensitive-information requests (new in Phase 2) -----------------------------
_CRED_TERMS = re.compile(
    r"\b(otp|cvv|upi[- ]?pin|atm[- ]?pin|password|passcode|card (?:number|details)|aadhaar|aadhar|"
    r"pan (?:number|card)|net ?banking (?:id|password|details))\b", re.I)
_REQUEST_VERB = re.compile(r"\b(share|send|tell|give|provide|enter|confirm|verify|read out|forward)\b", re.I)
_WARNING = re.compile(r"\b(never|do not|don'?t|dont)\s+(share|tell|give|send|disclose)\b", re.I)


def is_credential_request(text: str) -> bool:
    """True if a message asks for a credential (OTP, PIN, password...) and is not a warning."""
    text = text or ""
    return bool(_CRED_TERMS.search(text) and _REQUEST_VERB.search(text) and not _WARNING.search(text))


# Content indicators: what the messages SAY (payment asks, urgency, links, scam themes, credentials).
CONTENT_COLS = [
    "n_payment_request_msgs", "n_urgency_msgs", "n_link_msgs", "n_suspicious_link_msgs",
    "suspicious_kw_total", "n_distinct_upi_ids", "urgency_near_payment_request",
    "first_payment_request_amount_log", "kw_investment_total", "kw_kyc_account_total",
    "kw_prize_total", "kw_job_total", "kw_secrecy_total", "kw_authority_total", "kw_trust_total",
    "n_credential_request_msgs", "n_persuasion_msgs",
]
# Structure/timing statistics: HOW the chat is shaped. In the simulation these mostly reflect how the
# generator scripts each scenario (chat length, who talks, where the request sits), so they are kept
# out of the default model and evaluated only as the `combined_with_timing` ablation.
TIMING_COLS = [
    "n_messages", "initiator_share", "duration_minutes", "messages_per_hour", "mean_gap_minutes",
    "max_gap_minutes", "minutes_to_first_payment_request", "msgs_before_first_payment_request",
    "first_payment_request_position", "persuasion_share", "max_consecutive_initiator_msgs",
]
STRUCT_COLS = CONTENT_COLS                      # default structured inputs
ALL_STRUCT_COLS = CONTENT_COLS + TIMING_COLS    # used by the ablation and to fill the frame
TEXT_COL = "conversation_text"
THEMES = {"kw_investment_total": "investment", "kw_kyc_account_total": "kyc/account",
          "kw_prize_total": "prize", "kw_job_total": "job", "kw_secrecy_total": "secrecy",
          "kw_authority_total": "authority", "kw_trust_total": "trust"}


def build_extra_features(msgs: pd.DataFrame) -> pd.DataFrame:
    """Phase 2 conversation indicators computed from Phase 1 enriched messages."""
    m = msgs.sort_values(["conversation_id", "timestamp", "message_id"])
    cred = m["message"].fillna("").map(is_credential_request).astype(int)
    persuasion = (((m["has_urgency"] == 1) | (m["kw_trust"] > 0) | (m["kw_secrecy"] > 0) |
                   (m["kw_authority"] > 0)) | (cred == 1)).astype(int)
    m = m.assign(_cred=cred, _pers=persuasion)
    rows = []
    for cid, g in m.groupby("conversation_id", sort=True):
        senders = g["sender_id"].to_numpy()
        initiator, run, best = senders[0], 0, 0
        for s in senders:  # longest one-sided run by whoever opened the chat
            run = run + 1 if s == initiator else 0
            best = max(best, run)
        n_pers = int(g["_pers"].sum())
        rows.append({"conversation_id": cid, "n_credential_request_msgs": int(g["_cred"].sum()),
                     "n_persuasion_msgs": n_pers, "persuasion_share": n_pers / len(g),
                     "max_consecutive_initiator_msgs": best})
    return pd.DataFrame(rows)


def build_model_frame(msgs_enriched: pd.DataFrame, convs: pd.DataFrame) -> pd.DataFrame:
    """One row per conversation with every model input column filled (NaN -> 0)."""
    cf = build_conversation_features(msgs_enriched, convs)
    f = cf.merge(build_extra_features(msgs_enriched), on="conversation_id", how="left")
    f["first_payment_request_amount_log"] = np.log1p(
        pd.to_numeric(f["first_payment_request_amount"], errors="coerce").fillna(0.0))
    for c in ALL_STRUCT_COLS:
        f[c] = pd.to_numeric(f[c], errors="coerce").fillna(0.0)
    return f


def build_messaging_frame(raw_typed: dict, truth_dir: str | Path | None = None) -> pd.DataFrame:
    """Training frame from typed Phase 1 raw tables. `scenario` (ground truth) is attached ONLY for
    splitting/reporting and is never a model input."""
    frame = build_model_frame(enrich_messages(raw_typed["messages"]), raw_typed["conversations"])
    if truth_dir is not None:
        truth = pd.read_csv(Path(truth_dir) / "conversation_truth.csv", dtype=str)
        frame = frame.merge(truth[["conversation_id", "scenario"]], on="conversation_id", how="left")
    return frame


def make_pipeline(variant: str = "combined", C: float = 1.0, seed: int = 42) -> Pipeline:
    if variant not in VARIANTS:
        raise ValueError(f"variant must be one of {VARIANTS}")
    parts = []
    if variant in ("text_only", "combined", "combined_with_timing"):
        parts.append(("text", TfidfVectorizer(ngram_range=(1, 2), min_df=2, sublinear_tf=True), TEXT_COL))
    if variant in ("structured_only", "combined"):
        parts.append(("struct", StandardScaler(), CONTENT_COLS))
    if variant == "combined_with_timing":
        parts.append(("struct", StandardScaler(), ALL_STRUCT_COLS))
    # class_weight="balanced": scam conversations are the minority class (25% in the simulation)
    return Pipeline([("prep", ColumnTransformer(parts)),
                     ("clf", LogisticRegression(C=C, class_weight="balanced", max_iter=2000,
                                                random_state=seed))])


# ---- input validation / conversion for inference ------------------------------------------------
def _conversation_to_frame(conversation, entity_id: str):
    """Turn a str or a list of message dicts into a Phase 1 style messages DataFrame."""
    assumed = []
    if isinstance(conversation, str):
        conversation = [{"message": conversation}]
    if not isinstance(conversation, (list, tuple)) or len(conversation) == 0:
        raise InvalidInputError("conversation must be a non-empty string or list of message dicts")
    for i, m in enumerate(conversation):
        if not isinstance(m, dict):
            raise InvalidInputError(f"message {i} must be a dict")
        txt = m.get("message")
        if not isinstance(txt, str) or not txt.strip():
            raise InvalidInputError(f"message {i}: 'message' must be a non-empty string")
    has_ts = [m.get("timestamp") is not None for m in conversation]
    has_sender = [m.get("sender_id") not in (None, "") for m in conversation]
    if any(has_ts) and not all(has_ts):
        raise InvalidInputError("either all messages or none must have a timestamp")
    if any(has_sender) and not all(has_sender):
        raise InvalidInputError("either all messages or none must have a sender_id")
    if all(has_ts):
        ts = pd.to_datetime([m["timestamp"] for m in conversation], errors="coerce", format="mixed")
        if pd.isna(ts).any():
            raise InvalidInputError("invalid timestamp in conversation")
    else:
        ts = pd.Timestamp("2025-01-01") + pd.to_timedelta(range(len(conversation)), unit="min")
        assumed.append("timestamps (1 minute apart)")
    if all(has_sender):
        senders = [str(m["sender_id"]) for m in conversation]
    else:
        senders = ["party_a" if i % 2 == 0 else "party_b" for i in range(len(conversation))]
        assumed.append("sender_id (alternating)")
    df = pd.DataFrame({"conversation_id": entity_id, "sender_id": senders,
                       "timestamp": pd.to_datetime(ts), "message": [m["message"] for m in conversation]})
    df = df.sort_values("timestamp", kind="stable").reset_index(drop=True)
    df["message_id"] = [f"M{i:06d}" for i in range(len(df))]
    other = {"party_a": "party_b", "party_b": "party_a"}
    uniq = list(dict.fromkeys(df["sender_id"]))
    df["receiver_id"] = [other.get(s, next((u for u in uniq if u != s), s)) for s in df["sender_id"]]
    df["message_type"] = np.where(df["message"].str.contains("http", case=False), "link_share", "text")
    return df, assumed


class MessagingModel:
    VERSION = "v1"

    def __init__(self, variant: str = "combined", threshold: float = 0.5, C: float = 1.0, seed: int = 42):
        self.variant, self.threshold, self.C, self.seed = variant, threshold, C, seed
        self.pipe = make_pipeline(variant, C, seed)
        self.fitted = False

    @property
    def name(self) -> str:
        return f"messaging_{self.variant}_logreg_{self.VERSION}"

    def fit(self, frame: pd.DataFrame, y) -> "MessagingModel":
        self.pipe.fit(frame, np.asarray(y).astype(int))
        self.fitted = True
        return self

    def predict_proba_frame(self, frame: pd.DataFrame) -> np.ndarray:
        return self.pipe.predict_proba(frame)[:, 1]

    # ---- explanations -------------------------------------------------------------------------
    def top_features(self, k: int = 15) -> dict:
        names = self.pipe.named_steps["prep"].get_feature_names_out()
        coef = self.pipe.named_steps["clf"].coef_[0]
        order = np.argsort(coef)
        pick = lambda idx: [{"feature": str(names[i]), "coefficient": round(float(coef[i]), 4)} for i in idx]
        return {"fraud_indicators": pick(order[::-1][:k]), "legitimate_indicators": pick(order[:k])}

    def _model_signals(self, row: pd.DataFrame, top_k: int = 5, min_weight: float = 0.05) -> list:
        prep, clf = self.pipe.named_steps["prep"], self.pipe.named_steps["clf"]
        xt = prep.transform(row)
        x = xt.toarray()[0] if sparse.issparse(xt) else np.asarray(xt)[0]
        contrib = x * clf.coef_[0]
        names = prep.get_feature_names_out()
        out = []
        for i in np.argsort(-contrib)[:top_k]:
            if contrib[i] < min_weight:  # drop negligible contributions (noise like 'the')
                break
            n = str(names[i])
            if n.startswith("text__"):
                detail = f'phrase "{n[6:]}"'
            else:
                col = n[len("struct__"):]
                detail = f"{col}={row.iloc[0][col]:g}"
            out.append(signal(f"model:{n}", "model", detail, contrib[i]))
        return out

    @staticmethod
    def _rule_signals(r: pd.Series, msgs: pd.DataFrame) -> list:
        sig = []
        if r["n_payment_request_msgs"] > 0:
            amt = r["first_payment_request_amount"]
            sig.append(signal("payment_request", "rule",
                              f"upi={r['first_payment_request_upi'] or 'n/a'}, "
                              f"amount={'n/a' if pd.isna(amt) else f'{amt:g}'}"))
        if r["n_urgency_msgs"] > 0:
            sig.append(signal("urgency", "rule", f"{int(r['n_urgency_msgs'])} urgent message(s)"))
        if r["n_suspicious_link_msgs"] > 0:
            flags = sorted({f for s in msgs["link_risk_flags"].fillna("") for f in s.split("|") if f})
            sig.append(signal("suspicious_link", "rule", ", ".join(flags)))
        if r["n_credential_request_msgs"] > 0:
            sig.append(signal("credential_request", "rule", "asks for OTP/PIN/password/card details"))
        if r["n_persuasion_msgs"] >= 2:
            sig.append(signal("repeated_persuasion", "rule",
                              f"{int(r['n_persuasion_msgs'])} persuasion/pressure messages"))
        themes = [lbl for col, lbl in THEMES.items() if r[col] > 0]
        if themes:
            sig.append(signal("scam_language", "rule", ", ".join(themes)))
        return sig

    # ---- inference ----------------------------------------------------------------------------
    def predict(self, conversation, entity_id: str = "conversation") -> dict:
        """conversation: a str, or a list of {"message", optional "sender_id", optional "timestamp"}."""
        if not self.fitted:
            raise RuntimeError("model is not fitted")
        df, assumed = _conversation_to_frame(conversation, str(entity_id))
        msgs = enrich_messages(df)
        convs = pd.DataFrame({"conversation_id": [str(entity_id)], "scam_label": [pd.NA]})
        frame = build_model_frame(msgs, convs)
        score = float(self.predict_proba_frame(frame)[0])
        r = frame.iloc[0]
        upis = sorted({u for s in msgs["extracted_upi_ids"].fillna("") for u in s.split("|") if u})
        assumed_ts = any(a.startswith("timestamps") for a in assumed)
        req_ts = pd.NaT if assumed_ts else r["first_payment_request_ts"]  # never report invented times
        evidence = {"upi_ids": upis,
                    "payment_request_amount": None if pd.isna(r["first_payment_request_amount"])
                    else float(r["first_payment_request_amount"]),
                    "payment_request_ts": None if pd.isna(req_ts) else pd.Timestamp(req_ts).isoformat(),
                    "n_messages": int(r["n_messages"])}
        # model-based reasons are only shown when there is something to explain (score >= threshold/2)
        model_sigs = self._model_signals(frame) if score >= self.threshold / 2 else []
        return make_result(entity_id, "conversation", score, self.threshold, self.name,
                           self._rule_signals(r, msgs) + model_sigs,
                           evidence, None if assumed_ts else msgs["timestamp"].max().isoformat(),
                           {"assumed_inputs": assumed})

    # ---- persistence --------------------------------------------------------------------------
    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"variant": self.variant, "threshold": self.threshold, "C": self.C,
                     "seed": self.seed, "pipe": self.pipe}, path)

    @classmethod
    def load(cls, path: str | Path) -> "MessagingModel":
        d = joblib.load(path)
        m = cls(d["variant"], d["threshold"], d["C"], d["seed"])
        m.pipe, m.fitted = d["pipe"], True
        return m
