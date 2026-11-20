"""Aligned, held-out replay of messaging, payment and correlated review signals."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer

from crossfraud.io import dirs
from crossfraud.models.correlation import MatchConfig, build_requests, make_alert, match_payment
from crossfraud.models.messaging import CONTENT_COLS, TEXT_COL, MessagingModel
from crossfraud.models.metrics import binary_metrics
from crossfraud.models.payment import PAYMENT_FEATURES, PaymentModel
from crossfraud.models.phase2 import HELD_SCENARIOS, _group_order, _read, choose_threshold, prepare

VERSION = "phase3-v1"
METHODS = ("messaging_only", "payment_only", "rule_matching", "combined")
MSG_COLS = [TEXT_COL, *CONTENT_COLS]


def common_partitions(messaging, payment, seed):
    users = _group_order(pd.concat([messaging["user_id"], payment["user_id"]]), seed)
    i, j = int(0.60 * len(users)), int(0.80 * len(users))
    groups = [set(users[:i]), set(users[i:j]), set(users[j:])]
    instants = payment["event_time"].sort_values().reset_index(drop=True)
    first, second = instants.iloc[[int(0.55 * len(instants)), int(0.75 * len(instants))]]
    campaigns = messaging.loc[messaging["campaign_id"].ne("__NOT_APPLICABLE__"), "campaign_id"]
    withheld = _group_order(campaigns, seed + 1)[:len(campaigns.unique()) // 3]
    paired = []
    for frame in (messaging, payment):
        time = frame["event_time"]
        periods = [time.lt(first), time.ge(first) & time.lt(second), time.ge(second)]
        held = frame["campaign_id"].isin(withheld) | frame["scenario"].isin(HELD_SCENARIOS)
        paired.append([frame.loc[period & frame["user_id"].isin(group) & (~held if k < 2 else True)].copy()
                       for k, (period, group) in enumerate(zip(periods, groups))])
    msg, pay = paired
    vectorizer = HashingVectorizer(analyzer="char", ngram_range=(3, 5), n_features=2**18,
                                   alternate_sign=False)
    purged = []
    for k in (1, 2):
        preceding = pd.concat(msg[:k])[TEXT_COL]
        query = msg[k][TEXT_COL]
        similarity = (vectorizer.transform(query) @ vectorizer.transform(preceding).T).toarray()
        overlaps = query.isin(preceding).to_numpy() | (similarity.max(axis=1) >= 0.95)
        purged.append(int(overlaps.sum()))
        msg[k] = msg[k].loc[~overlaps].copy()
    for parts in paired:
        if any(part["target"].nunique() < 2 for part in parts):
            raise ValueError("Phase 3 replay requires both classes in every partition; use the default dataset")
    return list(zip(*paired)), {"boundaries_utc": [x.tz_convert("UTC").isoformat() for x in (first, second)],
                                 "withheld_campaigns": withheld, "withheld_scenarios": sorted(HELD_SCENARIOS),
                                 "near_duplicate_messaging_exclusions": purged,
                                 "partition_focal_users": [len(group) for group in groups]}


def reference_rank(scores, training_reference):
    """Map modality scores to separate empirical training percentiles, not probabilities."""
    ranked = np.sort(training_reference)
    positions = np.searchsorted(ranked, scores, side="left")
    return (positions + 1) / (len(ranked) + 2)


def exact_link_baseline(match):
    candidates = [candidate for candidate in match["candidates"]
                  if candidate["identifier_evidence"] in {"exact", "normalized_exact"}
                  and {"payer mapping agrees", "amount within tolerance"} <= set(candidate["support"])]
    status = "matched" if len(candidates) == 1 else ("ambiguous" if candidates else "no_match")
    return {"status": status, "reason": "unique exact address, payer and amount rule",
            "selected": candidates[0] if status == "matched" else None, "candidates": candidates}


def replay(messaging, payments, requests, models, refs, config):
    msg_model, pay_model = models
    msg_raw = msg_model.predict_proba_frame(messaging[MSG_COLS])
    pay_raw = pay_model.predict_proba_frame(payments[PAYMENT_FEATURES])
    m_rank = reference_rank(msg_raw, refs[0])
    p_rank = reference_rank(pay_raw, refs[1])
    prior = {}
    events = {key: [] for key in METHODS}
    for row, raw, rank in zip(messaging.itertuples(), msg_raw, m_rank):
        prior[row.conversation_id] = row.event_time, float(raw), float(rank)
        evidence = {"conversation_score": float(raw),
                    "conversation_observed_at_utc": row.event_time.tz_convert("UTC").isoformat(),
                    "message_count": row.n_messages,
                    "urgency_messages": row.n_urgency_msgs,
                    "credential_request_messages": row.n_credential_request_msgs,
                    "suspicious_link_messages": row.n_suspicious_link_msgs,
                    "payment_request_messages": row.n_payment_request_msgs,
                    "signals": ["observable conversation prefix"]}
        event = (row.conversation_id, row.event_time, float(rank), evidence)
        events["messaging_only"].append(event)
        events["combined"].append(event)

    matches, baseline_matches = {}, {}
    eligible_requests = requests[requests["conversation_id"].isin(messaging["conversation_id"])]
    for row, raw, rank in zip(payments.itertuples(), pay_raw, p_rank):
        attempt = {"timestamp": row.event_time, "receiver_id": row.receiver_id, "amount": row.amount}
        match = match_payment(attempt, eligible_requests, row.event_time, row.telegram_id, config)
        matches[row.transaction_id] = match
        baseline = exact_link_baseline(match)
        baseline_matches[row.transaction_id] = baseline
        selected = match["selected"]
        evidence = {"payment_score": float(raw), "payment_type": row.transaction_type,
                    "amount_inr": row.amount, "new_beneficiary": bool(row.is_new_beneficiary),
                    "prior_sender_attempts": int(row.sender_prior_txn_count),
                    "attempts_last_hour": int(row.txn_count_1h), "match": match,
                    "combined_basis": "payment percentile"}
        combined = float(rank)
        if selected:
            seen, msg_score, msg_rank = prior[selected["conversation_id"]]
            if seen <= row.event_time:
                # Bounded corroboration. A strong rank on only one side cannot supply the bonus alone.
                bonus = 0.08 * min(float(rank), msg_rank) * selected["confidence"]
                combined = min(1.0, max(float(rank), msg_rank) + bonus)
                evidence.update({"conversation_score": msg_score,
                                 "conversation_observed_at_utc": seen.tz_convert("UTC").isoformat(),
                                 "combined_basis": "maximum modality rank plus corroboration bonus",
                                 "corroboration_bonus": bonus})
        events["payment_only"].append((row.transaction_id, row.event_time, float(rank), {"payment_score": float(raw)}))
        events["rule_matching"].append((row.transaction_id, row.event_time, float(bool(baseline["selected"])), {"match": baseline}))
        events["combined"].append((row.transaction_id, row.event_time, combined, evidence))
    return events, matches, baseline_matches


def group_cases(messaging, payments, links):
    """Use reference links after replay to map alerts onto common evaluation cases."""
    msg_ids, txn_ids = set(messaging["conversation_id"]), set(payments["transaction_id"])
    internal = links[links["conversation_id"].isin(msg_ids) & links["transaction_id"].isin(txn_ids)]
    mapping = internal.set_index("transaction_id")["conversation_id"].to_dict()
    cases = {}
    for row in messaging.itertuples():
        cases[row.conversation_id] = {"target": int(row.target), "first_attempt": None,
                                      "cohort": "conversation_only"}
    linked_globally = set(links["transaction_id"])
    for row in payments.itertuples():
        key = mapping.get(row.transaction_id, row.transaction_id)
        existing = cases.setdefault(key, {"target": int(row.target), "first_attempt": None,
                                          "cohort": "linked_conversation_outside_cohort"
                                          if row.transaction_id in linked_globally else ("fraud_without_visible_chat" if row.scenario == "txn_only_fraud"
                                                else "payment_without_truth_link")})
        existing["target"] = max(existing["target"], int(row.target))
        if key != row.transaction_id:
            existing["cohort"] = "linked_pair_in_cohort"
        first = existing["first_attempt"]
        existing["first_attempt"] = min(first, row.event_time) if first is not None else row.event_time
    return cases, mapping


def case_events(cases, mapping, events):
    result = {key: [] for key in cases}
    for entity, instant, score, evidence in events:
        result[mapping.get(entity, entity)].append((instant, score))
    return result


def case_metrics(cases, events, threshold):
    targets, scores, leads = [], [], []
    linked_fraud = 0
    results_by_cohort = {}
    for key, case in cases.items():
        history = events[key]
        score = max((score for _, score in history), default=0.0)
        targets.append(case["target"])
        scores.append(score)
        flags = [instant for instant, value in history if value >= threshold]
        cohort = results_by_cohort.setdefault(case["cohort"], {"cases": 0, "fraud": 0,
                                                               "detected_fraud": 0, "false_alerts": 0})
        cohort["cases"] += 1
        cohort["fraud"] += case["target"]
        cohort["detected_fraud"] += bool(flags) and case["target"]
        cohort["false_alerts"] += bool(flags) and not case["target"]
        if case["target"] and case["cohort"] == "linked_pair_in_cohort":
            linked_fraud += 1
            if flags and min(flags) < case["first_attempt"]:
                leads.append((case["first_attempt"] - min(flags)).total_seconds() / 60)
    stats = binary_metrics(targets, scores, threshold)
    stats["false_alerts_per_1000_cases"] = 1000 * stats["confusion_matrix"]["fp"] / len(cases)
    stats["by_cohort"] = results_by_cohort
    stats["early_warning"] = {"linked_fraud_cases": linked_fraud, "warned_before_attempt": len(leads),
                              "coverage": len(leads) / linked_fraud if linked_fraud else None,
                              "lead_time_minutes": sorted(leads),
                              "median_lead_minutes": float(np.median(leads)) if leads else None}
    return stats


def link_metrics(matches, links, cohort_conversations, config):
    truth = links.set_index("transaction_id")["conversation_id"].to_dict()
    visible = set(cohort_conversations)
    internal = {key: truth[key] for key in matches if key in truth and truth[key] in visible}
    chosen = {key: value["selected"]["conversation_id"] for key, value in matches.items() if value["selected"]}
    tp = sum(internal.get(key) == value for key, value in chosen.items())
    precision = tp / len(chosen) if chosen else 0.0
    recall = tp / len(internal) if internal else 0.0
    return {"attempts": len(matches), "reference_links_in_cohort": len(internal),
            "links_with_chat_outside_cohort": sum(key in truth and key not in internal for key in matches),
            "selected": len(chosen), "true_links": tp, "false_links": len(chosen) - tp,
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
            "ambiguous": sum(value["status"] == "ambiguous" for value in matches.values()),
            "no_match": sum(value["status"] == "no_match" for value in matches.values()),
            "known_link_beyond_window": int((links.loc[links["transaction_id"].isin(internal),
                                                        "delay_minutes"] > config.window_minutes).sum()),
            "top3_candidate_recall": (sum(any(candidate["conversation_id"] == cid for candidate in
                                               matches[txn]["candidates"][:3])
                                          for txn, cid in internal.items()) / len(internal)) if internal else None}


def _flagged(mapping, events, threshold):
    return {mapping.get(entity, entity) for entity, _, score, _ in events if score >= threshold}


def run(data_dir, seed, config=MatchConfig(), use_cleaned=False):
    data = prepare(data_dir, use_cleaned)
    messaging, payment = data["messaging"][0], data["payment"][0]
    d = dirs(data_dir)
    users = _read(d["cleaned"], "users")[["user_id", "telegram_id"]]
    payment = payment.merge(users, on="user_id", validate="many_to_one")
    links = _read(d["truth"], "links")
    messages = _read(d["cleaned"], "messages")
    conversations = _read(d["cleaned"], "conversations")
    requests = build_requests(messages, conversations)
    (train, validation, test), split = common_partitions(messaging, payment, seed)
    model_m = MessagingModel("combined", seed=seed).fit(train[0][MSG_COLS], train[0]["target"])
    model_p = PaymentModel("logreg", seed=seed).fit(train[1][PAYMENT_FEATURES], train[1]["target"])
    models = (model_m, model_p)
    refs = (model_m.predict_proba_frame(train[0][MSG_COLS]), model_p.predict_proba_frame(train[1][PAYMENT_FEATURES]))
    val_events, _, _ = replay(*validation, requests, models, refs, config)
    test_events, matches, baseline_matches = replay(*test, requests, models, refs, config)
    val_cases, val_map = group_cases(*validation, links)
    test_cases, test_map = group_cases(*test, links)
    metrics, alerts = {}, []
    for method in METHODS:
        val_by_case = case_events(val_cases, val_map, val_events[method])
        val_max = np.array([max((score for _, score in history), default=0.0) for history in val_by_case.values()])
        threshold = 0.5 if method == "rule_matching" else choose_threshold(
            [case["target"] for case in val_cases.values()], val_max)
        metrics[method] = {
            "validation": case_metrics(val_cases, val_by_case, threshold),
            "test": case_metrics(test_cases, case_events(test_cases, test_map, test_events[method]), threshold),
        }
        if method in {"combined", "messaging_only"}:
            for entity, time, score, evidence in sorted(test_events[method], key=lambda event: event[1]):
                if score >= threshold:
                    kind = "messaging_warning" if entity.startswith("C") else "payment_time_review"
                    alerts.append(make_alert(kind, time, score, threshold, entity, evidence,
                                             {"replay": VERSION, "messaging": model_m.name, "payment": model_p.name}))
                    alerts[-1]["detector"] = method
    baseline_flags = _flagged(test_map, test_events["payment_only"],
                              metrics["payment_only"]["test"]["threshold"])
    combined_flags = _flagged(test_map, test_events["combined"],
                              metrics["combined"]["test"]["threshold"])
    def class_counts(flagged):
        fraud = sum(test_cases[key]["target"] for key in flagged)
        return {"fraud_cases": fraud, "legitimate_cases": len(flagged) - fraud}

    report = {"version": VERSION, "seed": seed, "source": "synthetic", "split": split,
              "partitions": {name: {"conversations": len(a), "payments": len(b),
                                    "fraud_conversations": int(a["target"].sum()),
                                    "fraud_payments": int(b["target"].sum())}
                             for name, (a, b) in zip(("train", "validation", "test"), (train, validation, test))},
              "config": vars(config), "matching": link_metrics(matches, links, test[0]["conversation_id"], config),
              "exact_rule_link_metrics": link_metrics(baseline_matches, links, test[0]["conversation_id"], config),
              "combined_vs_payment": {"only_combined_alerted": class_counts(combined_flags - baseline_flags),
                                      "only_payment_alerted": class_counts(baseline_flags - combined_flags),
                                      "both_alerted": class_counts(combined_flags & baseline_flags)},
              "methods": metrics, "combined_alert_events": sum(a["detector"] == "combined" for a in alerts),
              "dataset_configuration": json.loads((Path(data_dir) / "dataset_manifest.json").read_text())}
    (d["reports"] / "phase3_evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (d["reports"] / "phase3_alert_examples.json").write_text(json.dumps(alerts[:20], indent=2, allow_nan=False), encoding="utf-8")
    return report
