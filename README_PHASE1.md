# Phase 1 | Synthetic dataset and validation

**Status:** Complete. This phase established the data foundation for studying fraud that crosses messaging and UPI.

## What was built

- Audited the repository and documented the research targets, the early-warning cutoff, and the human-review workflow.
- Built a deterministic, configurable simulation of Telegram and WhatsApp conversations and UPI payment attempts. The payment records cover person-to-person transfers, merchant payments, and collect requests. They model UPI generally, with no app-specific behavior for PhonePe, Google Pay, or other UPI apps.
- Generated 10 scam conversation scenarios and nine benign scenarios. Examples include impersonation, task scams, investment pitches, credential requests, delivery fees, rent, purchases, and refunds. Included unpaid and abandoned attempts, failed and reversed transactions, benign urgency, and fraud attempts with no visible chat.
- Used fictional identifiers and separate population profiles. State or union territory, language context, adult age, settlement, education, occupation, household income, smartphone and internet access, and UPI experience support coverage analysis. Population distributions are illustrative. Profile fields are excluded from the feature pipeline.
- Preserved raw records and wrote a separate cleaned layer with UTC timestamps, normalized Unicode and whitespace, and derived amounts, currency, payment IDs, and URLs. Stored labels, message stages, outcomes, and truth links separately.
- Validated schema, timestamps, amounts, identifiers, duplicates, references, and label consistency. Ingestion reports failures and rejects an invalid batch.

## Seed-42 dataset and verification

| Metric | Result |
| --- | ---: |
| Participant profiles | 300 |
| States and union territories represented | 21 |
| Broad regions / settlement categories | 6 / 4 |
| Conversations | 750 |
| Scam / benign conversations | 300 / 450 |
| Messages | 3,570 |
| UPI payment attempts | 9,582 |
| Fraud-labeled attempts | 230 |
| Failed / reversed attempts | 548 / 596 |
| Conversation-to-attempt truth links | 418 |
| Linked scam / benign attempts | 190 / 228 |
| Fraud attempts without a visible linked chat | 40 |
| Validation errors / warnings / excluded observations | 0 / 0 / 0 |

Two independent seed-42 generations produced byte-identical copies of all ten source CSVs and the configuration manifest. The full run also checked feature generation and SQLite export, and a small configuration with zero payment links passed ingestion. At Phase 1 sign-off, 93 tests passed with one pandas warning from the legacy payment model. These are simulation and data-quality results.

## Code and tools

| Component | Code or tool |
| --- | --- |
| CLI and serialization | [cli.py](crossfraud/cli.py), [io.py](crossfraud/io.py), Python standard library |
| Seeded generator | [synthetic.py](crossfraud/data/synthetic.py), Python random, pandas |
| Population sampling | [demographics.py](crossfraud/data/demographics.py) |
| Schema, validation and ingestion | [schemas.py](crossfraud/schemas.py), [validation.py](crossfraud/data/validation.py), [ingestion.py](crossfraud/data/ingestion.py), pandas, NumPy |
| Observation-only export and database | [pipeline.py](crossfraud/features/pipeline.py), [db.py](crossfraud/data/db.py), SQLite |
| Verification | pytest, [synthetic tests](tests/test_synthetic.py), [validation tests](tests/test_validation.py), [ingestion tests](tests/test_ingestion.py) |

## Run and inspect

From the project root in a Python 3.10+ environment with [dependencies installed](requirements.txt):

```powershell
python -m crossfraud.cli phase1 --seed 42 --data-dir data/phase1
python -m crossfraud.cli ingest --data-dir data/phase1
python -m pytest -q tests/test_synthetic.py tests/test_validation.py tests/test_ingestion.py
```

Use `--config` to supply a JSON generator configuration. Outputs include [dataset manifest](data/phase1/dataset_manifest.json), [raw observations](data/phase1/raw), [cleaned observations](data/phase1/cleaned), [profiles](data/phase1/profiles), [ground truth](data/phase1/ground_truth), and the [validation report](data/phase1/reports/validation_report.json). The optional full run adds [SQLite](data/phase1/crossfraud.db) and processed features.

See the [data dictionary](docs/DATA_DICTIONARY.md), [research protocol](docs/RESEARCH_PROTOCOL.md), and [project audit](docs/PROJECT_PLAN.md). The next completed phase is [Phase 2](README_PHASE2.md).
