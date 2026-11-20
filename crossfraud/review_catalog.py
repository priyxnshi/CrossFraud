"""Read-only display catalog for the synthetic review web app."""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

_ADDRESS = re.compile(r"\b[\w.-]+\s*(?:@|\bat\b|\[at\]|\(at\))\s*(?:demo\w+|examplebank|test\w+|sandbox\w+|ok\w+|ybl|upi|paytm|ibl)\b", re.I)
_URL = re.compile(r"https?://[^\s]+", re.I)


def _reference(value):
    return "REF-" + hashlib.sha256(value.encode()).hexdigest()[:8].upper()


class DemoCatalog:
    def __init__(self, root):
        self.root = Path(root)

    def rows(self, layer, name):
        path = self.root / layer / (name + ".csv")
        if not path.exists():
            return []
        with path.open(encoding="utf-8-sig", newline="") as stream:
            return [row for row in csv.DictReader(stream) if row.get("data_source") == "synthetic"]

    def index(self):
        conversations = self.rows("raw", "conversations")
        payments = self.rows("raw", "transactions")
        profiles = self.rows("profiles", "user_profiles")
        categories = {row["conversation_id"]: row
                      for row in self.rows("ground_truth", "conversation_truth")}
        return {
            "source": "synthetic",
            "conversations": [{"id": row["conversation_id"], "platform": row["platform"],
                               "start": row["start_ts"], "category": categories.get(row["conversation_id"], {}).get("scenario"),
                               "scenario_is_scam": categories.get(row["conversation_id"], {}).get("is_scam") == "1"}
                              for row in conversations],
            "payments": [self.payment(row) for row in payments],
            "coverage": {key: Counter(row[key] for row in profiles) for key in ("primary_language", "region")},
            "evaluation": json.loads((self.root / "reports" / "phase3_evaluation.json").read_text(encoding="utf-8")),
        }

    @staticmethod
    def payment(row):
        return {"id": row["transaction_id"], "type": row["transaction_type"], "amount": float(row["amount"]),
                "status": row["status_at_event"], "timestamp": row["timestamp"],
                "sender": _reference(row["sender_id"]), "receiver": _reference(row["receiver_id"])}

    def conversation(self, entity, cutoff=None):
        row = next((row for row in self.rows("raw", "conversations") if row["conversation_id"] == entity), None)
        if row is None:
            return None
        return self._conversation(row, self.rows("raw", "messages"), cutoff)

    @staticmethod
    def _conversation(row, rows, cutoff=None):
        entity = row["conversation_id"]
        messages = []
        for item in rows:
            if item["conversation_id"] != entity or (cutoff is not None and item["timestamp"] > cutoff):
                continue
            original = item["message"]
            indicators = []
            if _ADDRESS.search(original):
                indicators.append("UPI reference")
            if _URL.search(original):
                indicators.append("URL reference")
            if re.search(r"\b(?:otp|pin|password|cvv)\b", original, re.I):
                indicators.append("Credential reference")
            text = _URL.sub("[URL redacted]", _ADDRESS.sub("[UPI reference redacted]", original))
            messages.append({"time": item["timestamp"], "text": text,
                             "speaker": "Participant" if item["sender_id"] == row["participant_a"] else "Counterparty",
                             "indicators": indicators})
        return {"id": entity, "platform": row["platform"], "messages": messages}

    def conversation_details(self):
        """Build redacted conversation details in one pass for the static demo."""
        by_conversation = defaultdict(list)
        for message in self.rows("raw", "messages"):
            by_conversation[message["conversation_id"]].append(message)
        return {row["conversation_id"]: self._conversation(row, by_conversation[row["conversation_id"]])
                for row in self.rows("raw", "conversations")}
