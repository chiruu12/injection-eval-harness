"""Metric code, checked against hand-computed values. No model, no network."""

import math

from injection_eval.metrics import (
    counts_at,
    expected_calibration_error,
    marginal_accuracy,
    pair_accuracy,
    recall_at_fpr,
)

Y = [1, 1, 1, 1, 0, 0, 0, 0]
S = [0.9, 0.8, 0.4, 0.1, 0.7, 0.3, 0.2, 0.05]


def test_counts_at_threshold():
    c = counts_at(Y, S, 0.5)
    assert (c.tp, c.fn, c.fp, c.tn) == (2, 2, 1, 3)
    assert math.isclose(c.recall, 0.5)
    assert math.isclose(c.precision, 2 / 3)
    assert math.isclose(c.fpr, 0.25)


def test_counts_are_exhaustive():
    c = counts_at(Y, S, 0.5)
    assert c.tp + c.fp + c.tn + c.fn == len(Y)


def test_recall_at_zero_fpr():
    # 0.7 is the highest negative, so a zero-FPR threshold must sit above it,
    # which admits exactly the two positives at 0.9 and 0.8.
    rec, thr = recall_at_fpr(Y, S, 0.0)
    assert math.isclose(rec, 0.5)
    assert thr > 0.7


def test_ece_is_zero_for_a_perfectly_calibrated_score():
    y = [1] * 50 + [0] * 50
    s = [1.0] * 50 + [0.0] * 50
    ece, curve = expected_calibration_error(y, s)
    assert math.isclose(ece, 0.0, abs_tol=1e-9)
    assert sum(b["n"] for b in curve) == 100


def test_ece_is_large_for_a_confidently_wrong_score():
    ece, _ = expected_calibration_error([0] * 20, [0.95] * 20)
    assert ece > 0.9


def test_pair_accuracy_needs_both_halves_right():
    labels = {"a1": 1, "a0": 0, "b1": 1, "b0": 0}
    pairs = {"a1": "a", "a0": "a", "b1": "b", "b0": "b"}
    # pair a correct; pair b fires on the benign twin
    scores = {"a1": 0.9, "a0": 0.1, "b1": 0.9, "b0": 0.9}
    acc, ok, total = pair_accuracy(labels, scores, pairs, 0.5)
    assert (ok, total) == (1, 2)
    assert math.isclose(acc, 0.5)


def test_pair_accuracy_is_stricter_than_marginal():
    labels = {"a1": 1, "a0": 0, "b1": 1, "b0": 0}
    pairs = {"a1": "a", "a0": "a", "b1": "b", "b0": "b"}
    scores = {"a1": 0.9, "a0": 0.1, "b1": 0.9, "b0": 0.9}
    marg, marg_ok, marg_n = marginal_accuracy(labels, scores, 0.5)
    acc, _, _ = pair_accuracy(labels, scores, pairs, 0.5)
    assert (marg_ok, marg_n) == (3, 4)
    assert math.isclose(marg, 0.75)
    assert acc < marg


def test_marginal_accuracy_matches_tp_tn_over_n():
    labels = {"p": 1, "n": 0, "fn": 1, "fp": 0}
    scores = {"p": 0.9, "n": 0.1, "fn": 0.1, "fp": 0.9}
    acc, ok, total = marginal_accuracy(labels, scores, 0.5)
    assert (ok, total) == (2, 4)
    assert math.isclose(acc, 0.5)


def test_marginal_accuracy_on_no_rows_is_zero():
    acc, ok, total = marginal_accuracy({}, {}, 0.5)
    assert (acc, ok, total) == (0.0, 0, 0)
