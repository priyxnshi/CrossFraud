"""Write aggregate experiment records locally with no raw event or identifier fields."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import re
import subprocess

SCORE_KEYS = ("n", "n_positive", "precision", "recall", "f1", "pr_auc", "roc_auc", "threshold",
              "false_alerts_per_1000_events", "false_alerts_per_1000_cases")


def _sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _revision(project):
    try:
        revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=project, check=True,
                                  capture_output=True, text=True).stdout.strip()
        return revision if re.fullmatch(r"[a-f0-9]{40,64}", revision) else None
    except (OSError, subprocess.CalledProcessError):
        return None


def _metrics(record):
    return {key: record[key] for key in SCORE_KEYS if isinstance(record.get(key), (int, float))}


def record(data_dir, project=None):
    root = Path(data_dir)
    project = Path(project) if project else Path(__file__).resolve().parents[1]
    reports = root / "reports"
    manifest = _read(root / "dataset_manifest.json")
    cleaned = _read(root / "cleaned" / "manifest.json")
    phase2 = _read(reports / "phase2_evaluation.json")
    phase3 = _read(reports / "phase3_evaluation.json")
    if not (manifest.get("source") == phase2.get("data_source") == phase3.get("source") == "synthetic"):
        raise ValueError("Local tracking accepts the synthetic pipeline only")
    code = sorted((project / "crossfraud").rglob("*.py"))
    code.extend(path for name in ("dvc.yaml", "requirements-lock.txt", "config/synthetic.json")
                if (path := project / name).is_file())
    source = hashlib.sha256()
    for path in code:
        source.update(f"{path.relative_to(project).as_posix()}:{_sha(path)}\n".encode())
    links = phase3["matching"]
    models = {
        "messaging_combined_logreg": _sha(root / "phase2_models" / "messaging_combined_logreg.joblib"),
        "payment_logreg": _sha(root / "phase2_models" / "payment_logreg.joblib"),
        "payment_random_forest": _sha(root / "phase2_models" / "payment_random_forest.joblib"),
    }
    data = {
        "schema_version": 1, "source": "synthetic", "git_revision": _revision(project),
        "code_sha256": source.hexdigest(), "dataset_manifest_sha256": _sha(root / "dataset_manifest.json"),
        "source_table_sha256": cleaned["source_sha256"], "dataset_seed": int(manifest["configuration"]["seed"]),
        "evaluation_seed": {"phase2": int(phase2["seed"]), "phase3": int(phase3["seed"])},
        "dataset_version": manifest["source_version"],
        "evaluation_versions": {"phase2": phase2["version"], "phase3": phase3["version"]},
        "match_config": {key: value for key, value in phase3["config"].items() if isinstance(value, (int, float))},
        "libraries": {key: importlib.metadata.version(key) for key in ("pandas", "numpy", "scikit-learn", "joblib")},
        "model_sha256": models,
        "phase2_metrics": {
            modality: {name: _metrics(entry["test"]) for name, entry in
                       {"baseline": section["baseline"], **section["models"]}.items()}
            for modality, section in phase2["modalities"].items()
        },
        "phase3_metrics": {name: _metrics(entry["test"]) for name, entry in phase3["methods"].items()},
        "matching_metrics": {key: links[key] for key in ("attempts", "selected", "precision", "recall", "ambiguous")},
    }
    raw = json.dumps(data, sort_keys=True, allow_nan=False).encode()
    run_id = hashlib.sha256(raw).hexdigest()
    encoded = json.dumps({"run_id": run_id, **data}, indent=2, sort_keys=True, allow_nan=False) + "\n"
    tracking = root / "tracking"
    history = tracking / "runs"
    history.mkdir(parents=True, exist_ok=True)
    (history / f"{run_id}.json").write_text(encoded, encoding="utf-8")
    (tracking / "latest.json").write_text(encoded, encoding="utf-8")
    return run_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="data/pipeline")
    args = parser.parse_args()
    print(f"Local experiment ID {record(args.data_dir)}")
