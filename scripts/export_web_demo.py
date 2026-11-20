"""Export the synthetic-only inputs for the public browser demo."""
import argparse
import hashlib
import json
from pathlib import Path

from crossfraud.review_catalog import DemoCatalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data/pipeline"))
    args = parser.parse_args()
    catalog = DemoCatalog(args.data_dir)
    index = catalog.index()
    evaluation = index["evaluation"]
    if evaluation.get("source") != "synthetic":
        raise ValueError("Only synthetic evaluation outputs may be exported")
    index["evaluation"] = {key: evaluation[key] for key in ("methods", "matching", "partitions")}
    source = args.data_dir / "reports" / "phase3_alert_examples.json"
    alerts = json.loads(source.read_text(encoding="utf-8"))
    if any(alert.get("schema_version") != "phase3-alert-v1" for alert in alerts):
        raise ValueError("Unexpected alert schema")
    display_alerts = [{"alert_id": hashlib.sha256(json.dumps(alert, sort_keys=True).encode()).hexdigest()[:20],
                       **alert, "review_outcome": "unresolved", "review_history": []} for alert in alerts]
    details = catalog.conversation_details()
    payload = {"catalog": index, "alerts": display_alerts, "conversations": details}
    target = Path("deploy/demo.json")
    target.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False) + "\n",
                      encoding="utf-8")
    print(f"Exported {len(details)} synthetic conversations and {len(alerts)} alerts")


if __name__ == "__main__":
    main()
