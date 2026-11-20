"""Controlled SYNTHETIC cross-platform data generator (Phase 1).

EVERYTHING produced here is synthetic. No real Telegram or banking data is used,
and every raw row carries data_source="synthetic".

Raw tables (pipeline inputs):  users, conversations, messages, transactions
Ground-truth tables (evaluation ONLY, never model features):
    scammers, conversation_truth, message_stages, transaction_truth, links
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from crossfraud.data.demographics import make_user_profiles

import pandas as pd

DATA_SOURCE = "synthetic"
BANKS = ["demobank", "examplebank", "testbank", "sandboxupi"]
FIRST = ["aarav", "diya", "rohan", "ananya", "kabir", "meera", "vihaan", "isha",
         "arjun", "sara", "neha", "rahul", "pooja", "karan", "tanvi"]
SURNAMES = ["sharma", "verma", "iyer", "khan", "patel", "reddy", "singh", "das"]
SCAM_PREFIX = ["support", "earn", "trade", "kycdesk", "prize", "helpline"]
SCAM_AMOUNTS = [150, 400, 499, 850, 999, 1200, 1500, 2000, 2500, 4999, 8000, 12000, 15000]
BENIGN_AMOUNTS = SCAM_AMOUNTS.copy()
RENT_AMOUNTS = [8000, 12000, 15000]
SCAM_LINKS = ["http://verify-account.invalid/update", "https://short.invalid/3xAb12",
              "http://prize-claim.invalid/win", "http://203.0.113.7/verify"]
BENIGN_LINKS = ["https://video.example/watch?v=abc123xyz", "https://docs.example/share/123"]
HOUR_WEIGHTS = [1, 1, 1, 1, 1, 1, 2, 3, 5, 6, 6, 6, 6, 6, 6, 6, 6, 7, 7, 8, 8, 7, 5, 3]
SMALLTALK = ["Hey, how are you?", "Did you finish the assignment?", "Let's meet for lunch tomorrow",
             "Saw the match last night, amazing", "Can you share the notes from class?",
             "Happy birthday! Have a great day", "Which movie should we watch this weekend?"]


def S(role, text, stage, p=1.0):
    """One scripted message: (role, text or [variants], lifecycle stage, inclusion prob)."""
    return (role, text, stage, p)


SCAM_SCENARIOS = {
    "task_job": [
        S("counterpart", ["Hi {name}, part-time job offer: earn Rs 3000 daily by liking videos.",
                          "Hello {name}! Work from home opportunity, earn Rs 5000 per day, no experience needed."], "contact"),
        S("user", ["Is this genuine?", "Who are you? How did you get my number?"], "victim_response"),
        S("counterpart", ["Yes, 100% genuine, thousands already earning. Join our group.",
                          "Trusted company, ask my other members. Daily payout guaranteed."], "grooming"),
        S("counterpart", "Register here to start: {link}", "grooming", 0.5),
        S("counterpart", "Complete a small prepaid task first and get your money back with commission.", "grooming"),
        S("user", ["ok what do I do", "How much is the task?"], "victim_response"),
        S("counterpart", ["Limited slots, only 10 minutes left!", "Hurry, slots are filling fast, last chance today."], "urgency", 0.6),
        S("counterpart", ["Pay Rs {amount} to {upi} now.", "Send Rs {amount} to {upi} to confirm your slot.",
                          "Transfer the task fee of Rs {amount} to {upi} immediately."], "payment_request"),
        S("user", ["ok sending", "paying now"], "victim_response", 0.7),
    ],
    "investment": [
        S("counterpart", ["Hello {name}, our trading expert guarantees 40% returns every week.",
                          "Hi {name}, invest with us and double your money in 30 days, risk free."], "contact"),
        S("counterpart", ["See these profit screenshots from our members, completely risk free.",
                          "Over 5000 investors trust us. Genuine returns guaranteed."], "grooming"),
        S("user", ["How do I start?", "Is it safe?"], "victim_response"),
        S("counterpart", "Open your trading account here: {link}", "grooming", 0.5),
        S("counterpart", "Our senior analyst will personally manage your account.", "grooming"),
        S("counterpart", ["Offer closes tonight!", "Only 3 slots left today, don't miss it."], "urgency", 0.6),
        S("counterpart", ["Deposit Rs {amount} to {upi} to activate your account.",
                          "Send Rs {amount} to {upi} as the initial deposit."], "payment_request"),
        S("user", ["done soon", "ok sending"], "victim_response", 0.7),
    ],
    "kyc_bank": [
        S("counterpart", ["Dear {name}, your bank account will be blocked today. Update KYC immediately.",
                          "Dear customer, your KYC has expired and your account will be suspended."], "contact"),
        S("counterpart", ["I am from the bank support desk. This is your final warning.",
                          "This is the official customer care. We want to help you avoid account closure."], "grooming"),
        S("user", ["What should I do?", "Which bank is this?"], "victim_response"),
        S("counterpart", "Update your KYC here: {link}", "grooming", 0.6),
        S("counterpart", "This is confidential, do not share this with anyone.", "grooming"),
        S("counterpart", ["You have only 30 minutes left.", "Act immediately to avoid permanent block."], "urgency", 0.7),
        S("counterpart", ["Pay verification fee Rs {amount} on {upi}.",
                          "Send Rs {amount} to {upi} as KYC verification charge."], "payment_request"),
        S("user", ["paying", "ok"], "victim_response", 0.7),
    ],
    "prize": [
        S("counterpart", ["Congratulations {name}! You won a lucky draw prize of Rs 50000.",
                          "Dear {name}, you have been selected for a lottery prize worth Rs 100000."], "contact"),
        S("user", ["Really?", "I never entered any draw"], "victim_response"),
        S("counterpart", ["Yes! To release the prize, a small processing fee is required.",
                          "Many winners have already received their money. It is 100% genuine."], "grooming"),
        S("counterpart", "Claim your prize here: {link}", "grooming", 0.5),
        S("counterpart", ["The prize expires in 15 minutes!", "Last chance, offer valid only today."], "urgency", 0.6),
        S("counterpart", ["Pay Rs {amount} to {upi} urgently to release the prize.",
                          "Send the processing fee Rs {amount} to {upi}."], "payment_request"),
        S("user", ["ok", "sending now"], "victim_response", 0.7),
    ],
}

# Short fictional sketches, with credential values never generated.
for scenario, introductions in {
    "support_impersonation": ["I am calling from customer support.", "Your refund ticket is still open."],
    "government_impersonation": ["I am following up about your certificate.", "This is about a pending service fee."],
    "family_impersonation": ["I changed my number. Can you help?", "Are you free? My usual phone stopped working."],
    "organization_impersonation": ["I handle payments for your office.", "There is an outstanding membership fee."],
    "credential_request": ["Your login needs a check.", "Can you share the OTP from the message?"],
    "delivery_fee": ["Your delivery is awaiting clearance.", "The parcel is held for a small customs fee."],
}.items():
    SCAM_SCENARIOS[scenario] = [
        S("counterpart", introductions, "contact"),
        S("user", ["Can you send details?", "What is this for?"], "victim_response"),
        S("counterpart", ["Please share the confirmation code.", "Can you share the OTP?", "What is your PIN?"], "grooming", 0.35),
        S("counterpart", "Please settle it today.", "grooming"),
        S("counterpart", ["Please send Rs {amount} to {upi}.", "The amount is Rs {amount}, UPI {upi}."],
          "payment_request"),
        S("user", "I will check first.", "victim_response", 0.45),
    ]

BENIGN_PAYMENT_CONTEXT = {
    "household_transfer": "This is for the household groceries.",
    "small_business": "Here is the balance from the stationery invoice.",
    "purchase": "Thanks for collecting your order.",
    "refund": "Can you return the duplicate payment?",
}
CODE_MIX = (" Haan, please check.", " Thoda time please.", " Theek hai.", " Please ನೋಡಿ.", " சரி, please check.")

URGENT_BENIGN = [
    [S("counterpart", "Urgent: team meeting moved to 5 pm, please confirm ASAP", "chat"),
     S("user", "ok will join", "chat"),
     S("counterpart", "Great, don't be late, it's important!", "chat")],
    [S("counterpart", "Please call me immediately, it's about tomorrow's exam", "chat"),
     S("user", "Calling now", "chat"),
     S("counterpart", "Thanks, the paper pattern changed, check the notice", "chat")],
    [S("counterpart", "Reminder: project report deadline is tonight, last chance to add your part", "chat"),
     S("user", "Almost done, sending in an hour", "chat"),
     S("counterpart", "Okay, hurry up please", "chat")],
]
LINK_BENIGN = [S("counterpart", "Check this out {link}", "chat"), S("user", "Nice, thanks!", "chat")]
P2P_SPLIT = [
    S("counterpart", "Hey {name}, dinner was fun yesterday", "chat"),
    S("user", "Yes! How much was my share?", "chat"),
    S("counterpart", ["Rs {amount} please, send it to {upi} whenever you can",
                      "Your share is Rs {amount}, UPI me at {upi}"], "payment_request"),
    S("user", "sending now", "chat"),
]
RENT = [
    S("counterpart", "Hi {name}, rent reminder: please send Rs {amount} to {upi} by tomorrow", "payment_request"),
    S("user", "Sure, I will pay it", "chat"),
]


@dataclass
class SynthConfig:
    seed: int = 42
    n_users: int = 300
    n_scammers: int = 15
    n_scam_convs: int = 300
    n_benign_convs: int = 450
    n_txn_only_fraud: int = 40
    scam_pay_rate: float = 0.6
    scam_collect_rate: float = 0.2
    p2p_pay_rate: float = 0.8
    obfuscation_rate: float = 0.25
    days: int = 60
    population_weights: dict[str, list[float]] = field(default_factory=dict)
    code_mix_rate: float = 0.30
    unsuccessful_rate: float = 0.12
    start: datetime = datetime(2025, 1, 1)


def _obfuscate(upi: str, rng: random.Random, rate: float) -> str:
    """Messages may write a UPI ID in noisy forms; raw IDs elsewhere stay canonical."""
    if rng.random() >= rate:
        return upi
    local, bank = upi.split("@")
    style = rng.choice(["upper", "spaced", "at_word"])
    if style == "upper":
        return upi.upper()
    if style == "spaced":
        return f"{local} @ {bank}"
    return f"{local} at {bank}"


def _name(rng):
    return f"{rng.choice(FIRST).title()} {rng.choice(SURNAMES).title()}"


def _make_users(cfg, rng):
    rows = []
    for i in range(cfg.n_users):
        f = rng.choice(FIRST)
        rows.append({"user_id": f"U{i:04d}", "telegram_id": f"tg_u{i:04d}",
                     "upi_id": f"{f}{i}@{rng.choice(BANKS)}",
                     "display_name": f"{f.title()} {rng.choice(SURNAMES).title()}",
                     "data_source": DATA_SOURCE})
    return pd.DataFrame(rows)


def _make_scammers(cfg, rng):
    rows = []
    for i in range(cfg.n_scammers):
        p = rng.choice(SCAM_PREFIX)
        for k in range(rng.randint(1, 2)):
            rows.append({"scammer_id": f"S{i:03d}", "telegram_id": f"tg_s{i:03d}",
                         "upi_id": f"{p}{i}.{k}@{rng.choice(BANKS)}", "display_name": _name(rng)})
    return pd.DataFrame(rows)


def _stage_text(spec, rng, ctx):
    role, text, stage, p = spec
    if rng.random() >= p:
        return None
    if isinstance(text, list):
        text = rng.choice(text)
    return role, text.format(**ctx), stage


def _delay_minutes(rng, median):
    return max(1, int(rng.lognormvariate(math.log(median), 0.9)))


def generate(cfg: SynthConfig | None = None):
    """Return (raw_tables, truth_tables) as dicts of DataFrames."""
    cfg = cfg or SynthConfig()
    if not 7 <= cfg.n_users <= 10000 or not 1 <= cfg.n_scammers <= 1000:
        raise ValueError("Require 7–10000 users and 1–1000 campaigns")
    if min(cfg.n_scam_convs, cfg.n_benign_convs) < 1 or cfg.n_txn_only_fraud < 0 or cfg.days < 6:
        raise ValueError("Require positive conversation counts, nonnegative unlinked fraud and at least six days")
    rates = (cfg.scam_pay_rate, cfg.scam_collect_rate, cfg.p2p_pay_rate,
             cfg.obfuscation_rate, cfg.code_mix_rate, cfg.unsuccessful_rate)
    if any(not 0 <= rate <= 1 for rate in rates):
        raise ValueError("Rates must lie between zero and one")
    rng = random.Random(cfg.seed)
    users, scammers = _make_users(cfg, rng), _make_scammers(cfg, rng)
    profiles = make_user_profiles(users, random.Random(cfg.seed + 9107), cfg.population_weights)
    presentation = random.Random(cfg.seed + 8431)
    urows, srows = users.to_dict("records"), scammers.to_dict("records")
    merchants = [{"upi_id": f"merchant{i}@demobank", "display_name": f"Merchant {i}"} for i in range(30)]

    payee_info = {}
    for r in urows + srows:
        payee_info[r["upi_id"]] = (r["display_name"], "individual")
    for m in merchants:
        payee_info[m["upi_id"]] = (m["display_name"], "merchant")

    habit = {}
    for u in urows:
        others = [x for x in urows if x["user_id"] != u["user_id"]]
        habit[u["upi_id"]] = {
            "contacts": [x["upi_id"] for x in rng.sample(others, rng.randint(3, 6))],
            "merchants": [m["upi_id"] for m in rng.sample(merchants, rng.randint(3, 6))],
            "median": rng.uniform(150, 700)}

    def rand_ts(lo_day=3, hi_day=None):
        hi_day = cfg.days - 3 if hi_day is None else hi_day
        hour = rng.choices(range(24), weights=HOUR_WEIGHTS)[0]
        return cfg.start + timedelta(days=rng.randint(lo_day, hi_day), hours=hour,
                                     minutes=rng.randint(0, 59), seconds=rng.randint(0, 59))

    convs, msgs, stages, ctruth, txns, links = [], [], [], [], [], []

    def add_txn(ts, payer, payee, amount, ttype, fraud, scenario):
        name, btype = payee_info[payee]
        status = "settled"
        if presentation.random() < cfg.unsuccessful_rate:
            status = presentation.choice(("failed", "reversed"))
        status_at_event = "failed" if status == "failed" else "accepted"
        txns.append({"_key": len(txns), "timestamp": ts, "sender_id": payer, "receiver_id": payee,
                     "amount": float(amount), "currency": "INR", "status_at_event": status_at_event,
                     "_outcome": status, "transaction_type": ttype,
                     "beneficiary_name": name, "beneficiary_type": btype,
                     "beneficiary_handle": payee.split("@")[1], "fraud_label": fraud,
                     "data_source": DATA_SOURCE, "_scenario": scenario})
        return len(txns) - 1

    def emit(label, scenario, user, other_tg, specs, ctx, instructed, written, amount):
        conv_id = f"C{len(convs):05d}"
        built = [b for b in (_stage_text(s, rng, ctx) for s in specs) if b]
        ts, pay_ts = rand_ts(), None
        start_ts = ts
        platform = presentation.choice(("telegram", "whatsapp"))
        for i, (role, text, stage) in enumerate(built):
            if i:
                ts += timedelta(minutes=rng.randint(1, 90), seconds=rng.randint(0, 59))
            sender = user["telegram_id"] if role == "user" else other_tg
            receiver = other_tg if role == "user" else user["telegram_id"]
            if presentation.random() < cfg.code_mix_rate:
                text += presentation.choice(CODE_MIX)
            mid = f"M{len(msgs):06d}"
            msgs.append({"message_id": mid, "conversation_id": conv_id, "sender_id": sender,
                         "receiver_id": receiver, "timestamp": ts, "message": text,
                         "message_type": "link_share" if "http" in text else "text",
                         "scam_label": label, "data_source": DATA_SOURCE})
            stages.append({"message_id": mid, "conversation_id": conv_id, "stage": stage})
            if stage == "payment_request":
                pay_ts = ts
        convs.append({"conversation_id": conv_id, "platform": platform,
                      "participant_a": user["telegram_id"], "participant_b": other_tg,
                      "start_ts": start_ts, "end_ts": ts, "scam_label": label,
                      "data_source": DATA_SOURCE})
        truth = {"conversation_id": conv_id, "scenario": scenario, "is_scam": label,
                 "instructed_upi": instructed, "upi_as_written": written,
                 "instructed_amount": amount, "paid": 0}
        ctruth.append(truth)
        return conv_id, pay_ts, truth

    kinds = ["scam"] * cfg.n_scam_convs + ["benign"] * cfg.n_benign_convs
    rng.shuffle(kinds)

    # Independent shuffled cycles cover every participant in both classes at default sizes.
    schedules = {}
    for kind, count in (("scam", cfg.n_scam_convs), ("benign", cfg.n_benign_convs)):
        order = urows.copy()
        presentation.shuffle(order)
        schedules[kind] = iter(order[i % len(order)] for i in range(count))
    for kind in kinds:
        user = next(schedules[kind])
        if kind == "scam":
            sc = rng.choice(srows)
            scenario = rng.choice(list(SCAM_SCENARIOS))
            amount = rng.choice(SCAM_AMOUNTS)
            written = _obfuscate(sc["upi_id"], rng, cfg.obfuscation_rate)
            ctx = {"name": user["display_name"].split()[0], "amount": amount, "upi": written,
                   "link": rng.choice(SCAM_LINKS)}
            cid, pay_ts, truth = emit(1, scenario, user, sc["telegram_id"],
                                      SCAM_SCENARIOS[scenario], ctx, sc["upi_id"], written, amount)
            if rng.random() < cfg.scam_pay_rate:
                paid = amount if rng.random() < 0.8 else int(amount * rng.uniform(0.3, 0.9))
                delay = _delay_minutes(rng, 20)
                ttype = "COLLECT" if rng.random() < cfg.scam_collect_rate else "P2P"
                k = add_txn(pay_ts + timedelta(minutes=delay), user["upi_id"], sc["upi_id"],
                            paid, ttype, 1, scenario)
                links.append({"conversation_id": cid, "_key": k, "link_type": "scam_payment",
                              "delay_minutes": delay})
                truth["paid"] = 1
            continue

        scenario = rng.choices(["smalltalk", "urgent_nonpayment", "benign_link", "p2p_split", "benign_rent",
                                *BENIGN_PAYMENT_CONTEXT], weights=[20, 10, 10, 14, 10, 9, 9, 9, 9])[0]
        friend = rng.choice([u for u in urows if u["user_id"] != user["user_id"]])
        name = user["display_name"].split()[0]
        if scenario == "smalltalk":
            specs = [S("counterpart" if j % 2 == 0 else "user", rng.choice(SMALLTALK), "chat")
                     for j in range(rng.randint(3, 7))]
            emit(0, scenario, user, friend["telegram_id"], specs, {}, None, None, None)
        elif scenario == "urgent_nonpayment":
            emit(0, scenario, user, friend["telegram_id"], rng.choice(URGENT_BENIGN), {}, None, None, None)
        elif scenario == "benign_link":
            emit(0, scenario, user, friend["telegram_id"], LINK_BENIGN,
                 {"link": rng.choice(BENIGN_LINKS)}, None, None, None)
        else:
            rent = scenario == "benign_rent"
            amount = rng.choice(RENT_AMOUNTS if rent else BENIGN_AMOUNTS)
            written = _obfuscate(friend["upi_id"], rng, cfg.obfuscation_rate)
            ctx = {"name": name, "amount": amount, "upi": written}
            cid, pay_ts, truth = emit(0, scenario, user, friend["telegram_id"],
                                      RENT if rent else [S("counterpart", BENIGN_PAYMENT_CONTEXT[scenario], "chat"),
                                                        *P2P_SPLIT] if scenario in BENIGN_PAYMENT_CONTEXT else P2P_SPLIT,
                                      ctx, friend["upi_id"], written, amount)
            if rng.random() < cfg.p2p_pay_rate:
                delay = _delay_minutes(rng, 10)
                t = pay_ts + timedelta(minutes=delay)
                ttype = "COLLECT" if rng.random() < 0.1 else "P2P"
                if rent:  # recurring rent: earlier payments to the same payee exist
                    for back in (30, 60):
                        add_txn(t - timedelta(days=back, hours=rng.randint(0, 5)), user["upi_id"],
                                friend["upi_id"], amount, "P2P", 0, "benign_rent_history")
                k = add_txn(t, user["upi_id"], friend["upi_id"], amount, ttype, 0,
                            "benign_rent" if rent else "benign_p2p")
                links.append({"conversation_id": cid, "_key": k, "link_type": "benign_p2p",
                              "delay_minutes": delay})
                truth["paid"] = 1

    for _ in range(cfg.n_txn_only_fraud):  # fraud with no visible conversation
        user, sc = rng.choice(urows), rng.choice(srows)
        add_txn(rand_ts(), user["upi_id"], sc["upi_id"], rng.choice(SCAM_AMOUNTS), "P2P", 1,
                "txn_only_fraud")

    for u in urows:  # background legitimate activity (history for Phase 3 features)
        h = habit[u["upi_id"]]
        for _ in range(rng.randint(15, 45)):
            if rng.random() < 0.88:
                use_merchant = rng.random() < 0.7
                payee = rng.choice(h["merchants"] if use_merchant else h["contacts"])
            else:
                use_merchant = rng.random() < 0.5
                payee = rng.choice(merchants)["upi_id"] if use_merchant else rng.choice(urows)["upi_id"]
            if payee == u["upi_id"]:
                continue
            factor = 1.0 if payee_info[payee][1] == "merchant" else 1.5
            amount = int(min(8000, max(10, rng.lognormvariate(math.log(h["median"] * factor), 0.7))))
            ttype = "P2M" if payee_info[payee][1] == "merchant" else ("COLLECT" if rng.random() < 0.05 else "P2P")
            add_txn(rand_ts(0, cfg.days), u["upi_id"], payee, amount, ttype, 0, "background")

    tdf = pd.DataFrame(txns).sort_values(["timestamp", "_key"], kind="stable").reset_index(drop=True)
    tdf.insert(0, "transaction_id", [f"T{i:06d}" for i in range(len(tdf))])
    key_to_id = dict(zip(tdf["_key"], tdf["transaction_id"]))
    txn_truth = tdf[["transaction_id", "_scenario", "_outcome", "fraud_label"]].rename(
        columns={"_scenario": "scenario", "_outcome": "outcome"})
    tdf = tdf.drop(columns=["_key", "_scenario", "_outcome", "fraud_label"])

    ldf = pd.DataFrame(links, columns=["conversation_id", "_key", "link_type", "delay_minutes"])
    ldf["transaction_id"] = ldf["_key"].map(key_to_id)
    ldf = ldf[["conversation_id", "transaction_id", "link_type", "delay_minutes"]]

    ldf["link_evidence"] = "simulated_request_to_attempt"
    conversations = pd.DataFrame(convs).drop(columns="scam_label")
    messages = pd.DataFrame(msgs).drop(columns="scam_label")
    conv_truth = pd.DataFrame(ctruth)
    conv_truth["campaign_id"] = conversations["participant_b"].where(
        conv_truth["is_scam"].eq(1), "__NOT_APPLICABLE__")
    conv_truth["attempt_outcome"] = [
        ("abandoned" if presentation.random() < 0.5 else "unpaid") if row.is_scam else "__NOT_APPLICABLE__"
        for row in conv_truth.itertuples()
    ]
    outcome_by_id = txn_truth.set_index("transaction_id")["outcome"]
    attempt_by_conv = ldf.set_index("conversation_id")["transaction_id"].map(outcome_by_id)
    linked = conv_truth["conversation_id"].map(attempt_by_conv)
    conv_truth["attempt_outcome"] = linked.fillna(conv_truth["attempt_outcome"])
    conv_truth["paid"] = conv_truth["attempt_outcome"].isin(["settled", "reversed"]).astype(int)
    for column in ("instructed_upi", "upi_as_written", "instructed_amount"):
        conv_truth[column] = conv_truth[column].fillna("__NOT_APPLICABLE__")
    raw = {"users": users, "conversations": conversations, "messages": messages, "transactions": tdf}
    truth = {"scammers": scammers, "conversation_truth": conv_truth, "message_stages": pd.DataFrame(stages),
             "transaction_truth": txn_truth, "links": ldf}
    for table in [*raw.values(), profiles, *truth.values()]:
        table["data_source"] = DATA_SOURCE
        table["source_version"] = "synthetic-v2"
    for table, binary in ((conv_truth, "is_scam"), (txn_truth, "fraud_label")):
        table["label_status"] = table[binary].map({1: "confirmed", 0: "legitimate"})
    for table in truth.values():
        table["label_source"] = "simulation"
        table["label_confidence"] = 1.0
    return {**raw, "user_profiles": profiles}, truth
