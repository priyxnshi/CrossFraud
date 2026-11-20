"""Local prototype entry points. Run the Phase 1 data pipeline with the phase1 subcommand."""
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

import pandas as pd

from crossfraud.data.db import load_sqlite
from crossfraud.data.public_adapters import adapt_sms_spam
from crossfraud.data.synthetic import SynthConfig, generate
from crossfraud.data.ingestion import ingest
from crossfraud.features.pipeline import run_features
from crossfraud.io import (PROCESSED_TABLES, RAW_TABLES, dirs, load_tables,
                           write_tables)


def cmd_generate(a):
    options = json.loads(Path(a.config).read_text(encoding="utf-8-sig")) if a.config else {}
    if a.seed is not None:
        options["seed"] = a.seed
    if "start" in options:
        options["start"] = datetime.fromisoformat(options["start"])
    config = SynthConfig(**options)
    raw, truth = generate(config)
    d = dirs(a.data_dir)
    write_tables({"user_profiles": raw.pop("user_profiles")}, d["profiles"])
    write_tables(raw, d["raw"])
    write_tables(truth, d["truth"])
    manifest = {"source": "synthetic", "source_version": "synthetic-v2",
                "configuration": asdict(config)}
    (d["raw"].parent / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    print("SYNTHETIC DATA generated (no real Telegram/banking data).")
    print(f"  users={len(raw['users'])}  conversations={len(raw['conversations'])}  "
          f"messages={len(raw['messages'])}  transactions={len(raw['transactions'])}")
    print(f"  scam conversations={int(truth['conversation_truth']['is_scam'].sum())}  "
          f"fraud transactions={int(truth['transaction_truth']['fraud_label'].sum())}")
    print(f"  raw -> {d['raw']}   ground truth (evaluation only) -> {d['truth']}")


def cmd_validate(a) -> bool:
    d = dirs(a.data_dir)
    rep = ingest(a.data_dir, getattr(a, 'ingested_at_utc', None))
    print(rep.summary())
    print(f"  report -> {d['reports'] / 'validation_report.json'}")
    return rep.ok


def cmd_features(a):
    out = run_features(a.data_dir)
    d = dirs(a.data_dir)
    for k, v in out.items():
        print(f"  {k}: {v.shape[0]} rows x {v.shape[1]} cols -> {d['processed'] / (k + '.csv')}")
    summary = {k: {"rows": int(v.shape[0]), "cols": list(v.columns)} for k, v in out.items()}
    (d["reports"]).mkdir(parents=True, exist_ok=True)
    (d["reports"] / "feature_summary.json").write_text(json.dumps(summary, indent=2))


def cmd_db(a):
    d = dirs(a.data_dir)
    tables = load_tables(d["raw"], RAW_TABLES)
    tables.update({k: pd.read_csv(d["processed"] / f"{k}.csv") for k in PROCESSED_TABLES})
    load_sqlite(tables, f"{a.data_dir}/crossfraud.db")
    print(f"SQLite written -> {a.data_dir}/crossfraud.db")


def cmd_adapt_sms(a):
    df = adapt_sms_spam(a.input)
    d = dirs(a.data_dir)
    write_tables({"public_sms_messages": df.drop(columns="spam_label")}, d["external"])
    write_tables({"public_sms_labels": df[["message_id", "spam_label", "data_source"]]},
                 d["external"] / "ground_truth")
    print(f"Adapted {len(df)} public SMS rows -> {d['external'] / 'public_sms_messages.csv'}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m crossfraud.cli")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ["generate", "validate", "ingest", "phase1", "phase2", "phase3", "features", "db", "all", "adapt-sms",
                 "train-messaging", "train-payment", "train", "demo"]:
        p = sub.add_parser(name)
        legacy = name in {"train-messaging", "train-payment", "train", "demo"}
        p.add_argument("--data-dir", default="data" if legacy else "data/phase1")
        if name in ("generate", "all", "phase1"):
            p.add_argument("--seed", type=int)
            p.add_argument("--config")
        if name in ("phase2", "phase3"):
            p.add_argument("--seed", type=int, default=42)
            p.add_argument("--use-cleaned", action="store_true")
        if name == "ingest":
            p.add_argument("--ingested-at-utc", help="Explicit synthetic replay timestamp for reproducible exports")
        if name == "phase3":
            p.add_argument("--window-minutes", type=float, default=180)
            p.add_argument("--amount-fraction", type=float, default=0.10)
            p.add_argument("--amount-floor-inr", type=float, default=10)
            p.add_argument("--minimum-confidence", type=float, default=0.75)
            p.add_argument("--ambiguity-margin", type=float, default=0.06)
        if name == "adapt-sms":
            p.add_argument("--input", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "generate":
        cmd_generate(a)
    elif a.cmd in ("validate", "ingest"):
        raise SystemExit(0 if cmd_validate(a) else 1)
    elif a.cmd == "phase1":
        cmd_generate(a)
        raise SystemExit(0 if cmd_validate(a) else 1)
    elif a.cmd == "phase2":
        from crossfraud.models.phase2 import run
        run(a.data_dir, a.seed, use_cleaned=a.use_cleaned)
        print(f"Phase 2 evaluation -> {a.data_dir}/reports/phase2_evaluation.json")
    elif a.cmd == "phase3":
        from crossfraud.models.correlation import MatchConfig
        from crossfraud.models.phase3 import run
        config = MatchConfig(a.window_minutes, a.amount_fraction, a.amount_floor_inr,
                             a.minimum_confidence, a.ambiguity_margin)
        run(a.data_dir, a.seed, config, use_cleaned=a.use_cleaned)
        print(f"Phase 3 evaluation -> {a.data_dir}/reports/phase3_evaluation.json")
    elif a.cmd == "features":
        cmd_features(a)
    elif a.cmd == "db":
        cmd_db(a)
    elif a.cmd == "adapt-sms":
        cmd_adapt_sms(a)
    elif a.cmd in ("train-messaging", "train-payment", "train"):
        from crossfraud.models.cli_train import run
        run(a.cmd, a.data_dir)
    elif a.cmd == "demo":
        from crossfraud.models.demo import run_demo
        run_demo(a.data_dir)
    else:  # all
        cmd_generate(a)
        if not cmd_validate(a):
            raise SystemExit(1)
        cmd_features(a)
        cmd_db(a)


if __name__ == "__main__":
    main()
