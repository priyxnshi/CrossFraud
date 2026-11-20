# Data card | Synthetic messaging and UPI v2

## Purpose and source

This dataset supports research on observability, cross-platform link quality, and review alerts. It is generated locally from fictional templates and configurable population assumptions. The 300 synthetic profiles cover 21 states and union territories. Geographic, income, occupation, device, and language distributions are illustrative. The data has no partner-supplied or public source records. Document an approved license, legal basis, scope, retention schedule, and a source manifest before adding any external data.

The default seed produces 750 chats, 3,570 messages, 9,582 UPI attempts, and 418 reference links. Status at the attempt and eventual outcome are in different layers. Some cases have no payment or no visible chat. Simulated timestamps use India time and stable source IDs. The DVC replay uses a fixed synthetic batch timestamp for byte reproducibility, while ordinary ingest timestamps the actual processing run.

## Structure and handling

Observations, cleaned records, demographic profiles, and truth tables have separate directories. Truth includes scenario, labels, stages, campaign, outcomes, and reference links. The feature allowlist excludes truth and demographic inputs. IDs represent simulated accounts and people. Real direct identifiers, chats, credentials, and transaction data require access controls and a documented purpose. Keep them outside source control, ordinary logs, this prototype demo, and remote experiment systems.

The simulation includes overlapping attempted amounts and simple identity mapping. Text is template-based. The sample does not support population-level estimates or real-world performance claims. Treat profile attributes as coverage context, and report denominator and uncertainty for any subgroup metric.

[Schema and assumptions](DATA_DICTIONARY.md) · [Phase 1 metrics and verification](../README_PHASE1.md)
