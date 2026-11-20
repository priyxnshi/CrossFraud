import pandas as pd

from crossfraud.models.correlation import MatchConfig, build_requests, make_alert, match_payment
from crossfraud.models.phase3 import case_events, case_metrics, exact_link_baseline, reference_rank


def requests(*texts):
    conversations = pd.DataFrame({"conversation_id": [f"C{i}" for i in range(len(texts))],
                                  "participant_a": ["participant"] * len(texts)})
    messages = conversations[["conversation_id"]].assign(
        message_id=[f"M{i}" for i in range(len(texts))], message=list(texts),
        timestamp="2025-02-01T10:00:00+05:30",
    )
    return build_requests(messages, conversations)


ATTEMPT = {"timestamp": "2025-02-01T10:02:00+05:30", "receiver_id": "seller42@demobank", "amount": 850}


def match(rows, payer="participant", cutoff=ATTEMPT["timestamp"], config=MatchConfig()):
    return match_payment(ATTEMPT, rows, cutoff, payer, config)


def test_normalized_match_keeps_audit_evidence():
    scored = match(requests("Send Rs 850 to SELLER42 [at] DEMOBANK"))
    assert scored["status"] == "matched"
    chosen = scored["selected"]
    assert chosen["identifier_evidence"] == "normalized_exact"
    assert chosen["delay_minutes"] == 2
    assert chosen["amount_difference_inr"] == 0
    assert "payer mapping agrees" in chosen["support"]


def test_fuzzy_match_requires_corroboration():
    rows = requests("Send Rs 850 to sellar42@demobank")
    scored = match(rows)
    assert scored["selected"]["identifier_evidence"] == "one_edit_local_part"
    assert exact_link_baseline(scored)["status"] == "no_match"
    assert match(rows, payer=None)["status"] == "no_match"
    assert match(requests("Try sellar42@demobank"))["status"] == "no_match"


def test_ambiguous_competitors_abstain():
    rows = requests("Send Rs 850 to seller42@demobank", "Send Rs 850 to SELLER42 @ DEMOBANK")
    scored = match(rows)
    assert scored["status"] == "ambiguous"
    assert scored["selected"] is None
    assert len(scored["candidates"]) == 2
    assert exact_link_baseline(scored)["status"] == "ambiguous"


def test_ignores_later_or_concurrent_requests_and_conflicting_payer():
    rows = requests("Send Rs 850 to seller42@demobank")
    assert match(rows, cutoff="2025-02-01T10:01:59+05:30")["status"] == "no_match"
    assert match(rows, config=MatchConfig(window_minutes=1))["status"] == "no_match"
    assert match(rows, payer="someone_else")["status"] == "no_match"
    rows.loc[0, "request_time"] = pd.Timestamp(ATTEMPT["timestamp"]).tz_convert("UTC")
    assert match(rows)["status"] == "no_match"
    rows.loc[0, "request_time"] += pd.Timedelta(seconds=1)
    assert match(rows)["status"] == "no_match"


def test_lead_time_requires_alert_strictly_before_attempt():
    attempt = pd.Timestamp(ATTEMPT["timestamp"])
    cases = {"C0": {"target": 1, "first_attempt": attempt, "cohort": "linked_pair_in_cohort"}}
    mapping = {"T0": "C0"}
    payment_event = ("T0", attempt, 0.9, {})
    messaging_event = ("C0", attempt - pd.Timedelta(minutes=2), 0.8, {})
    pay_stats = case_metrics(cases, case_events(cases, mapping, [payment_event]), 0.5)
    both_stats = case_metrics(cases, case_events(cases, mapping, [payment_event, messaging_event]), 0.5)
    assert pay_stats["early_warning"]["warned_before_attempt"] == 0
    assert both_stats["early_warning"]["median_lead_minutes"] == 2
    assert both_stats["confusion_matrix"]["tp"] == 1


def test_alert_contract_and_rank_reference():
    below, above = reference_rank([0.25, 0.75], [0.2, 0.4, 0.6])
    assert below < above
    alert = make_alert("payment_time_review", ATTEMPT["timestamp"], above, 0.5, "T0", {}, {"payment": "v1"})
    assert alert["risk_level"] == "high"
    assert alert["earliest_possible_alert_time_utc"] == "2025-02-01T04:32:00+00:00"
    assert "Review signal" in alert["interpretation"]
