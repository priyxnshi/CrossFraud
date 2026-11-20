# Research protocol

## Users and decisions

Fraud analysts and research reviewers inspect signals in a local review queue. Each alert should name the observed entity, evidence timestamps, supporting and conflicting signals, match ambiguity, and model version. Analysts inspect the supplied evidence and record confirmed, dismissed or unresolved with an audit reason. A score represents estimated review priority. Decisions about individuals require independent corroboration, authorization and due process. The prototype provides no automated accusations, blocking, reporting or sanctions.

| Target | Unit and reference |
| --- | --- |
| Messaging risk | A conversation prefix as of its scoring time. The reference is whether the conversation belongs to a fraud or grooming event. Stage labels support retrospective analysis. |
| Payment risk | A payment attempt when the payment event is available. The reference is fraud context independently of whether the attempt settled. |
| Link | A candidate conversation/request and payment attempt. The simulated association is positive truth. Unknown association in authorized data stays unknown unless adjudicated. |
| Combined risk | A review event at an explicit cutoff. For linked activity, judge the fraud case using observable conversation and payment evidence available at the cutoff. Track unlinked fraud and no-payment conversations separately. |

Confirmed requires independently verified evidence or an exact simulation assignment. Suspected means evidence of risk without adequate confirmation. Legitimate means an adjudicated benign case or simulated benign activity. Unknown covers unreviewed or insufficiently evidenced cases. Use only confirmed and legitimate for primary binary metrics. Report excluded counts for suspected and unknown. A scam conversation can remain unpaid or abandoned, and a fraudulent attempt can fail or reverse.

## Timing and comparison

The alert time is when its last required observation is available plus processing latency. At cutoff t, each observation must have both event and availability times at or before t. The v2 generator uses event time as simulated availability. Its ingestion timestamp records the actual batch run, separate from simulated availability. In a future authorized source, use event and arrival times independently and account for late events and delays.

An early warning must be strictly earlier than the first adjudicated associated payment attempt, even if the attempt later fails. At or after the attempt, label the alert payment-time or post-payment. The latest eligible instant is immediately before that attempt at the source time resolution. Report lead time as first associated attempt time minus first qualifying alert time, among detected linked cases. Also publish warning coverage among all eligible linked fraud cases and report unpaid cases separately. A pre-payment alert can use messaging and qualifying historical observations. Payment attempt evidence can only corroborate an alert once that attempt is observable. Replay all comparators over the same event timeline.

## Evaluation

Use temporal partitions plus grouped holdouts by participant, campaign, scenario and duplicate/template family. Keep both sides of an evaluated link within the relevant partition; document overlapping groups and any dropped cases. Use explicit event-time cutoffs and strictly earlier payment history. Keep staged truth, final status and future messages outside feature building. Fit model transforms and choose thresholds using training and training-derived validation only. Compare at matched alert budgets and report precision, recall, F1, average precision (PR-AUC), ROC-AUC, confusion counts, and false alerts per 1,000 eligible events and per review day. For matching report precision, recall, F1, top-k recall, ambiguity and abstention with denominators including unlinked cases. Report median and spread of lead time alongside warning coverage. Report denominators and uncertainty for overall and subgroup metrics, using grouped intervals when feasible, plus out-of-template errors.

## Privacy and use

Phase 1 consumes generated observations only. The optional SMS format adapter is isolated and the test uses invented rows. Use authorized external data only after recording the custodian, license or data-use agreement, permitted purpose, consent or other approved basis, and access and retention policy. Seek separate authorization before any transfer or live connection.

Separate identity mapping, profiles and labels from model input. For authorized data, minimize fields, tokenize direct identifiers with a controlled mapping, use encryption and role-based access, limit raw message access to authorized reviewers, and audit reads and exports. Establish a retention and deletion schedule with the custodian before ingestion, including copies and backups. Keep identifiers, text, credentials and partner data out of source control, ordinary logs and external experiments. Never request or collect actual OTPs, PINs or passwords. The prototype uses fictional handles and example or reserved URL hosts.
