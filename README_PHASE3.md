# Phase 3 | UPI correlation and early-warning evaluation

**Status:** Complete. This phase adds an auditable matcher and compares four detectors on the same held-out synthetic timeline.

## What was built

- Extracted payment-request evidence from message text with timestamps. Supported literal UPI addresses, case and spacing normalization, and written separators such as `at`, `[at]`, and `(at)`. A single local-part edit is a weaker candidate when the handle matches and the account is long enough. Parser candidates require agreement with an observed payee address to become relevant.
- Ranked conversations for each observed payment with address agreement, amount difference, elapsed time, and available payer-to-participant evidence. Kept candidates with conflicts for audit, abstained below a confidence threshold, and left competing candidates unresolved within a configurable margin. The confidence is a heuristic score.
- Produced review alerts with detector and model versions, event time, earliest observable scoring time, score, threshold, risk level, supporting and conflicting signals, and candidate evidence.
- Replayed messaging-only, payment-only, exact rule matching, and combined scoring at observable event times. Evaluated no-message fraud and measured how many linked fraud cases received a strictly pre-attempt warning.

## Replay and assurance

The replay uses common chronological train, validation, and test windows and disjoint focal participant groups. Five campaigns and four scenario names were excluded from training and validation. Overlapping messaging prefixes were purged across partitions using exact cleaned text and hashed character n-gram similarity. Training used 180 conversations and 3,201 attempts. Validation used 20 conversations and 364 attempts. Truth labels are supervised targets and reference links group events into cases only for evaluation. Matching reads visible observations and the simulation's payer identity mapping.

Messaging scores once per eligible chat at its second observable message. Payment scoring uses strictly earlier transaction history. At payment time, the combined detector can use an accepted chat match with a score already available by that instant. It uses the larger modality rank plus a bounded corroboration bonus. Each modality rank is an empirical percentile relative to its own training scores. The model and combined thresholds maximize validation F1 subject to 20 false alerts per 1,000 validation cases. The exact rule uses a fixed criterion requiring a unique normalized address, agreeing payer and within-tolerance amount. Model thresholds were fixed before testing.

The test includes 22 conversations and 478 attempts, grouped into 484 evaluation cases with 17 fraud cases. Six linked attempts had their conversation outside the eligible cohort and were evaluated as payment-only cases for grouping purposes. The available transaction history can contain earlier unlabeled observations from test payers. The design holds out focal participants, and secondary IDs may recur. It uses event time as simulated availability with no processing delay. Results are synthetic and the sample of linked fraud is small.

## Seed-42 results

| Detector | Fraud caught / 17 | False alerts | Precision | Recall | F1 | PR-AUC | Pre-attempt warnings / 9 linked fraud cases |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Messaging only | 4 | 0 | 1.000 | 0.235 | 0.381 | 0.674 | 4 |
| Payment only | 4 | 7 | 0.364 | 0.235 | 0.286 | 0.308 | 0 |
| Exact rule matching | 7 | 4 | 0.636 | 0.412 | 0.500 | 0.283 | 0 |
| Combined | 8 | 5 | 0.615 | 0.471 | 0.533 | 0.477 | 0 |

The combined detector alerted on five fraud cases missed by payment-only, and payment-only caught one that combined missed. Combined had fewer false alerts at the chosen operating points. Its high validation-selected threshold yielded payment-time alerts only. Messaging alone warned on four linked fraud cases between 121 and 241 minutes before the attempt, with a median of 152.6 minutes. Payment-only caught one of five fraud attempts without a visible chat. The other detectors caught none in that cohort.

The ranked matcher selected 13 of 16 reference links in the cohort with zero incorrect selections. This gives 100% precision and 81.25% recall, compared with 100% precision and 68.75% recall for the exact rule. Neither recorded an ambiguous selection on the seed-42 holdout. Controlled tests verify that competing candidates cause abstention and that fuzzy identifiers require corroboration. The synthetic payer mapping and scripted payees make matching easier than an authorized real-world implementation could assume.

## Code, tools and outputs

| Component | Code and tools |
| --- | --- |
| Request extraction, normalization, confidence and review alert schema | [correlation.py](crossfraud/models/correlation.py), Python and pandas |
| Temporal replay, grouped holdout, threshold selection and metrics | [phase3.py](crossfraud/models/phase3.py), [Phase 2 feature loading](crossfraud/models/phase2.py), NumPy and scikit-learn |
| CLI and verification | [cli.py](crossfraud/cli.py), [test_phase3.py](tests/test_phase3.py), pytest |

From the root of the project with [dependencies installed](requirements.txt):

```powershell
python -m crossfraud.cli phase3 --data-dir data/phase1 --seed 42
python -m pytest -q
```

CLI settings include `--window-minutes` (180), `--amount-fraction` (0.10), `--amount-floor-inr` (10), `--minimum-confidence` (0.75), and `--ambiguity-margin` (0.06). See the [machine-readable metrics](data/phase1/reports/phase3_evaluation.json) and [example review alerts](data/phase1/reports/phase3_alert_examples.json). The examples include messaging-only warnings and combined payment-time reviews.

[Phase 4](README_PHASE4.md) documents the completed DVC workflow, local tracking, repository checks, and review demo.
