# Phase 4 | Reproducibility and human-review demo

**Status:** Complete. The full research pipeline runs locally against synthetic data. The project is ready for local reproduction and review.

## What was built

- Defined six DVC stages covering data generation, schema validation and ingestion, feature exports, separate-model training, held-out correlation evaluation, and local experiment tracking. The stages write to `data/pipeline/`. The Phase 1–3 artifacts remain available in `data/phase1/`.
- Pinned the Python libraries used for the verified run and recorded the DVC output hashes in the pipeline lock. The synthetic DVC replay uses a fixed batch timestamp. Ordinary ingestion records its actual run time. Training and evaluation verify the SHA-256 hashes of source and cleaned files before using a completed ingestion run.
- Added an aggregate local experiment record with seeds, versions, model hashes, metric summaries, and the Git revision when available. This copy uses a source fingerprint because it has no Git metadata. The record excludes raw events, individual scores, identifiers, and example alerts.
- Added local Git ignore rules and a GitHub Actions workflow for tests and uncached reproducibility checks. The workflow is available for future repository setup.
- Added a loopback-only review API with a SQLite review history. It shows the event timeline, risk signals, candidate links and confidence, and records confirmed, dismissed, or unresolved review outcomes.

## Run the pipeline

From the project root in an activated Python 3.10 virtual environment:

```powershell
python -m pip install -r requirements-lock.txt -r requirements-dvc.txt
$env:DVC_SITE_CACHE_DIR = Join-Path (Get-Location) '.dvc/site-cache'
python -m dvc repro
python scripts/verify_pipeline.py
python -m pytest -q
```

The supplied DVC configuration works without a Git repository and disables analytics. The site-cache variable keeps Windows cache files inside the project. To use Git later, initialize an approved local repository and turn off DVC's no-SCM mode with `python -m dvc config core.no_scm false`. Review the files selected for Git before staging them. GitHub and DagsHub publication and all DVC remotes require separate approval.

## Open the local review API

```powershell
python -m crossfraud.review_api --data-dir data/pipeline
```

The API listens on `http://127.0.0.1:8765`. Visit the `/alerts` route in a local browser to inspect the JSON, or use the following PowerShell commands in a second terminal:

```powershell
$reviewEndpoint = 'http://127.0.0.1:8765/alerts'
$alerts = (Invoke-RestMethod $reviewEndpoint).alerts
$alerts | Select-Object alert_id, detector, risk_level, event_time_utc, review_outcome
$alertId = $alerts[0].alert_id
Invoke-RestMethod "$reviewEndpoint/$alertId"
Invoke-RestMethod "$reviewEndpoint/$alertId/review" -Method Post -ContentType 'application/json' -Body '{"outcome":"dismissed"}'
```

The example review writes to `data/pipeline/review/reviews.sqlite3`. Valid outcomes are `confirmed`, `dismissed`, and `unresolved`. Use Ctrl+C in the server terminal to stop it. You can also point it at the existing Phase 3 examples by passing `--data-dir data/phase1`. The API reads saved synthetic alerts and runs locally without credentials.

## Code, tools and outputs

| Component | Code or tool |
| --- | --- |
| Pipeline, cache and output manifest | [dvc.yaml](dvc.yaml), [dvc.lock](dvc.lock), DVC 3.67.1 |
| Reproducibility checks | [verify_pipeline.py](scripts/verify_pipeline.py), [workflow](.github/workflows/checks.yml), pytest |
| Local experiment tracking | [local_tracking.py](crossfraud/local_tracking.py), JSON and SHA-256 |
| Review data and endpoints | [review_api.py](crossfraud/review_api.py), Python HTTP server and SQLite |
| API and provenance tests | [test_phase4.py](tests/test_phase4.py) |

Pipeline outputs include the [validation report](data/pipeline/reports/validation_report.json), [Phase 2 metrics](data/pipeline/reports/phase2_evaluation.json), [Phase 3 metrics](data/pipeline/reports/phase3_evaluation.json), [synthetic alert examples](data/pipeline/reports/phase3_alert_examples.json), [models](data/pipeline/phase2_models), and [aggregate experiment record](data/pipeline/tracking/latest.json). Phase 4 reproduced the synthetic experiment. [Phase 3 results and limitations](README_PHASE3.md)

## Readiness and optional external setup

See the [data card](docs/DATA_CARD.md), [model card](docs/MODEL_CARD.md), and [readiness guide](docs/READINESS.md) for access, retention, monitoring, rollback, and optional DagsHub procedures. GitHub Actions has a workflow file for use after authorized repository setup. No hosting, DagsHub credentials, or remote cache is needed for the local prototype.

## Verification notes

The review tests cover valid and invalid HTTP outcomes, persisted review history, and rejection of non-synthetic reports. The pipeline check reruns the full DVC graph twice without the run cache and compares SHA-256 fingerprints for source and cleaned data, scores, models, reports, and the experiment record. The random forest uses a fixed single-worker summation order so the payment score CSV can be compared byte for byte on the same runtime.

The verified seed-42 run passed ingestion with zero errors or warnings. Two uncached replays matched 30 pipeline artifacts byte for byte, and the Desktop copy matched the DVC lock. The Desktop test suite passed 107 tests, with one pandas warning in the legacy payment inference path.
