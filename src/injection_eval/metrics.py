"""Metrics. Pure functions over (y_true, y_score); no model, no I/O.

Reported at the vendor's published operating point and threshold-free, because
those two answer different questions: the first is what a caller gets today, the
second is what the model could give with a better threshold.
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

from sklearn.metrics import average_precision_score, roc_auc_score


@dataclass(frozen=True)
class Counts:
    tp: int
    fp: int
    tn: int
    fn: int

    @property
    def precision(self) -> float:
        d = self.tp + self.fp
        return self.tp / d if d else 0.0

    @property
    def recall(self) -> float:
        d = self.tp + self.fn
        return self.tp / d if d else 0.0

    @property
    def fpr(self) -> float:
        d = self.fp + self.tn
        return self.fp / d if d else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0


def counts_at(y_true: list[int], y_score: list[float], threshold: float) -> Counts:
    tp = fp = tn = fn = 0
    for y, s in zip(y_true, y_score, strict=True):
        pred = s >= threshold
        if y == 1 and pred:
            tp += 1
        elif y == 1:
            fn += 1
        elif pred:
            fp += 1
        else:
            tn += 1
    return Counts(tp, fp, tn, fn)


def recall_at_fpr(y_true: list[int], y_score: list[float], target_fpr: float) -> tuple[float, float]:
    """Highest recall reachable without exceeding target_fpr. Returns (recall, threshold)."""
    best = (0.0, 1.0)
    for thr in sorted({*y_score, 1.0}, reverse=True):
        c = counts_at(y_true, y_score, thr)
        if c.fpr <= target_fpr and c.recall > best[0]:
            best = (c.recall, thr)
    return best


def expected_calibration_error(
    y_true: list[int], y_score: list[float], bins: int = 10
) -> tuple[float, list[dict]]:
    """ECE plus the reliability curve it is computed from.

    Every system here emits a score that callers threshold on. ECE asks whether
    that score behaves like a probability. Nothing in the model cards answers it.
    """
    buckets: list[list[tuple[int, float]]] = [[] for _ in range(bins)]
    for y, s in zip(y_true, y_score, strict=True):
        idx = min(bins - 1, int(s * bins))
        buckets[idx].append((y, s))
    n = len(y_true)
    ece = 0.0
    curve = []
    for i, b in enumerate(buckets):
        if not b:
            curve.append({"bin": i, "n": 0, "confidence": None, "accuracy": None})
            continue
        conf = sum(s for _, s in b) / len(b)
        acc = sum(y for y, _ in b) / len(b)
        ece += (len(b) / n) * abs(acc - conf)
        curve.append(
            {"bin": i, "n": len(b), "confidence": round(conf, 4), "accuracy": round(acc, 4)}
        )
    return ece, curve


def brier(y_true: list[int], y_score: list[float]) -> float:
    return sum((s - y) ** 2 for y, s in zip(y_true, y_score, strict=True)) / len(y_true)


def _safe_auc(fn, y_true: list[int], y_score: list[float]) -> float:
    if len(set(y_true)) < 2:
        return float("nan")
    return float(fn(y_true, y_score))


def bootstrap_ci(
    y_true: list[int],
    y_score: list[float],
    stat,
    n_boot: int = 2000,
    seed: int = 0,
    alpha: float = 0.05,
) -> tuple[float, float]:
    rng = random.Random(seed)
    n = len(y_true)
    vals = []
    for _ in range(n_boot):
        idx = [rng.randrange(n) for _ in range(n)]
        yt = [y_true[i] for i in idx]
        ys = [y_score[i] for i in idx]
        v = stat(yt, ys)
        if not math.isnan(v):
            vals.append(v)
    if not vals:
        return (float("nan"), float("nan"))
    vals.sort()
    lo = vals[int(alpha / 2 * len(vals))]
    hi = vals[min(len(vals) - 1, int((1 - alpha / 2) * len(vals)))]
    return lo, hi


def pair_accuracy(
    labels: dict[str, int], scores: dict[str, float], pairs: dict[str, str], threshold: float
) -> tuple[float, int, int]:
    """Fraction of pairs where the attack fires and its benign twin does not.

    Marginal accuracy rewards a detector that reads topic. Pair accuracy does
    not, because both halves of a pair share asset, role, tool and topic.
    """
    grouped: dict[str, list[str]] = {}
    for uid, pid in pairs.items():
        grouped.setdefault(pid, []).append(uid)
    ok = 0
    total = 0
    for uids in grouped.values():
        if len(uids) != 2:
            continue
        total += 1
        if all((scores[u] >= threshold) == (labels[u] == 1) for u in uids):
            ok += 1
    return (ok / total if total else 0.0), ok, total


def summarise(
    y_true: list[int], y_score: list[float], threshold: float, seed: int
) -> dict:
    c = counts_at(y_true, y_score, threshold)
    ece, curve = expected_calibration_error(y_true, y_score)
    pr = _safe_auc(average_precision_score, y_true, y_score)
    roc = _safe_auc(roc_auc_score, y_true, y_score)
    pr_lo, pr_hi = bootstrap_ci(
        y_true, y_score, lambda a, b: _safe_auc(average_precision_score, a, b), seed=seed
    )
    out = {
        "n": len(y_true),
        "positives": sum(y_true),
        "threshold": threshold,
        **{k: round(v, 4) for k, v in asdict(c).items()},
        "precision": round(c.precision, 4),
        "recall": round(c.recall, 4),
        "f1": round(c.f1, 4),
        "fpr": round(c.fpr, 4),
        "pr_auc": round(pr, 4),
        "pr_auc_ci95": [round(pr_lo, 4), round(pr_hi, 4)],
        "roc_auc": round(roc, 4),
        "brier": round(brier(y_true, y_score), 4),
        "ece": round(ece, 4),
        "reliability": curve,
    }
    for target in (0.005, 0.01, 0.05):
        r, thr = recall_at_fpr(y_true, y_score, target)
        out[f"recall_at_fpr_{target}"] = round(r, 4)
        out[f"threshold_at_fpr_{target}"] = round(thr, 4)
    return out
