"""Conversation-level statistics built from enriched messages (needs timestamps)."""
from __future__ import annotations

import numpy as np
import pandas as pd

KW_COLS = ["kw_investment", "kw_kyc_account", "kw_prize", "kw_job", "kw_secrecy", "kw_authority", "kw_trust"]


def build_conversation_features(msgs: pd.DataFrame, convs: pd.DataFrame) -> pd.DataFrame:
    m = msgs.sort_values(["conversation_id", "timestamp", "message_id"])
    label = convs.set_index("conversation_id").get("scam_label")
    rows = []
    for cid, g in m.groupby("conversation_id", sort=True):
        ts = g["timestamp"]
        n = len(g)
        dur = (ts.iloc[-1] - ts.iloc[0]).total_seconds() / 60
        gaps = ts.diff().dropna().dt.total_seconds() / 60
        initiator = g["sender_id"].iloc[0]
        n_init = int((g["sender_id"] == initiator).sum())
        pay_idx = np.flatnonzero(g["has_payment_request"].to_numpy())
        row = {
            "conversation_id": cid,
            "n_messages": n,
            "n_initiator_msgs": n_init,
            "n_responder_msgs": n - n_init,
            "initiator_share": n_init / n,
            "duration_minutes": dur,
            "messages_per_hour": n / (max(dur, 1.0) / 60),
            "mean_gap_minutes": gaps.mean() if len(gaps) else 0.0,
            "max_gap_minutes": gaps.max() if len(gaps) else 0.0,
            "n_payment_request_msgs": int(len(pay_idx)),
            "n_urgency_msgs": int(g["has_urgency"].sum()),
            "n_link_msgs": int(g["has_link"].sum()),
            "n_suspicious_link_msgs": int(g["suspicious_link"].sum()),
            "suspicious_kw_total": int(g["suspicious_kw_count"].sum()),
            "n_distinct_upi_ids": len({u for s in g["extracted_upi_ids"] for u in str(s).split("|") if u}),
            "has_payment_request": int(len(pay_idx) > 0),
        }
        for c in KW_COLS:
            row[c + "_total"] = int(g[c].sum())
        if len(pay_idx):
            i = int(pay_idx[0])
            row.update({
                "minutes_to_first_payment_request": (ts.iloc[i] - ts.iloc[0]).total_seconds() / 60,
                "msgs_before_first_payment_request": i,
                "first_payment_request_position": i / n,
                "payment_request_from_initiator": int(g["sender_id"].iloc[i] == initiator),
                "urgency_near_payment_request": int(g["has_urgency"].iloc[max(0, i - 1): i + 1].any()),
                "first_payment_request_ts": ts.iloc[i],
                "first_payment_request_upi": g["extracted_upi"].iloc[i],
                "first_payment_request_amount": g["extracted_amount"].iloc[i],
            })
        else:
            row.update({k: np.nan for k in [
                "minutes_to_first_payment_request", "msgs_before_first_payment_request",
                "first_payment_request_position", "payment_request_from_initiator",
                "urgency_near_payment_request", "first_payment_request_ts",
                "first_payment_request_upi", "first_payment_request_amount"]})
        row["conversation_text"] = " ".join(g["text_clean"])
        if label is not None:
            row["scam_label"] = label.get(cid, pd.NA)
        rows.append(row)
    return pd.DataFrame(rows)
