"""Metrics: score-level (static) and trajectory-level (episode), pure functions throughout.

The split is by input shape. static.py takes flat (y_true, y_score) arrays and
answers how well a detector ranks texts; episode.py takes lists of Episode and
answers what a guard changed over whole trajectories. Neither does I/O or
imports a model, so a reported number is a function of its inputs alone.

The static names are re-exported at the package root because existing imports
say `from .metrics import counts_at`; the module-to-package move must not break
them, and a caller should not need to know where a function lives.
"""

from .static import (
    Counts,
    bootstrap_ci,
    brier,
    counts_at,
    expected_calibration_error,
    marginal_accuracy,
    pair_accuracy,
    recall_at_fpr,
    summarise,
)

__all__ = [
    "Counts",
    "bootstrap_ci",
    "brier",
    "counts_at",
    "expected_calibration_error",
    "marginal_accuracy",
    "pair_accuracy",
    "recall_at_fpr",
    "summarise",
]
