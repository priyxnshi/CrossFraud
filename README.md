# Cross-platform fraud research prototype

This local prototype studies whether conversational evidence can flag risk before a related UPI attempt and whether payment evidence improves later human review. Phase 1 uses a configurable synthetic simulation of Indian messaging and payment activity. Its results establish pipeline behavior only.

## Phase READMEs

| Phase | Status |
| --- | --- |
| [Phase 1 — Synthetic dataset and validation](README_PHASE1.md) | Complete |
| [Phase 2 — Separate messaging and UPI models](README_PHASE2.md) | Complete |
| [Phase 3 — Correlation and early-warning evaluation](README_PHASE3.md) | Complete |
| [Phase 4 — Reproducibility and review demo](README_PHASE4.md) | Complete |


## Run Phase 1

From this project directory using Python 3.10 or later:

```powershell
python -m pip install -r requirements.txt
python -m crossfraud.cli phase1 --seed 42
python -m pytest -q
```

The existing Windows environment can be used with `.venv/Scripts/python.exe` in place of `python`. `phase1` generates source tables and runs ingestion, with output in `data/phase1/`. Use `--data-dir` to choose another directory, and `--config` to supply a JSON generator configuration. `ingest` or `validate` reruns source validation and normalization. Check `reports/validation_report.json` and the cleaned completion manifest. The existing `features` command can check observation-only transformation, and `all` also runs the legacy feature and SQLite workflow. Full-conversation features are retrospective until an alert-time cutoff is implemented.

- [Project audit and checklist](docs/PROJECT_PLAN.md)
- [Data dictionary and population assumptions](docs/DATA_DICTIONARY.md)
- [Research protocol and review workflow](docs/RESEARCH_PROTOCOL.md)

## Run Phase 2

`python -m crossfraud.cli phase2 --data-dir data/phase1 --seed 42` trains the separate messaging and UPI models using the Phase 1 v2 dataset and writes local artifacts. [Phase 2 implementation, results and next phase](docs/PHASE2_EVALUATION.md)

## Run Phase 3

`python -m crossfraud.cli phase3 --data-dir data/phase1 --seed 42` runs the local held-out replay and writes synthetic matching metrics and example review alerts. [Phase 3 implementation and results](README_PHASE3.md)


## Run Phase 4

The local DVC pipeline regenerates the synthetic dataset, trains the separate models, evaluates cross-platform alerts, and records the run. The loopback review API displays synthetic evidence and saves reviewer decisions in SQLite. [Phase 4 setup, commands and verification](README_PHASE4.md)


## Legacy prototype

The preserved `data/` root contains older artifacts and reports from the original simulation, including messaging and payment model experiments. The legacy `train*` and `demo` commands still default to that root. The v2 Phase 1 data has separate target tables. Use the Phase 2 command above for v2 supervised loading and evaluation. [Legacy feature notes](FEATURES.md)

## Enterprise review website

From the project root, start the local synthetic website:

```powershell
python -m crossfraud.review_api --data-dir data/pipeline --port 8768
```

Open `http://127.0.0.1:8768/` for the landing page or `http://127.0.0.1:8768/#overview` for the analyst dashboard. The app uses the existing Python API and SQLite review history. The root route serves the website and `/alerts` serves the original JSON interface. The frontend is in [review_web](crossfraud/review_web), and the [synthetic catalog](crossfraud/review_catalog.py) supplies masked payment account references and redacted chat evidence.

The workspace uses the saved alert replay and prototype evaluation. Dataset totals describe the synthetic catalog. Alert charts describe the saved alert examples. The application uses a local demo profile, and the Sign In link opens that profile. Investigation notes and review decisions remain in the local review database.

### Hosted synthetic demo

The Vercel build runs `node deploy/build.mjs` and serves the resulting `public/` directory. It uses the checked-in synthetic snapshot at `deploy/demo.json`. On the hosted demo, investigation notes and decisions are stored in the visitor's browser. The local Python app continues to use SQLite.

To refresh the hosted snapshot after a synthetic replay, run `python -m scripts.export_web_demo` from the repository root. The export starts with empty review histories and does not read the local review database.
