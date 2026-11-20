"""Evaluation helpers: metrics, F1-optimal threshold, bootstrap confidence intervals."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import (average_precision_score, confusion_matrix, precision_recall_curve,
                             precision_score, recall_score, f1_score, roc_auc_score)


def binary_metrics(y_true, scores, threshold: float) -> dict:
    y = np.asarray(y_true).astype(int)
    s = np.asarray(scores, dtype=float)
    pred = (s >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, pred, labels=[0, 1]).ravel()
    both = len(np.unique(y)) == 2
    return {
        "threshold": float(threshold), "n": int(len(y)), "n_positive": int(y.sum()),
        "precision": float(precision_score(y, pred, zero_division=0)),
        "recall": float(recall_score(y, pred, zero_division=0)),
        "f1": float(f1_score(y, pred, zero_division=0)),
        "roc_auc": float(roc_auc_score(y, s)) if both else None,
        "pr_auc": float(average_precision_score(y, s)) if both else None,
        "accuracy": float((pred == y).mean()),
        "majority_class_accuracy": float(max(y.mean(), 1 - y.mean())),
        "confusion_matrix": {"tn": int(tn), "fp": int(fp), "fn": int(fn), "tp": int(tp)},
    }


def best_f1_threshold(y_true, scores) -> tuple[float, float]:
    """Threshold maximising F1 (use on training/out-of-fold scores, never on the test set)."""
    p, r, t = precision_recall_curve(np.asarray(y_true).astype(int), np.asarray(scores, float))
    f1 = 2 * p[:-1] * r[:-1] / np.maximum(p[:-1] + r[:-1], 1e-12)
    i = int(np.argmax(f1))
    return float(t[i]), float(f1[i])


def bootstrap_ci(y_true, scores, threshold: float, n_boot: int = 300, seed: int = 42) -> dict:
    """95% percentile bootstrap intervals over the test set (shows how noisy small test sets are)."""
    rng = np.random.default_rng(seed)
    y, s = np.asarray(y_true).astype(int), np.asarray(scores, float)
    keys = ["precision", "recall", "f1", "roc_auc", "pr_auc"]
    acc = {k: [] for k in keys}
    for _ in range(n_boot):
        idx = rng.integers(0, len(y), len(y))
        yb = y[idx]
        if yb.sum() in (0, len(yb)):
            continue
        m = binary_metrics(yb, s[idx], threshold)
        for k in keys:
            acc[k].append(m[k])
    return {k: [float(np.percentile(v, 2.5)), float(np.percentile(v, 97.5))] for k, v in acc.items()}
