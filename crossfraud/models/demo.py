"""Prints example outputs of both models in the shared contract format."""
from __future__ import annotations

import json

import pandas as pd

from crossfraud.io import RAW_TABLES, dirs, load_tables, to_typed
from crossfraud.models.contract import InvalidInputError, validate_result
from crossfraud.models.training import load_messaging_model, load_payment_model

SCAM_CONVERSATION = [
    {"sender_id": "tg_s001", "timestamp": "2025-03-01 10:00:00", "message": "Dear customer, your KYC has expired and your account will be suspended."},
    {"sender_id": "tg_s001", "timestamp": "2025-03-01 10:20:00", "message": "I am from the bank support desk. This is your final warning."},
    {"sender_id": "tg_u0001", "timestamp": "2025-03-01 10:41:00", "message": "What should I do?"},
    {"sender_id": "tg_s001", "timestamp": "2025-03-01 11:05:00", "message": "Update your KYC here: http://kyc-verify-sbi.xyz/update"},
    {"sender_id": "tg_s001", "timestamp": "2025-03-01 11:30:00", "message": "You have only 30 minutes left."},
    {"sender_id": "tg_s001", "timestamp": "2025-03-01 11:45:00", "message": "Pay verification fee Rs 2000 on helpline81@ybl."},
]
NORMAL_CONVERSATION = [
    {"sender_id": "tg_u0002", "timestamp": "2025-03-01 18:00:00", "message": "Hey, did you finish the assignment?"},
    {"sender_id": "tg_u0003", "timestamp": "2025-03-01 18:05:00", "message": "Almost, will share the notes tonight"},
    {"sender_id": "tg_u0002", "timestamp": "2025-03-01 18:07:00", "message": "Great, let's meet for lunch tomorrow"},
]


def _show(title, obj):
    print(f"\n=== {title} ===")
    print(json.dumps(obj, indent=2, default=str))
    problems = validate_result(obj) if isinstance(obj, dict) and "contract_version" in obj else []
    print("contract check:", "OK" if not problems else problems)


def run_demo(data_dir: str = "data") -> None:
    d = dirs(data_dir)
    msg = load_messaging_model(data_dir)
    pay = load_payment_model(data_dir)
    _show("Messaging: suspicious conversation (template-style scam)", msg.predict(SCAM_CONVERSATION, "demo_scam"))
    _show("Messaging: normal conversation", msg.predict(NORMAL_CONVERSATION, "demo_normal"))
    _show("Messaging: scam written OUTSIDE the templates (known weak spot)",
          msg.predict("Hurry! Only 10 minutes left. Send Rs 4999 to quickcash77@ybl now and verify at "
                      "http://claim-bonus.xyz/pay", "demo_ood"))

    raw = to_typed(load_tables(d["raw"], RAW_TABLES))["transactions"]
    sender = raw.groupby("sender_id").size().idxmax()
    hist = raw[raw["sender_id"] == sender].sort_values("timestamp")
    usual_payee = hist["receiver_id"].value_counts().index[0]
    last = hist["timestamp"].max()
    normal = {"transaction_id": "demo_normal_txn", "sender_id": sender, "receiver_id": usual_payee,
              "timestamp": str((last + pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=14)),
              "amount": float(hist["amount"].median()), "transaction_type": "P2M", "beneficiary_type": "merchant"}
    suspicious = {"transaction_id": "demo_suspicious_txn", "sender_id": sender, "receiver_id": "quickcash77@ybl",
                  "timestamp": str((last + pd.Timedelta(days=1)).normalize() + pd.Timedelta(hours=3, minutes=12)),
                  "amount": 25000.0, "transaction_type": "P2P", "beneficiary_type": "individual"}
    print(f"\n(using sender {sender}, {len(hist)} earlier transactions as history, model={pay.name})")
    _show("Payment: normal transaction (usual payee, usual amount, daytime)", pay.predict(normal, raw))
    _show("Payment: suspicious transaction (new payee, 25,000, 03:12)", pay.predict(suspicious, raw))
    for title, bad in [("message list is empty", lambda: msg.predict([])),
                       ("message is not text", lambda: msg.predict([{"message": 123}])),
                       ("transaction missing amount", lambda: pay.predict({"sender_id": "a@ybl", "receiver_id": "b@ybl", "timestamp": "2025-03-01"})),
                       ("negative amount", lambda: pay.predict({**normal, "amount": -5}))]:
        try:
            bad()
        except InvalidInputError as e:
            print(f"\n=== Invalid input: {title} ===\nInvalidInputError: {e}")
