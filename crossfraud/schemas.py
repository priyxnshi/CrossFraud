"""Single source of truth for Phase 1 table schemas (raw layer)."""

USER_COLS = ["user_id", "telegram_id", "upi_id", "display_name", "data_source"]

# Synthetic-only population context. Never use these fields as fraud predictors.
USER_PROFILE_COLS = ["user_id", "state_ut", "region", "settlement_type", "age_band",
                     "primary_language", "secondary_language", "education_band", "occupation_sector",
                     "monthly_household_income_band_inr", "smartphone_access",
                     "internet_access", "upi_experience_band", "data_source"]

CONVERSATION_COLS = ["conversation_id", "platform", "participant_a", "participant_b",
                     "start_ts", "end_ts", "data_source"]

MESSAGE_COLS = ["message_id", "conversation_id", "sender_id", "receiver_id", "timestamp",
                "message", "message_type", "data_source"]

TRANSACTION_COLS = ["transaction_id", "sender_id", "receiver_id", "timestamp", "amount",
                    "transaction_type", "beneficiary_name", "beneficiary_type",
                    "beneficiary_handle", "currency", "status_at_event", "data_source"]

TABLES = {"users": USER_COLS, "user_profiles": USER_PROFILE_COLS,
          "conversations": CONVERSATION_COLS,
          "messages": MESSAGE_COLS, "transactions": TRANSACTION_COLS}

MESSAGE_TYPES = {"text", "link_share"}
TRANSACTION_TYPES = {"P2P", "P2M", "COLLECT"}
BENEFICIARY_TYPES = {"individual", "merchant"}
