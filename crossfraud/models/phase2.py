"""Reproducible Phase 2 evaluation for the versioned synthetic dataset."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import HashingVectorizer

from crossfraud.data.ingestion import ingest, normalized_id, verify_cleaned
from crossfraud.features.transaction_features import build_transaction_features
from crossfraud.io import dirs, write_tables
from crossfraud.models.messaging import CONTENT_COLS, TEXT_COL, MessagingModel
from crossfraud.models.metrics import binary_metrics
from crossfraud.models.payment import KINDS, PAYMENT_FEATURES, PaymentModel
from crossfraud.models.phase2_features import conversation_prefixes, observation_times
from crossfraud.models.probes import run_probes

VERSION = "phase2-v2"
PROFILE_FIELDS = ("state_ut", "region", "settlement_type", "age_band", "primary_language",
                  "secondary_language", "education_band", "occupation_sector",
                  "monthly_household_income_band_inr", "smartphone_access", "internet_access",
                  "upi_experience_band")
HELD_SCENARIOS = {"family_impersonation", "delivery_fee", "refund", "urgent_nonpayment"}


def _read(directory, name):
    return pd.read_csv(directory / f"{name}.csv", keep_default_na=False)


def prepare(data_dir, use_cleaned=False):
    if use_cleaned:
        verify_cleaned(data_dir)
    else:
        report = ingest(data_dir)
        if not report.ok:
            raise ValueError(report.summary())
    d = dirs(data_dir)
    messages = _read(d["cleaned"], "messages")
    conversations = _read(d["cleaned"], "conversations")
    users = _read(d["cleaned"], "users")
    transactions = _read(d["cleaned"], "transactions")
    profiles = _read(d["profiles"], "user_profiles")[["user_id", *PROFILE_FIELDS]]

    messages["timestamp"] = observation_times(messages["timestamp_utc"])
    messages["message"] = messages["message_normalized"]
    ordered = messages.sort_values(["timestamp", "message_id"])
    cutoffs = ordered.groupby("conversation_id").head(2).groupby("conversation_id")["timestamp"].max()
    cutoffs = cutoffs.rename("cutoff_utc").reset_index()
    msg = conversation_prefixes(messages, conversations, cutoffs)
    msg_truth = _read(d["truth"], "conversation_truth")
    msg = msg.merge(msg_truth[["conversation_id", "is_scam", "label_status", "scenario", "campaign_id", "data_source"]],
                    on="conversation_id", validate="one_to_one")
    msg = msg.merge(conversations[["conversation_id", "participant_a", "participant_b"]],
                    on="conversation_id", validate="one_to_one")
    msg = msg.merge(users[["user_id", "telegram_id"]], left_on="participant_a", right_on="telegram_id",
                    validate="many_to_one").rename(columns={"cutoff_utc": "event_time", "is_scam": "target"})
    # Payment features use source-zone hour and weekday and chronological ordering by instant.
    transactions["timestamp"] = observation_times(transactions["timestamp_utc"]).dt.tz_convert("Asia/Kolkata")
    transactions["amount"] = transactions["amount_normalized"]
    for key in ("sender_id", "receiver_id"):
        transactions[key] = transactions[f"{key}_normalized"]
    pay = build_transaction_features(transactions)
    pay = pay.merge(_read(d["truth"], "transaction_truth")[
        ["transaction_id", "fraud_label", "label_status", "scenario", "data_source"]], on="transaction_id", validate="one_to_one")
    actors = _read(d["truth"], "scammers").set_index("upi_id")["telegram_id"]
    pay["campaign_id"] = pay["receiver_id"].map(actors).fillna("__NOT_APPLICABLE__")
    users["upi_id"] = users["upi_id"].map(normalized_id)
    pay = pay.merge(users[["user_id", "upi_id"]], left_on="sender_id", right_on="upi_id",
                    validate="many_to_one").rename(columns={"timestamp": "event_time", "fraud_label": "target"})
    links = _read(d["truth"], "links")
    attempts = pay[["transaction_id", "event_time"]].rename(columns={"event_time": "attempt_time"})
    first_attempt = links.merge(attempts, on="transaction_id").groupby("conversation_id")["attempt_time"].min()
    msg["attempt_time"] = msg["conversation_id"].map(first_attempt)
    msg["observed_before_attempt"] = msg["event_time"].lt(msg["attempt_time"])

    result = {}
    for name, frame in (("messaging", msg), ("payment", pay)):
        known = frame["label_status"].isin(["confirmed", "legitimate"])
        labeled = frame.loc[known].merge(profiles, on="user_id", validate="many_to_one")
        labeled["target"] = labeled["target"].astype(int)
        result[name] = labeled, int((~known).sum())
    return result


def _group_order(values, seed):
    return sorted(values.unique(), key=lambda value: hashlib.sha256(f"{seed}:{value}".encode()).digest())


def split_frames(frame, seed, messaging):
    """Hold out focal users, time, campaigns and selected messaging scenario families."""
    users = _group_order(frame["user_id"], seed)
    i, j = int(len(users) * 0.60), int(len(users) * 0.80)
    user_groups = [set(users[:i]), set(users[i:j]), set(users[j:])]
    campaigns = frame.loc[frame["campaign_id"].ne("__NOT_APPLICABLE__"), "campaign_id"]
    held_campaigns = set(_group_order(campaigns, seed + 1)[:max(1, len(campaigns.unique()) // 3)])
    sorted_times = frame["event_time"].sort_values().reset_index(drop=True)
    first, second = sorted_times.iloc[[int(len(frame) * 0.55), int(len(frame) * 0.75)]]
    time_masks = [frame["event_time"].lt(first), frame["event_time"].ge(first) & frame["event_time"].lt(second),
                  frame["event_time"].ge(second)]
    # Held-out cohorts occur only in the test. Test also retains familiar scenarios/campaigns.
    blocked = frame["campaign_id"].isin(held_campaigns)
    if messaging:
        blocked |= frame["scenario"].isin(HELD_SCENARIOS)
    parts = [frame.loc[time_masks[k] & frame["user_id"].isin(user_groups[k]) & (~blocked if k < 2 else True)].copy()
             for k in range(3)]
    purged = {"validation": 0, "test": 0}
    if messaging:
        vectorizer = HashingVectorizer(analyzer="char", ngram_range=(3, 5), n_features=2**18,
                                       alternate_sign=False)
        for index, name in ((1, "validation"), (2, "test")):
            reference = pd.concat(parts[:index])[TEXT_COL]
            query = parts[index][TEXT_COL]
            if not reference.empty and not query.empty:
                similarity = (vectorizer.transform(query) @ vectorizer.transform(reference).T).toarray()
                overlap = query.isin(reference).to_numpy() | (similarity.max(axis=1) >= 0.95)
                purged[name] = int(overlap.sum())
                parts[index] = parts[index].loc[~overlap].copy()
    for left, right in zip(parts, parts[1:]):
        if set(left["user_id"]) & set(right["user_id"]) or left["event_time"].max() >= right["event_time"].min():
            raise RuntimeError("Inconsistent temporal or focal-user split")
    if any(part["target"].nunique() < 2 for part in parts):
        raise ValueError("Each Phase 2 partition needs both classes. Use the default Phase 1 dataset.")
    return parts, {"duplicate_purged": purged, "held_campaigns": sorted(held_campaigns),
                   "held_scenarios": sorted(HELD_SCENARIOS) if messaging else [],
                   "excluded_from_partitions": len(frame) - sum(map(len, parts)),
                   "boundaries_utc": [first.tz_convert("UTC").isoformat(), second.tz_convert("UTC").isoformat()]}


def messaging_rule(frame):
    credential = frame["n_credential_request_msgs"].gt(0)
    pressured_request = frame["n_payment_request_msgs"].gt(0) & frame["n_urgency_msgs"].gt(0)
    suspicious_link = frame["n_suspicious_link_msgs"].gt(0)
    return (credential | pressured_request | suspicious_link).astype(float).to_numpy()


def choose_threshold(y, scores, max_fp_per_1000=20):
    """Maximize F1 on the validation partition under a fixed false-alert budget."""
    candidates = np.unique(np.r_[scores, 1.0])
    best_f1, best_threshold = -1.0, 1.0
    y = np.asarray(y, dtype=bool)
    for threshold in candidates:
        positive = scores >= threshold
        fp = int((positive & ~y).sum())
        tp = int((positive & y).sum())
        if 1000 * fp / len(y) > max_fp_per_1000:
            continue
        f1 = 2 * tp / (int(y.sum()) + int(positive.sum()))
        if (f1, threshold) > (best_f1, best_threshold):
            best_f1, best_threshold = f1, float(threshold)
    if best_f1 < 0:
        raise ValueError("Validation false-alert budget has no feasible threshold in [0,1]")
    return best_threshold


def _metrics(test, scores, threshold):
    if test.empty:
        return {"n": 0}
    result = binary_metrics(test["target"], scores, threshold)
    result["false_alerts_per_1000_events"] = 1000 * result["confusion_matrix"]["fp"] / len(test)
    observed_days = test["event_time"].dt.tz_convert("Asia/Kolkata").dt.date.nunique()
    result["days_with_eligible_events"] = observed_days
    result["false_alerts_per_observed_day"] = result["confusion_matrix"]["fp"] / observed_days
    return result


def _wilson(successes, total):
    if total == 0:
        return None
    p = successes / total
    z = 1.96
    center = p + z**2 / (2 * total)
    radius = z * np.sqrt(p * (1 - p) / total + z**2 / (4 * total**2))
    scale = 1 + z**2 / total
    return [float(max(0, (center - radius) / scale)), float(min(1, (center + radius) / scale))]


def _subgroups(test, scores, threshold):
    scored = test.assign(_score=scores)
    results = {}
    for field in (*PROFILE_FIELDS, "scenario", "data_source"):
        groups = {}
        for key, group in scored.groupby(field):
            metrics = _metrics(group, group["_score"], threshold)
            counts = metrics["confusion_matrix"]
            groups[str(key)] = {
                "n": len(group), **counts, "recall": metrics["recall"] if counts["tp"] + counts["fn"] else None,
                "recall_95ci_descriptive": _wilson(counts["tp"], counts["tp"] + counts["fn"]),
                "fpr_95ci_descriptive": _wilson(counts["fp"], counts["fp"] + counts["tn"]),
            }
        results[field] = groups
    return results


def _cluster_ci(test, scores, threshold, seed, draws=250):
    sampled = test.assign(_score=scores).groupby("user_id").indices
    groups = list(sampled.values())
    rng = np.random.default_rng(seed)
    values = {name: [] for name in ("precision", "recall", "f1", "pr_auc", "roc_auc")}
    for _ in range(draws):
        index = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        metrics = _metrics(test.iloc[index], scores[index], threshold)
        for key, samples in values.items():
            if metrics[key] is not None:
                samples.append(metrics[key])
    return {key: np.percentile(samples, [2.5, 97.5]).tolist() if samples else None
            for key, samples in values.items()}


def run(data_dir, seed=42, use_cleaned=False):
    d = dirs(data_dir)
    models_dir = Path(data_dir) / "phase2_models"
    d["reports"].mkdir(exist_ok=True, parents=True)
    results = {"version": VERSION, "seed": seed, "data_source": "synthetic",
               "dataset_configuration": json.loads((Path(data_dir) / "dataset_manifest.json").read_text()),
               "threshold_policy": "Max validation F1, at most 20 false alerts per 1000 validation events",
               "modalities": {}}
    for name, (frame, unknown) in prepare(data_dir, use_cleaned).items():
        messaging = name == "messaging"
        entity = "conversation_id" if messaging else "transaction_id"
        (train, validation, test), split_meta = split_frames(frame, seed, messaging)
        columns = [TEXT_COL, *CONTENT_COLS] if messaging else PAYMENT_FEATURES
        models = {"combined_logreg": MessagingModel("combined", seed=seed)} if messaging else {
            kind: PaymentModel(kind, seed=seed) for kind in KINDS
        }
        rule = messaging_rule if messaging else lambda f: f["new_beneficiary_high_amount"].to_numpy()
        section = {"split": split_meta, "excluded_unresolved_labels": unknown,
                   "partitions": {key: {"n": len(part), "positive": int(part["target"].sum()),
                                        "focal_users": part["user_id"].nunique()}
                                  for key, part in zip(("train", "validation", "test"), (train, validation, test))},
                   "baseline": {"validation": _metrics(validation, rule(validation), 0.5),
                                "test": _metrics(test, rule(test), 0.5)}, "models": {}}
        test_scores = test[[entity, "event_time"]].copy()
        test_scores["rule_score"] = rule(test)
        for kind, model in models.items():
            model.fit(train[columns], train["target"].to_numpy())
            val_scores = model.predict_proba_frame(validation[columns])
            model.threshold = choose_threshold(validation["target"], val_scores)
            model.save(models_dir / f"{name}_{kind}.joblib")
            scores = model.predict_proba_frame(test[columns])
            test_scores[f"{kind}_score"] = scores
            novel_campaign = test["campaign_id"].isin(split_meta["held_campaigns"]).to_numpy()
            novel_scenario = test["scenario"].isin(split_meta["held_scenarios"]).to_numpy()
            entry = {"validation": _metrics(validation, val_scores, model.threshold),
                     "test": _metrics(test, scores, model.threshold),
                     "test_95ci_by_focal_user": _cluster_ci(test, scores, model.threshold, seed),
                     "subgroups": _subgroups(test, scores, model.threshold),
                     "held_campaign_cases": _metrics(test.loc[novel_campaign], scores[novel_campaign], model.threshold)}
            if messaging:
                entry["held_scenario_cases"] = _metrics(test.loc[novel_scenario], scores[novel_scenario], model.threshold)
                entry["out_of_template"] = run_probes(model)
                earlier = test["observed_before_attempt"].to_numpy()
                entry["linked_prefixes_before_attempt"] = _metrics(test.loc[earlier], scores[earlier], model.threshold)
            section["models"][kind] = entry
        write_tables({f"phase2_{name}_test_scores": test_scores}, d["processed"])
        results["modalities"][name] = section
    (d["reports"] / "phase2_evaluation.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    return results
