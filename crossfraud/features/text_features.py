"""Interpretable, rule-based message features (no ML). All indicators here are DERIVED from
message text by rules; they are not ground truth and not copies of any label."""
from __future__ import annotations

import re
from urllib.parse import urlparse

import pandas as pd

BANK_HANDLES = ("okaxis", "oksbi", "okhdfcbank", "okicici", "ybl", "ibl", "axl", "paytm",
                "demobank", "examplebank", "testbank", "sandboxupi", "upi", "apl", "sbi", "hdfcbank", "icici", "axisbank", "pnb")
_BANK = "|".join(BANK_HANDLES)
# matches name@bank, NAME@BANK, "name @ bank" and "name at bank"
UPI_RE = re.compile(rf"\b([a-z0-9][a-z0-9._-]+)\s*(?:@|\bat\b)\s*({_BANK})\b", re.I)
AMOUNT_RE = re.compile(r"(?:rs\.?|inr|₹)\s*([0-9][0-9,]*(?:\.[0-9]+)?)", re.I)
PAY_VERB_RE = re.compile(r"\b(pay|send|transfer|deposit|remit)\b", re.I)
URL_RE = re.compile(r"(?i)\b(?:https?://|www\.)[^\s]+")

URGENCY_PATTERNS = [re.compile(p, re.I) for p in [
    r"\burgent(ly)?\b", r"\bimmediately\b", r"\basap\b", r"\bright now\b", r"\bhurry\b",
    r"\blast chance\b", r"\bfinal warning\b", r"\bexpires?\b", r"\blimited (slots|time|offer)\b",
    r"\b\d+\s*minutes? left\b", r"\bonly \d+ (minutes?|hours?|slots?)\b",
    r"\bwithin \d+ (minutes?|hours?)\b", r"\bact now\b", r"\bfilling fast\b",
    r"\bcloses tonight\b", r"\bvalid only today\b", r"\bdon'?t miss\b"]]

KEYWORDS = {  # category -> regex; value = number of matches in the message
    "kw_investment": r"\b(guarantee[sd]?|returns?|profits?|trading|risk[- ]free|invest(ment|ors?)?|double your money)\b",
    "kw_kyc_account": r"\b(kyc|account (?:will be )?(?:blocked|suspended)|verification (?:fee|charge)|suspended|otp)\b",
    "kw_prize": r"\b(lucky draw|lottery|prize|congratulations|you (?:have )?won)\b",
    "kw_job": r"\b(part-?time job|work from home|earn rs|per day|daily payout|prepaid task|commission|task fee)\b",
    "kw_secrecy": r"\b(do not share|don'?t tell|keep (?:this )?(?:a )?secret|confidential)\b",
    "kw_authority": r"\b(bank support|support desk|customer care|official|department|bank)\b",
    "kw_trust": r"\b(100% genuine|genuine|trusted|thousands|guaranteed|trust us)\b",
}
KEYWORDS = {k: re.compile(v, re.I) for k, v in KEYWORDS.items()}

SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "cutt.ly", "is.gd", "rb.gy", "shorturl.at"}
SUSPICIOUS_TLDS = {"xyz", "top", "click", "buzz", "loan", "work", "icu", "vip", "site", "online"}
RISK_WORDS = ("kyc", "verify", "prize", "claim", "secure", "update", "bonus", "refund", "lucky")


def normalize_upi(local: str, bank: str) -> str:
    return f"{local.lower()}@{bank.lower()}"


def extract_upi_ids(text: str) -> list[str]:
    return [normalize_upi(m.group(1), m.group(2)) for m in UPI_RE.finditer(text)]


def extract_amounts(text: str) -> list[float]:
    return [float(m.group(1).replace(",", "")) for m in AMOUNT_RE.finditer(text)]


def analyse_url(url: str) -> tuple[str, list[str]]:
    u = url.rstrip(".,);!?")
    try:
        parsed = urlparse(u if "://" in u else "http://" + u)
        host = (parsed.hostname or "").lower()
    except ValueError:
        return "", ["malformed_url"]
    flags = []
    if host in SHORTENERS:
        flags.append("shortener")
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
        flags.append("ip_host")
    if host.rsplit(".", 1)[-1] in SUSPICIOUS_TLDS:
        flags.append("suspicious_tld")
    if any(w in host for w in RISK_WORDS):
        flags.append("risk_keyword_in_host")
    if u.lower().startswith("http://"):
        flags.append("no_https")
    return host, flags


def clean_text(text: str) -> str:
    """TF-IDF-ready text: lowercase, entities replaced by placeholder tokens, punctuation removed."""
    t = text.lower()
    t = URL_RE.sub(" urltoken ", t)
    t = UPI_RE.sub(" upitoken ", t)
    t = AMOUNT_RE.sub(" amttoken ", t)
    t = re.sub(r"\d+", " numtoken ", t)
    t = re.sub(r"[^a-z\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def message_features(text: str) -> dict:
    text = text or ""
    upis, amounts = extract_upi_ids(text), extract_amounts(text)
    urls = URL_RE.findall(text)
    all_flags: list[str] = []
    for u in urls:
        all_flags += analyse_url(u)[1]
    hits = sum(1 for p in URGENCY_PATTERNS if p.search(text))
    kw = {k: len(rx.findall(text)) for k, rx in KEYWORDS.items()}
    letters = [c for c in text if c.isalpha()]
    return {
        "has_payment_request": int(bool(upis) or (bool(PAY_VERB_RE.search(text)) and bool(amounts))),
        "extracted_upi": upis[0] if upis else "",
        "extracted_upi_ids": "|".join(dict.fromkeys(upis)),
        "extracted_amount": amounts[0] if amounts else float("nan"),
        "urgency_hits": hits,
        "has_urgency": int(hits > 0),
        "has_link": int(bool(urls)),
        "suspicious_link": int(bool(all_flags)),
        "link_risk_flags": "|".join(dict.fromkeys(all_flags)),
        **kw,
        "suspicious_kw_count": sum(kw.values()),
        "msg_length_chars": len(text),
        "exclamation_count": text.count("!"),
        "uppercase_ratio": (sum(c.isupper() for c in letters) / len(letters)) if letters else 0.0,
        "text_clean": clean_text(text),
    }


def enrich_messages(df: pd.DataFrame) -> pd.DataFrame:
    feats = pd.DataFrame([message_features(t) for t in df["message"].fillna("").astype(str)], index=df.index)
    return pd.concat([df, feats], axis=1)
