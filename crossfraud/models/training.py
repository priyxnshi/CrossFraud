"""Phase 2 training + evaluation. Every number in the reports is computed from the Phase 1 dataset."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score
from sklearn.model_selection import StratifiedKFold, cross_val_predict, train_test_split

from crossfraud.io import RAW_TABLES, dirs, load_tables, to_typed
from crossfraud.models.contract import risk_level
from crossfraud.models.messaging import (ALL_STRUCT_COLS, CONTENT_COLS, TIMING_COLS, VARIANTS, MessagingModel, build_messaging_frame,
                                         make_pipeline)
from crossfraud.models.metrics import best_f1_threshold, binary_metrics, bootstrap_ci
from crossfraud.models.probes import run_probes
from crossfraud.models.payment import (KINDS, PAYMENT_FEATURES, PaymentModel, build_payment_frame,
                                       make_estimator)


def _y(frame, col):
    return pd.to_numeric(frame[col], errors="coerce").astype(int).to_numpy()


def _per_scenario(df, scores, label_col, thr):
    d = df[["scenario", label_col]].copy()
    d["score"], d["flagged"] = scores, (np.asarray(scores) >= thr).astype(int)
    g = d.groupby("scenario").agg(n=("score", "size"), label=(label_col, "max"),
                                  mean_score=("score", "mean"), flagged_rate=("flagged", "mean"))
    return {k: {"n": int(v.n), "label": int(v.label), "mean_score": round(float(v.mean_score), 4),
                "flagged_rate": round(float(v.flagged_rate), 4)} for k, v in g.iterrows()}


# =============================== MESSAGING ====================================================
def temporal_split(frame: pd.DataFrame, train_frac: float = 0.7):
    """Earlier transactions train, later ones test (no future information in training)."""
    f = frame.sort_values(["timestamp", "transaction_id"]).reset_index(drop=True)
    cut = int(len(f) * train_frac)
    return f.iloc[:cut], f.iloc[cut:]


def benign_split(frame: pd.DataFrame, seed: int = 42):
    benign = frame[frame["scam_label"].astype(int) == 0]
    return train_test_split(benign.index, test_size=0.3, stratify=benign["scenario"], random_state=seed)


def scenario_holdout_indices(frame: pd.DataFrame, held_out: str, benign_train, benign_test):
    """Leave-one-scam-scenario-out: the held-out scam type never appears in training."""
    is_scam = frame["scam_label"].astype(int) == 1
    test_idx = list(frame.index[frame["scenario"] == held_out]) + list(benign_test)
    train_idx = list(frame.index[is_scam & (frame["scenario"] != held_out)]) + list(benign_train)
    return train_idx, test_idx


def evaluate_messaging(frame: pd.DataFrame, seed: int = 42) -> dict:
    y_all = _y(frame, "scam_label")
    res = {"protocols": {
        "random_split": "70/30 split stratified by scenario (optimistic: same templates in train and test)",
        "leave_one_scam_scenario_out": "train on 3 scam scenarios + 70% of benign; test on the unseen "
                                       "scam scenario + the held-out 30% of benign (stricter)"}}

    tr_i, te_i = train_test_split(frame.index, test_size=0.3, stratify=frame["scenario"], random_state=seed)
    tr, te = frame.loc[tr_i], frame.loc[te_i]
    res["random_split"] = {"n_train": len(tr), "n_test": len(te), "variants": {}}
    for v in VARIANTS:
        m = MessagingModel(v, seed=seed).fit(tr, _y(tr, "scam_label"))
        s = m.predict_proba_frame(te)
        entry = {"metrics": binary_metrics(_y(te, "scam_label"), s, 0.5)}
        if v == "combined":
            entry["bootstrap_95ci"] = bootstrap_ci(_y(te, "scam_label"), s, 0.5, seed=seed)
            entry["per_scenario"] = _per_scenario(te, s, "scam_label", 0.5)
        res["random_split"]["variants"][v] = entry

    b_tr, b_te = benign_split(frame, seed)
    scam_scen = sorted(frame.loc[frame["scam_label"].astype(int) == 1, "scenario"].unique())
    loso = {v: {} for v in VARIANTS}
    for s_out in scam_scen:
        train_idx, test_idx = scenario_holdout_indices(frame, s_out, b_tr, b_te)
        trn, tst = frame.loc[train_idx], frame.loc[test_idx]
        for v in VARIANTS:
            m = MessagingModel(v, seed=seed).fit(trn, _y(trn, "scam_label"))
            loso[v][s_out] = binary_metrics(_y(tst, "scam_label"), m.predict_proba_frame(tst), 0.5)
    res["leave_one_scam_scenario_out"] = {"held_out_scenarios": scam_scen, "variants": {}}
    for v in VARIANTS:
        folds = loso[v]
        mean = {k: float(np.mean([f[k] for f in folds.values()])) for k in ("precision", "recall", "f1", "roc_auc")}
        res["leave_one_scam_scenario_out"]["variants"][v] = {"folds": folds, "mean": mean}

    cov = {c: int((frame[c] > 0).sum()) for c in
           ["n_payment_request_msgs", "n_urgency_msgs", "n_suspicious_link_msgs", "n_credential_request_msgs",
            "n_persuasion_msgs"]}
    res["feature_coverage_conversations_with_signal"] = cov
    return res


def run_messaging(data_dir: str = "data", seed: int = 42) -> dict:
    d = dirs(data_dir)
    mdir = Path(data_dir) / "models"
    raw = to_typed(load_tables(d["raw"], RAW_TABLES))
    frame = build_messaging_frame(raw, d["truth"])
    ev = evaluate_messaging(frame, seed)

    y = _y(frame, "scam_label")
    model = MessagingModel("combined", seed=seed).fit(frame, y)
    model.save(mdir / "messaging_model.joblib")
    ev["top_features"] = model.top_features(15)
    ev["out_of_template_probe"] = run_probes(model)
    ev["model"] = {"name": model.name, "threshold": model.threshold, "n_train": len(frame),
                   "content_features": CONTENT_COLS, "timing_features_ablation_only": TIMING_COLS}

    oof = cross_val_predict(make_pipeline("combined", seed=seed), frame, y,
                            cv=StratifiedKFold(5, shuffle=True, random_state=seed), method="predict_proba")[:, 1]
    conv_end = raw["conversations"][["conversation_id", "end_ts"]]
    out = frame[["conversation_id", "first_payment_request_upi", "first_payment_request_amount",
                 "first_payment_request_ts"]].merge(conv_end, on="conversation_id")
    out["risk_score_oof"] = oof
    out["risk_level"] = [risk_level(s, model.threshold) for s in oof]
    out["predicted_class"] = (oof >= model.threshold).astype(int)
    out["scam_label"] = y
    out = out.rename(columns={"end_ts": "conversation_end_ts"})
    d["processed"].mkdir(parents=True, exist_ok=True)
    out.to_csv(d["processed"] / "scores_messaging_oof.csv", index=False)
    ev["oof_metrics_all_conversations"] = binary_metrics(y, oof, model.threshold)

    d["reports"].mkdir(parents=True, exist_ok=True)
    (d["reports"] / "phase2_messaging_eval.json").write_text(json.dumps(ev, indent=2))
    return ev


# =============================== PAYMENT ======================================================
def _oof(kind, X, y, seed):
    return cross_val_predict(make_estimator(kind, seed), X, y,
                             cv=StratifiedKFold(5, shuffle=True, random_state=seed), method="predict_proba")[:, 1]


def _eval_split(train, test, seed):
    Xtr, ytr, Xte, yte = train[PAYMENT_FEATURES], _y(train, "fraud_label"), test[PAYMENT_FEATURES], _y(test, "fraud_label")
    out = {"n_train": len(train), "n_train_fraud": int(ytr.sum()), "n_test": len(test),
           "n_test_fraud": int(yte.sum()), "models": {}}
    out["models"]["rule_new_beneficiary_high_amount"] = {
        "metrics_at_0.5": binary_metrics(yte, test["new_beneficiary_high_amount"].to_numpy(), 0.5)}
    for kind in KINDS:
        oof = _oof(kind, Xtr, ytr, seed)
        thr, oof_f1 = best_f1_threshold(ytr, oof)
        m = PaymentModel(kind, seed=seed).fit(train, ytr)
        s = m.predict_proba_frame(test)
        out["models"][kind] = {
            "train_oof_pr_auc": float(average_precision_score(ytr, oof)),
            "chosen_threshold_from_train_oof": thr, "train_oof_f1_at_threshold": oof_f1,
            "metrics_at_0.5": binary_metrics(yte, s, 0.5),
            "metrics_at_chosen_threshold": binary_metrics(yte, s, thr),
            "bootstrap_95ci_at_chosen_threshold": bootstrap_ci(yte, s, thr, seed=seed)}
        if "scenario" in test.columns:
            out["models"][kind]["per_scenario_at_chosen_threshold"] = _per_scenario(test, s, "fraud_label", thr)
    return out


def evaluate_payment(frame: pd.DataFrame, seed: int = 42) -> dict:
    f = frame.sort_values(["timestamp", "transaction_id"]).reset_index(drop=True)
    train_t, test_t = temporal_split(f)
    res = {"protocols": {
        "temporal_split": "first 70% of transactions by time = train, last 30% = test (primary; mimics deployment)",
        "random_split": "stratified 70/30 random split (secondary; optimistic)"},
        "fraud_rate_overall": float(_y(f, "fraud_label").mean())}
    res["temporal_split"] = _eval_split(train_t, test_t, seed)
    res["temporal_split"]["train_period"] = [str(train_t["timestamp"].iloc[0]), str(train_t["timestamp"].iloc[-1])]
    res["temporal_split"]["test_period"] = [str(test_t["timestamp"].iloc[0]), str(test_t["timestamp"].iloc[-1])]
    tr_i, te_i = train_test_split(f.index, test_size=0.3, stratify=_y(f, "fraud_label"), random_state=seed)
    res["random_split"] = _eval_split(f.loc[tr_i], f.loc[te_i], seed)
    return res


def run_payment(data_dir: str = "data", seed: int = 42) -> dict:
    d = dirs(data_dir)
    mdir = Path(data_dir) / "models"
    raw = to_typed(load_tables(d["raw"], RAW_TABLES))
    frame = build_payment_frame(raw, d["truth"])
    ev = evaluate_payment(frame, seed)

    X, y = frame[PAYMENT_FEATURES], _y(frame, "fraud_label")
    meta, scores = {"thresholds": {}, "oof_pr_auc": {}}, {}
    for kind in KINDS:
        oof = _oof(kind, X, y, seed)
        thr, _ = best_f1_threshold(y, oof)
        m = PaymentModel(kind, threshold=thr, seed=seed).fit(frame, y)
        m.save(mdir / f"payment_{kind}.joblib")
        meta["thresholds"][kind] = thr
        meta["oof_pr_auc"][kind] = float(average_precision_score(y, oof))
        scores[kind] = oof
        ev.setdefault("global_importance", {})[kind] = m.global_importance(10)
    active = max(meta["oof_pr_auc"], key=meta["oof_pr_auc"].get)
    meta["active"] = active
    meta["active_selected_by"] = "highest out-of-fold PR-AUC on all transactions (not on the test split)"
    (mdir / "payment_meta.json").write_text(json.dumps(meta, indent=2))
    ev["final_models"] = meta

    out = frame[["transaction_id", "sender_id", "receiver_id", "timestamp", "amount"]].copy()
    out["risk_score_logreg_oof"], out["risk_score_random_forest_oof"] = scores["logreg"], scores["random_forest"]
    out["risk_score_oof"] = scores[active]
    thr = meta["thresholds"][active]
    out["risk_level"] = [risk_level(s, thr) for s in scores[active]]
    out["predicted_class"] = (scores[active] >= thr).astype(int)
    out["fraud_label"] = y
    d["processed"].mkdir(parents=True, exist_ok=True)
    out.to_csv(d["processed"] / "scores_payment_oof.csv", index=False)

    d["reports"].mkdir(parents=True, exist_ok=True)
    (d["reports"] / "phase2_payment_eval.json").write_text(json.dumps(ev, indent=2))
    return ev


def load_payment_model(data_dir: str = "data", kind: str | None = None) -> PaymentModel:
    mdir = Path(data_dir) / "models"
    kind = kind or json.loads((mdir / "payment_meta.json").read_text())["active"]
    return PaymentModel.load(mdir / f"payment_{kind}.joblib")


def load_messaging_model(data_dir: str = "data") -> MessagingModel:
    return MessagingModel.load(Path(data_dir) / "models" / "messaging_model.joblib")


# =============================== REPORT =======================================================
def _row(name, m):
    cm = m["confusion_matrix"]
    f = lambda x: "n/a" if x is None else f"{x:.3f}"
    return (f"| {name} | {f(m['precision'])} | {f(m['recall'])} | {f(m['f1'])} | {f(m['roc_auc'])} | "
            f"{f(m['pr_auc'])} | {cm['tn']} / {cm['fp']} / {cm['fn']} / {cm['tp']} |")


def write_markdown_report(data_dir: str = "data") -> Path:
    d = dirs(data_dir)
    msg = json.loads((d["reports"] / "phase2_messaging_eval.json").read_text())
    pay = json.loads((d["reports"] / "phase2_payment_eval.json").read_text())
    hdr = ("| Model | Precision | Recall | F1 | ROC-AUC | PR-AUC | TN / FP / FN / TP |\n"
           "|---|---|---|---|---|---|---|")
    L = ["# Phase 2 evaluation (generated from the synthetic Phase 1 dataset)", "",
         "All numbers come from `data/reports/phase2_*_eval.json`. The data is simulated from templates; "
         "treat these as pipeline-validation results, not real-world performance.", "",
         "## A. Messaging model", "", "### Random split (optimistic)", "", hdr]
    for v, e in msg["random_split"]["variants"].items():
        L.append(_row(v, e["metrics"]))
    L += ["", "### Leave-one-scam-scenario-out (stricter): mean over 4 held-out scenarios", "",
          "| Variant | Precision | Recall | F1 | ROC-AUC |", "|---|---|---|---|---|"]
    for v, e in msg["leave_one_scam_scenario_out"]["variants"].items():
        m = e["mean"]
        L.append(f"| {v} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | {m['roc_auc']:.3f} |")
    pr = msg["out_of_template_probe"]
    L += ["", "### Out-of-template probe (13 hand-written conversations; illustrative, not a benchmark)", "",
          f"- scam probes flagged by the model: {pr['scam_flagged_by_model']}",
          f"- scam probes with at least one rule signal: {pr['scam_with_any_rule_signal']}",
          f"- benign probes flagged by the model: {pr['benign_flagged_by_model']}", "",
          "| Probe | Label | Model score | Class | Rule signals |", "|---|---|---|---|---|"]
    for r in pr["items"]:
        L.append(f"| {r['name']} | {r['label']} | {r['risk_score']:.3f} | {r['predicted_class']} | "
                 f"{', '.join(r['rule_signals']) or '-'} |")
    L += ["", "### Payment model", "", f"Overall fraud rate: {pay['fraud_rate_overall']:.4f}", ""]
    for proto in ("temporal_split", "random_split"):
        p = pay[proto]
        L += [f"#### {proto} (train {p['n_train']} / {p['n_train_fraud']} fraud; test {p['n_test']} / "
              f"{p['n_test_fraud']} fraud)", "", hdr]
        for k, e in p["models"].items():
            if k.startswith("rule"):
                L.append(_row(k + " (@0.5)", e["metrics_at_0.5"]))
            else:
                L.append(_row(f"{k} (@0.5)", e["metrics_at_0.5"]))
                L.append(_row(f"{k} (@chosen {e['chosen_threshold_from_train_oof']:.3f})",
                              e["metrics_at_chosen_threshold"]))
        L.append("")
    path = d["reports"] / "phase2_evaluation.md"
    path.write_text("\n".join(L))
    return path
