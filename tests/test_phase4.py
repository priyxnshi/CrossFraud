import json
from threading import Thread
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from crossfraud.data.ingestion import verify_cleaned
from crossfraud.review_api import ReviewStore, review_server


@pytest.fixture
def synthetic_reports(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "phase3_evaluation.json").write_text(json.dumps({"source": "synthetic"}))
    alert = {"schema_version": "phase3-alert-v1", "event_time_utc": "2025-01-01T00:00:00+00:00",
             "evidence": {"match": {"selected": {"confidence": 0.9}}}}
    (reports / "phase3_alert_examples.json").write_text(json.dumps([alert]))
    return tmp_path


def test_review_persists_all_outcomes(synthetic_reports):
    database = synthetic_reports / "review.sqlite3"
    store = ReviewStore(synthetic_reports, database)
    alert_id = next(iter(store.alerts))
    assert store.get(alert_id)["review_outcome"] == "unresolved"
    for outcome in ("confirmed", "dismissed", "unresolved"):
        assert store.set_outcome(alert_id, outcome)["review_outcome"] == outcome
    reopened = ReviewStore(synthetic_reports, database).get(alert_id)
    assert [entry["outcome"] for entry in reopened["review_history"]] == [
        "confirmed", "dismissed", "unresolved"]
    assert reopened["evidence"]["match"]["selected"]["confidence"] == 0.9


def test_demo_refuses_non_synthetic_report(synthetic_reports):
    path = synthetic_reports / "reports" / "phase3_evaluation.json"
    path.write_text(json.dumps({"source": "partner"}))
    with pytest.raises(ValueError, match="synthetic"):
        ReviewStore(synthetic_reports, synthetic_reports / "review.sqlite3")


def test_review_http_routes(synthetic_reports):
    with review_server(synthetic_reports, synthetic_reports / "review.sqlite3", port=0) as server:
        worker = Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f"http://127.0.0.1:{server.server_port}/alerts"
            with urlopen(base, timeout=5) as response:
                alert = json.load(response)["alerts"][0]
            route = f'{base}/{alert["alert_id"]}/review'
            request = Request(route, b'{"outcome":"confirmed"}', {"Content-Type": "application/json"})
            with urlopen(request, timeout=5) as response:
                assert json.load(response)["review_outcome"] == "confirmed"
            malformed = Request(route, b'{"outcome":"unknown"}', {"Content-Type": "application/json"})
            with pytest.raises(HTTPError) as error:
                urlopen(malformed, timeout=5)
            assert error.value.code == 400
        finally:
            server.shutdown()
            worker.join(timeout=5)


def test_missing_cleaned_manifest_refused(tmp_path):
    with pytest.raises(ValueError, match="missing or stale"):
        verify_cleaned(tmp_path)
