# Model card | Cross-platform fraud review prototype

## Models, fit and scores

Phase 2 trains messaging logistic regression using TF-IDF and content indicators, plus UPI logistic regression and random forest using the attempt and strictly earlier payment history. The Phase 2 artifacts correspond to the training partitions. Phase 3 retrains the messaging and UPI logistic models on an aligned split and combines their relative ranks through a fixed corroboration rule. Modality scores, ranks, and match confidence are heuristic review signals. The models have no probability calibration for operational use.

The holdout follows train and validation in time and separates focal participants. Held campaigns, selected held scenarios, and near-duplicate exclusions improve the replay's separation. Earlier unlabeled observations may remain available as context. Phase 2 uses validation to choose operating points. Phase 3 reports a common-case comparison and measures lead time only for alerts before the payment event.

## Intended use and evidence

Intended users are research reviewers inspecting synthetic examples locally. Human review can record confirmed, dismissed, or unresolved decisions in the demo. These outcomes concern the simulated alert and do not establish facts about a person. The workflow performs no enforcement actions.

On 484 Phase 3 synthetic cases, combined caught 8 of 17 fraud cases with 5 false alerts, versus 4 of 17 with 7 for payment-only. Messaging alone produced pre-attempt warnings for 4 of 9 linked fraud cases. The selected combined threshold generated zero pre-attempt warnings. The matcher selected 13 of 16 in-cohort links with zero errors. On hand-written Phase 2 probes the messaging model flagged only 1 of 6 scams. These are small synthetic comparisons. The coverage, error rates, drift behavior and operational value of the models on authorized real data remain unmeasured.

## Change control

Tie score thresholds and comparisons to the run ID, source hash, data manifest, library versions, artifacts, and model schema. Check data quality and review outcomes before evaluating a change. The local demo reads static alerts and has no online learning. Rollback and review procedures are documented in the [readiness guide](READINESS.md).

[Phase 2 results](../README_PHASE2.md) · [Phase 3 results](../README_PHASE3.md)
