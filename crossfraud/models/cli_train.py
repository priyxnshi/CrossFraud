"""CLI glue for Phase 2 training commands (prints compact summaries of the generated reports)."""
from __future__ import annotations

from crossfraud.models.training import run_messaging, run_payment, write_markdown_report


def _f(x):
    return "n/a" if x is None else f"{x:.3f}"


def run(cmd: str, data_dir: str) -> None:
    if cmd in ("train-messaging", "train"):
        ev = run_messaging(data_dir)
        print("\nMESSAGING MODEL  (TF-IDF + content indicators + Logistic Regression)")
        print("random split (optimistic):")
        for v, e in ev["random_split"]["variants"].items():
            m = e["metrics"]
            print(f"  {v:22s} P={_f(m['precision'])} R={_f(m['recall'])} F1={_f(m['f1'])} ROC-AUC={_f(m['roc_auc'])}")
        print("leave-one-scam-scenario-out (mean of 4 folds):")
        for v, e in ev["leave_one_scam_scenario_out"]["variants"].items():
            m = e["mean"]
            print(f"  {v:22s} P={_f(m['precision'])} R={_f(m['recall'])} F1={_f(m['f1'])} ROC-AUC={_f(m['roc_auc'])}")
        pr = ev["out_of_template_probe"]
        print(f"out-of-template probe: scam flagged {pr['scam_flagged_by_model']}, "
              f"scam with rule signal {pr['scam_with_any_rule_signal']}, benign flagged {pr['benign_flagged_by_model']}")
    if cmd in ("train-payment", "train"):
        ev = run_payment(data_dir)
        print(f"\nPAYMENT MODELS  (fraud rate {ev['fraud_rate_overall']:.4f})")
        for proto in ("temporal_split", "random_split"):
            p = ev[proto]
            print(f"{proto}: train {p['n_train']} ({p['n_train_fraud']} fraud) / test {p['n_test']} ({p['n_test_fraud']} fraud)")
            for k, e in p["models"].items():
                for key in ("metrics_at_0.5", "metrics_at_chosen_threshold"):
                    if key in e:
                        m = e[key]
                        cm = m["confusion_matrix"]
                        print(f"  {k:34s}{key.replace('metrics_', ''):22s} thr={m['threshold']:.3f} P={_f(m['precision'])} "
                              f"R={_f(m['recall'])} F1={_f(m['f1'])} ROC={_f(m['roc_auc'])} PR={_f(m['pr_auc'])} "
                              f"[TN {cm['tn']} FP {cm['fp']} FN {cm['fn']} TP {cm['tp']}]")
        print("active payment model:", ev["final_models"]["active"])
    if cmd == "train":
        print("\nmarkdown report ->", write_markdown_report(data_dir))
