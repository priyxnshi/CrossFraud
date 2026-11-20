"""Run two actual DVC replays and compare generated artifacts on this runtime."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "pipeline"
TRACKED = ("raw", "profiles", "ground_truth", "cleaned", "processed", "phase2_models", "reports")


def outputs():
    files = [DATA / "dataset_manifest.json", DATA / "tracking" / "latest.json"]
    for name in TRACKED:
        paths = sorted(path for path in (DATA / name).rglob("*") if path.is_file())
        if not paths:
            raise SystemExit(f"Missing stage outputs under {name}")
        files.extend(paths)
    validation = json.loads((DATA / "reports" / "validation_report.json").read_text(encoding="utf-8"))
    if not validation["ok"]:
        raise SystemExit("DVC produced a rejected dataset")
    return {str(path.relative_to(DATA)): hashlib.sha256(path.read_bytes()).hexdigest() for path in files}


def main():
    venv_bin = str(Path(sys.executable).resolve().parent)
    env = {**os.environ, "DVC_NO_ANALYTICS": "true",
           "PATH": venv_bin + os.pathsep + os.environ.get("PATH", "")}
    env.setdefault("DVC_SITE_CACHE_DIR", str(ROOT / ".dvc" / "site-cache"))
    checks = []
    for _ in range(2):
        subprocess.run([sys.executable, "-m", "dvc", "repro", "--force", "--no-run-cache"],
                       cwd=ROOT, env=env, check=True)
        checks.append(outputs())
    changed = [name for name in checks[0].keys() | checks[1].keys()
               if checks[0].get(name) != checks[1].get(name)]
    if changed:
        raise SystemExit("Replay outputs differed: " + ", ".join(sorted(changed)))
    print(f"Verified {len(checks[0])} pipeline artifacts byte for byte across two uncached replays.")


if __name__ == "__main__":
    main()
