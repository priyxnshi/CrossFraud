"""Illustrative population context, generated independently of labels and outcomes."""
from __future__ import annotations

import math

import pandas as pd

# Every entry has equal probability unless weights are supplied in the run configuration.
GEOGRAPHY = {
    "Delhi": ("North", "Hindi"), "Punjab": ("North", "Punjabi"),
    "Uttar Pradesh": ("North", "Hindi"), "Jammu and Kashmir": ("North", "Urdu"),
    "Rajasthan": ("North", "Hindi"), "Gujarat": ("West", "Gujarati"),
    "Maharashtra": ("West", "Marathi"), "Goa": ("West", "Konkani"),
    "Madhya Pradesh": ("Central", "Hindi"), "Chhattisgarh": ("Central", "Hindi"),
    "Bihar": ("East", "Bhojpuri"), "West Bengal": ("East", "Bengali"),
    "Odisha": ("East", "Odia"), "Assam": ("Northeast", "Assamese"),
    "Manipur": ("Northeast", "Meitei"), "Sikkim": ("Northeast", "Nepali"),
    "Karnataka": ("South", "Kannada"), "Kerala": ("South", "Malayalam"),
    "Tamil Nadu": ("South", "Tamil"), "Telangana": ("South", "Telugu"),
    "Puducherry": ("South", "Tamil"),
}
OPTIONS = {
    "settlement_type": ("metropolitan", "large_city", "small_town", "rural"),
    "age_band": ("18–24", "25–34", "35–49", "50–64", "65+"),
    "education_band": ("school_or_less", "secondary", "vocational", "degree_or_higher"),
    "occupation_sector": ("student", "services", "agriculture", "industry", "self_employed", "other"),
    "monthly_household_income_band_inr": ("under_15000", "15000_39999", "40000_79999", "80000_plus"),
    "smartphone_access": ("personal", "shared"),
    "internet_access": ("reliable", "intermittent"),
    "upi_experience_band": ("new", "occasional", "experienced"),
}


def make_user_profiles(users, rng, weights):
    available = {"state_ut": tuple(GEOGRAPHY), **OPTIONS}
    if set(weights) - set(available):
        raise ValueError("Unrecognized population weight key")

    for field, field_weights in weights.items():
        if (len(field_weights) != len(available[field]) or
                any(not math.isfinite(weight) or weight < 0 for weight in field_weights) or
                not any(field_weights)):
            raise ValueError(f"Invalid population weights for {field}")

    def choose(field):
        values = available[field]
        return rng.choices(values, weights=weights.get(field), k=1)[0]

    rows = []
    for user_id in users["user_id"]:
        state = choose("state_ut")
        region, language = GEOGRAPHY[state]
        secondary = rng.choice(("English", "Hindi" if language != "Hindi" else "English",
                                "__NOT_APPLICABLE__"))
        rows.append({"user_id": user_id, "state_ut": state, "region": region,
                     "primary_language": language, "secondary_language": secondary,
                     **{field: choose(field) for field in OPTIONS}, "data_source": "synthetic"})
    return pd.DataFrame(rows)
