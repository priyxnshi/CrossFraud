# Prototype readiness and operational requirements

The local API serves a finite set of synthetic alerts on loopback. Its SQLite database stores alert IDs, review outcomes, and UTC timestamps. Results are append-only for the life of that database. Keep the demo on a controlled workstation. Access to the local device grants access to the demo.

## Before any operational use

| Area | Required work |
| --- | --- |
| Data authorization | Agree on custodians, purpose, licensing and consent or other approved legal basis. Add a source intake review and a provenance manifest. |
| Retention and access | Approve retention limits for raw chats, payment events, and outcomes. Separate identity and truth layers. Use encryption, scoped access controls, audit logs, and deletion for active copies and backups. |
| Operational evaluation | Obtain independent adjudication, evaluate on authorized representative timelines, measure the effect of missing identity and delayed events, and agree on reviewer capacity and escalation criteria. Check out-of-template, subgroup, and ambiguous-case performance with uncertainty. |
| Security and controls | Assess privacy, threat model, reviewer permissions, endpoint security and incident handling. Require a reviewer to corroborate alerts. Define accountable owners and escalation before enabling any operational workflow. |
| External systems | Obtain separate approval for any hosted repository, remote cache, DagsHub service, or financial or messaging integration. Assess the destination and allowed fields before any transfer. |

## Monitoring and rollback

- Monitor schema and join failures, missing fields and timestamps, duplicate rates, and the fraction of inputs quarantined. Treat unexpected rejection or missing provenance as an investigation trigger.
- Monitor feature and language distribution changes, score distributions, link confidence, ambiguity, unmatched attempts, and alerts per eligible event and per review day.
- Track unresolved, confirmed and dismissed reviews with denominators. Audit error rates and review load by material cohort where sample sizes permit. Investigate when thresholds drift from approved baselines or available review capacity.
- Keep the last reviewed code revision, runtime lock, dataset manifest, model hashes, and thresholds. If input quality or alert behavior changes materially, pause use, preserve review history, restore the last reviewed release, rerun validation and confirm the change with reviewers.
- Keep credentials in approved environment variables or a secret manager. DVC remotes, raw inputs, and review databases require a separate access, retention, and legal review before use outside the local prototype.

## Optional DagsHub path

Local tracking is the default. If separately authorized and a private destination is approved, create or connect the account and project, configure authentication locally or with a secret manager, and validate project permissions. Start by mirroring only the aggregate fields in `tracking/latest.json`. Consider approved model files only after reviewing privacy and access. Keep source observations, chat content, payment identifiers, truth links, raw examples, and the local review database outside experiment uploads. Treat a DVC remote as a separate authorization decision. No DagsHub project or remote is configured by this repository.
