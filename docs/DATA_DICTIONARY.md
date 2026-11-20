# Phase 1 data dictionary

A dataset directory holds `dataset_manifest.json` with the effective configuration, seed and source version. Ingest reports counts and issues in `reports/validation_report.json`. A successful ingest writes observation CSVs and a completion manifest under `cleaned/`. On an error, the entire batch is excluded and the cleaned completion manifest is removed. Older CSVs may still be present. Give each concurrent run its own dataset directory.

## Observations in raw/

| Table | Keys and fields |
| --- | --- |
| users | PK `user_id`. Unique `telegram_id` is a generic simulated messaging identity despite its legacy name. Unique `upi_id` is a simulated account address. `display_name` is fictional. Mapping is simulation-only. |
| conversations | PK `conversation_id`. `participant_a` is the simulated focal user and `participant_b` the counterpart messaging identity. `platform` is telegram or whatsapp. `start_ts`, `end_ts` bound message events. The final end time is retrospective for an open conversation. |
| messages | PK `message_id`, FK `conversation_id`. `sender_id`, `receiver_id` are messaging identities. `timestamp`, original `message`, `message_type` (text or link_share). |
| transactions | PK `transaction_id`. `sender_id` is the payer's UPI address. `receiver_id` is a payee address and may represent an individual or merchant. `timestamp` is attempt time. `amount` is positive INR, `currency` is INR, and `transaction_type` is P2P/P2M/COLLECT. `beneficiary_name`, `beneficiary_type`, `beneficiary_handle` preserve payee metadata. `status_at_event` is accepted or failed. Accepted can later settle or reverse. |

All rows include `data_source` and `source_version`. V2 writes `synthetic` and `synthetic-v2`. The isolated SMS adapter uses a `public:` source marker and its own observed-text and spam-label files. It has no cross-platform timestamps or payment evidence. Partner data would have separate storage and a recorded approval and provenance manifest. The canonical ingest command accepts synthetic observations.

Cleaned observations retain source fields. `*_utc` timestamps use the explicit offset when available and Asia/Kolkata for naïve values. Simulated times represent wall-clock event times and exclude actual arrival latency. `message_normalized` applies Unicode NFKC and collapses whitespace. `urls_normalized` is a JSON array with lowercased scheme and authority and no fragment, retaining path and query, with HTTPS assumed for www-only URLs. URLs are never fetched. Identifiers are normalized in derived lowercased fields and whitespace surrounding @ is removed. `amount_normalized` is numeric INR and `currency_normalized` is uppercased. `ingested_at_utc` records actual batch time, and `processing_version` records the transformation version.

## Evaluation and subgroup data

| Directory and table | Keys and fields |
| --- | --- |
| profiles/user_profiles | PK/FK `user_id`. `state_ut`, `region`, `settlement_type`, adult `age_band`, `primary_language`, `secondary_language`, `education_band`, `occupation_sector`, `monthly_household_income_band_inr`, `smartphone_access`, `internet_access`, `upi_experience_band`. Coverage analysis only. |
| ground_truth/scammers | Simulated campaign/actor lookup. `scammer_id`, `telegram_id`, `upi_id`, `display_name`. One actor can own multiple addresses. |
| ground_truth/conversation_truth | PK/FK `conversation_id`. `scenario`, `is_scam`, `label_status`, `campaign_id`, `instructed_upi`, `upi_as_written`, `instructed_amount`, `attempt_outcome` and `paid` (settled or reversed). |
| ground_truth/message_stages | PK/FK `message_id`, FK `conversation_id`, `stage`: contact, grooming, urgency, payment_request, victim_response or chat. |
| ground_truth/transaction_truth | PK/FK `transaction_id`. `scenario`, `fraud_label`, `label_status`, `outcome` (settled, failed or reversed). |
| ground_truth/links | Composite `conversation_id`, `transaction_id`. `link_type`, `link_evidence`, and `delay_minutes` after the last scripted payment request. Includes linked attempts even when they fail. Absence denotes no known generated link. |

Truth adds `label_source` and `label_confidence` (simulation, 1.0). In the vocabulary, empty means missing, `__UNKNOWN__` means an unavailable value for an applicable field, and `__NOT_APPLICABLE__` means the field does not apply. Binary targets for suspected or unknown cases use `__UNKNOWN__`. Empty required fields are validation errors. Explicit not-applicable values occur on no-request conversations and on some profiles with no secondary language. The controlled v2 generator emits known synthetic targets.

## Population assumptions and limitations

The generator uses illustrative choices. There is no official source calibration and no claim of statistical representativeness. Default settings draw uniformly over 21 state/UT options across six broad regions and uniformly from the listed options for age, settlement, education, occupation, income, smartphone access, internet reliability and UPI experience. Language context uses one illustrative regional assignment per state or UT plus an optional secondary language. Language snippets in chat are sampled across both classes independently of the profile. The text covers a small set of Latin and Indic script phrases, so it cannot validate multilingual transfer. Profiles omit caste and religion.

The profile stream is independent of the activity stream. The default gives all 300 users at least one benign and one scam conversation. For custom counts below the number of users, subgroup coverage may be sparse. Even under defaults, intersectional groups can be small. Shorthand campaign IDs, short templates, payee reuse, exact synthetic joins, simplified payment outcomes and independent profile attributes limit realism. Conversation and transaction samples are clustered by participant and campaign. The generator has no realistic network outages, authorization latency or observational error model beyond noisy identifiers and the missing-message fraud scenario.

Use a JSON config to change `n_users`, `n_scammers`, `n_scam_convs`, `n_benign_convs`, `n_txn_only_fraud`, `days`, `start`, `seed`, `scam_pay_rate`, `scam_collect_rate`, `p2p_pay_rate`, `obfuscation_rate`, `code_mix_rate`, `unsuccessful_rate` and `population_weights`. The latter maps a profile field to weights ordered as declared in `crossfraud/data/demographics.py`. For example, `{"population_weights":{"settlement_type":[1,2,2,3]}}` emphasizes smaller places. Amounts, scripts and default scenario weights are declared in source. Background activity adds up to 45 attempted transactions per user. The generator builds data frames in memory and the small default run is suitable for a local CPU. Byte reproducibility covers source CSVs and configuration manifests on the same runtime. Cleaned outputs include a wall-clock ingestion timestamp.

The verified default run occupied about 6.75 MB across raw, cleaned, profile and truth files. Generation and ingestion took a few seconds locally. The SQLite and legacy feature exports are additional.
