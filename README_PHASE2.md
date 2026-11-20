# Phase 2 | Separate messaging and UPI models

**Status:** Complete. Inputs are the seed-42 synthetic records documented in [Phase 1](README_PHASE1.md).

## Completed in Phase 2

- Validated the Phase 1 v2 dataset at the training entry point. Built features from observations before joining binary targets and subgroup metadata. Confirmed and legitimate labels are used for binary training. The report counts unresolved labels separately.
- Added timestamped messaging prefixes for inference and evaluated one fixed decision point per conversation, when its second message becomes observable. Built payment features at attempt time, using strictly earlier history, including when transactions share a timestamp.
- Implemented a messaging rule and reused the new-beneficiary/high-amount payment rule. Fit a messaging logistic regression using TF-IDF and content indicators, and fit separate payment logistic regression and random forest models. Each fit receives an explicit feature allowlist. Fit transforms only on training rows. The separate model scores are uncalibrated and should not be compared directly or averaged.
- Added a basic candidate matcher. It returns already-observed attempts after the request with an exact normalized payee match, optionally constrains the payer, and ranks by amount tolerance and elapsed time. It retains multiple candidates and requires no truth file.
- Added review-only inference wrappers in `crossfraud.models.phase2_features`. `score_conversation_as_of` requires timestamped messages and a cutoff. `score_payment_attempt` uses the supplied payment event and earlier observable history. Both return the existing explainable output contract with a UTC scoring timestamp. The contract's predicted class is a review signal.
- Saved train-partition model artifacts, scored held-out rows and exported aggregate evaluation. The synthetic held-out score CSVs contain entity keys, event times and scores, with truth kept in Phase 1 tables.

## Reproduce locally

From this project folder using the environment described in the README:

```powershell
python -m crossfraud.cli phase2 --data-dir data/phase1 --seed 42
python -m pytest -q
```

The command revalidates the source and writes locally. See `data/phase1/reports/phase2_evaluation.json`, `data/phase1/phase2_models/` and `data/phase1/processed/phase2_*_test_scores.csv`. The model files are local joblib artifacts. Load only trusted files with the matching runtime.

## Evaluation protocol

The test follows train and validation in time. Focal participant groups are disjoint across partitions. Five campaign groups are absent from training and validation, and their test cases are broken out. Messaging also withholds delivery fee, family impersonation, refund and urgent non-payment scenarios from training and validation. Messaging validation and test prefixes with exact or at least 0.95 cosine-similar cleaned character n-grams in earlier partitions are removed. The overlap filter uses fixed hashing and does not fit learned transforms. It cannot detect every semantic template duplicate. Secondary conversational participants and payment payees can recur. Earlier unlabeled payment observations from the available history remain eligible as historical context, including for held-out payers. There is no claim of a cold-start or fully isolated social graph experiment.

The rule thresholds are fixed heuristics. Model thresholds maximize F1 on validation with at most 20 false alerts per 1,000 validation events. That budget is a prototype setting, and test alert rates may exceed it. The JSON contains precision, recall, F1, average precision (PR-AUC), ROC-AUC, confusion counts, false alerts per 1,000 events and per day with eligible events, user-clustered bootstrap intervals and cohort summaries. Cohort summaries report denominators, false positives, misses and descriptive Wilson intervals where rates are defined. Small cells are exploratory and do not support a fairness conclusion. Subgroup language is profile context. Existing text features are primarily English lexicons and ASCII TF-IDF.

## Seed-42 synthetic results

| Held-out detector | Test rows | Positives | Precision | Recall | F1 | PR-AUC | FP per 1,000 events |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Messaging rule | 22 | 12 | 0.000 | 0.000 | 0.000 | 0.545 | 0.0 |
| Messaging logistic regression | 22 | 12 | 1.000 | 0.333 | 0.500 | 1.000 | 0.0 |
| Payment rule | 478 | 14 | 0.375 | 0.429 | 0.400 | 0.177 | 20.9 |
| Payment logistic regression | 478 | 14 | 0.333 | 0.357 | 0.345 | 0.428 | 20.9 |
| Payment random forest | 478 | 14 | 0.500 | 0.214 | 0.300 | 0.390 | 6.3 |

The messaging rule fired on zero of the two-message test prefixes. At its validation threshold the model flagged four scams and missed eight. It flagged one of six hand-written scams and one of seven benign probes. The strict messaging test retained just 22 conversations after split and duplicate filtering, so its perfect ranking on that test is especially fragile. The payment rule had the highest F1 at these operating points. Logistic regression had the highest payment average precision and the forest generated the fewest false alerts. These results describe synthetic behavior only. The modality test cohorts differ, so comparing rows across modalities cannot establish the incremental value of combining evidence.

## Phase 3 proposed work

After explicit approval, build ambiguity-aware matching with auditable evidence, configurable tolerances and abstention. Evaluate link accuracy, no-message fraud, missing evidence and ambiguous cases. Compare messaging-only, payment-only, rule matching and combined alerts on a common held-out event timeline, then report alert coverage, false alerts and warning lead time. Phase 2 scores are separate and do not establish a cross-platform or early-warning benefit.


## Code, tools and output files

| Component | Code and tools |
| --- | --- |
| Training CLI, temporal/user split, thresholds, and metrics | [cli.py](crossfraud/cli.py), [phase2.py](crossfraud/models/phase2.py), [metrics.py](crossfraud/models/metrics.py), Python, pandas, NumPy and scikit-learn |
| Messaging model and text features | [messaging.py](crossfraud/models/messaging.py), [text_features.py](crossfraud/features/text_features.py), scikit-learn TF-IDF and logistic regression |
| Payment models and chronological history | [payment.py](crossfraud/models/payment.py), [transaction_features.py](crossfraud/features/transaction_features.py), scikit-learn logistic regression and random forest |
| Cutoffs, candidate matcher, and review output | [phase2_features.py](crossfraud/models/phase2_features.py), [contract.py](crossfraud/models/contract.py) |
| Independent examples and checks | [probes.py](crossfraud/models/probes.py), [test_phase2.py](tests/test_phase2.py), pytest |

- [Machine-readable evaluation](data/phase1/reports/phase2_evaluation.json)
- [Saved model artifacts](data/phase1/phase2_models), serialized with joblib
- [Messaging scores](data/phase1/processed/phase2_messaging_test_scores.csv) and [payment scores](data/phase1/processed/phase2_payment_test_scores.csv)

The Desktop copy passed 97 tests with one pandas warning in the legacy payment inference path. The three saved models reproduced the held-out scores checked through their inference functions. The next approval gate is [Phase 3](README_PHASE3.md).
