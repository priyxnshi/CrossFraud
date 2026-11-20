import math

from crossfraud.features.text_features import (analyse_url, clean_text, extract_amounts,
                                               extract_upi_ids, message_features)


def test_upi_normalisation_variants():
    assert extract_upi_ids("pay support00@okaxis now") == ["support00@okaxis"]
    assert extract_upi_ids("pay SUPPORT00@OKAXIS now") == ["support00@okaxis"]
    assert extract_upi_ids("pay support00 @ okaxis now") == ["support00@okaxis"]
    assert extract_upi_ids("pay support00 at okaxis now") == ["support00@okaxis"]
    assert extract_upi_ids("meet me at the office") == []


def test_amounts():
    assert extract_amounts("Send Rs 9,999 now") == [9999.0]
    assert extract_amounts("fee is Rs. 499.50") == [499.5]
    assert extract_amounts("no amount here") == []


def test_payment_request_and_urgency():
    f = message_features("Limited slots, only 10 minutes left! Pay Rs 999 to earn01@ybl now.")
    assert f["has_payment_request"] == 1 and f["has_urgency"] == 1 and f["extracted_amount"] == 999.0
    g = message_features("Let's meet for lunch tomorrow")
    assert g["has_payment_request"] == 0 and g["has_urgency"] == 0 and math.isnan(g["extracted_amount"])


def test_suspicious_links():
    assert analyse_url("https://bit.ly/3xAb12")[1] == ["shortener"]
    assert "ip_host" in analyse_url("http://103.21.58.7/verify")[1]
    assert {"suspicious_tld", "risk_keyword_in_host", "no_https"} <= set(analyse_url("http://kyc-verify-sbi.xyz/update")[1])
    assert analyse_url("https://www.youtube.com/watch?v=abc")[1] == []
    assert message_features("see https://github.com/x/y")["suspicious_link"] == 0
    assert message_features("click http://prize-claim.top/win")["suspicious_link"] == 1


def test_clean_text_placeholders():
    t = clean_text("Pay Rs 999 to Foo@YBL at http://x.xyz/a NOW!!")
    assert "amttoken" in t and "upitoken" in t and "urltoken" in t and "!" not in t
