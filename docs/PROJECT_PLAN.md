# Project audit and progress

| Component | As found | Phase 1 status |
| --- | --- | --- |
| Repository | Source project nested one level below workspace root. Git metadata unavailable in both locations. Python 3.10 project environment available. | Existing source and legacy data/models retained. |
| Data and schemas | CSV observations and simulation truth, generated SQLite and processed data. Raw observations carried labels. A partial profile schema and an import of a missing demographics module prevented generation. | Separate observation, normalized, profile and truth layers. Seeded population and activity generation restored and expanded. |
| Cleaning and validation | Schema, timestamp, duplicate, amount and identifier checks. No canonical cleaned layer or comprehensive truth joins. | Batch ingestion, UTC and derived fields, truth/reference validation, provenance and JSON reports. |
| Features | Existing text, conversation and transaction features with tests. Full-conversation aggregates require an explicit scoring cutoff for early warning. Legacy feature exports could carry labels. | Canonical feature entry point uses an observation-only allowlist and rejects invalid input. Cutoff-safe feature development remains Phase 2. |
| Models and evaluation | Existing rule signals, logistic regression, random forest, saved models, out-of-fold scores, temporal payment and scenario-held-out messaging reports. Existing metrics are tied to the old simulation. User/campaign/template isolation and subgroup evaluation are incomplete. | Existing model implementations and artifacts retained. No new training or evaluation run. Legacy training commands default to legacy data. |
| Cross-platform and readiness | Simulation truth links and matching evidence candidates existed. No demonstrated cross-platform matcher, early-warning study, DVC pipeline or review queue. | Pending Phases 3–4. |

## Checklist

- [x] Phase 1 audit, protocol and data dictionary.
- [x] Phase 1 configurable population, activity and truth generation.
- [x] Phase 1 source-preserving ingestion, quality checks and tests.
- [x] Phase 2 approved and completed. V2 target loading, scoring-time features, baselines, separate models, candidate matcher and synthetic evaluation are documented in [Phase 2 evaluation](PHASE2_EVALUATION.md).
- [x] Phase 3 approved and completed. Ranked matching, review alerts and common-timeline evaluation are documented in [Phase 3](../README_PHASE3.md).
- [x] Phase 4 approved and completed. DVC, local tracking, repository checks, a local review API, and readiness documentation are described in [Phase 4](../README_PHASE4.md).

The legacy `data/` artifacts predate this audit. Use `data/phase1/` for the v2 pipeline and keep performance results tied to the dataset and split that produced them.

## Verified default dataset

Seed 42 produced 300 profiles, 750 conversations (300 scam and 450 benign), 3,570 messages, 9,582 payment attempts (230 tagged fraud) and 418 links (190 scam and 228 benign). Forty fraud attempts have no linked conversation. The payment attempts include 548 failed and 596 reversed. There are 10 scam and nine benign conversation scenarios. Ingest reported zero errors, warnings or excluded observations. Repeated generation matched all ten CSVs and the dataset manifest byte for byte.
