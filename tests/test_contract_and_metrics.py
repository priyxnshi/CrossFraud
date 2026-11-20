import json

import numpy as np
import pytest

from crossfraud.models.contract import make_result, risk_level, signal, validate_result
from crossfraud.models.metrics import best_f1_threshold, binary_metrics


def test_risk_level_agrees_with_threshold():
    assert risk_level(0.9, 0.5) == "high" and risk_level(0.5, 0.5) == "high"
    assert risk_level(0.3, 0.5) == "medium" and risk_level(0.1, 0.5) == "low"
    assert risk_level(0.4, 0.4432) == "medium"


def test_make_result_is_valid_and_json_serialisable():
    r = make_result("C1", "conversation", 0.8, 0.5, "m", [signal("x", "rule", "d")], {"a": 1}, None, {})
    assert validate_result(r) == [] and r["predicted_class"] == 1 and r["predicted_label"] == "fraud"
    json.dumps(r)


def test_validate_result_catches_problems():
    good = make_result("T1", "transaction", 0.1, 0.5, "m", [])
    assert validate_result({**good, "risk_score": 1.5})
    assert validate_result({**good, "risk_score": float("nan")})
    assert validate_result({**good, "entity_type": "x"})
    assert validate_result({**good, "risk_level": "high"})  # disagrees with predicted_class 0
    assert validate_result({k: v for k, v in good.items() if k != "model"})
    assert validate_result("not a dict")


def test_binary_metrics_confusion_matrix_and_accuracy_trap():
    y = np.array([1, 1, 0, 0, 0, 0, 0, 0, 0, 0])
    s = np.array([0.9, 0.2, 0.8, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1])
    m = binary_metrics(y, s, 0.5)
    assert m["confusion_matrix"] == {"tn": 7, "fp": 1, "fn": 1, "tp": 1}
    assert m["precision"] == 0.5 and m["recall"] == 0.5 and m["f1"] == 0.5
    assert m["majority_class_accuracy"] == 0.8 and m["accuracy"] == 0.8


def test_best_f1_threshold_separates_clean_scores():
    y = np.array([0, 0, 0, 1, 1])
    thr, f1 = best_f1_threshold(y, np.array([0.1, 0.2, 0.3, 0.8, 0.9]))
    assert f1 == 1.0 and 0.3 < thr <= 0.8
