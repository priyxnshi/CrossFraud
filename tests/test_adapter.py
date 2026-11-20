from crossfraud.data.public_adapters import adapt_sms_spam
from crossfraud.schemas import MESSAGE_COLS


def test_sms_adapter_format_fixture(tmp_path):
    # 3-row FORMAT fixture (made up for this test; NOT the real public dataset)
    p = tmp_path / "sms.tsv"
    p.write_text("ham\tsee you at 5\nspam\tYou won a prize! call now\nham\tok\n")
    df = adapt_sms_spam(str(p))
    assert list(df.columns) == [*MESSAGE_COLS, "spam_label"]
    assert df["spam_label"].tolist() == [0, 1, 0]
    assert df["data_source"].str.startswith("public:").all()
