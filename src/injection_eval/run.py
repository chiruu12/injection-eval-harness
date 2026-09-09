"""`make table`: regenerate every reported number.

Writes results/*.json and results/manifest.json. The manifest carries dataset
shas, model shas, package versions, the seed and the harness git sha, so a table
in the README can always be traced back to the exact artifacts that produced it.
"""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from sklearn.metrics import average_precision_score, roc_auc_score

from . import metrics
from .bars import (
    classify_shift_failure,
    fails_contamination,
    fails_fpr_shift,
    fails_robustness,
)
from .core.contracts import SpanDetector
from .data import Split, load_split
from .detectors.regex_floor import regex_hits
from .detectors.registry import all_detectors
from .guard import Guard
from .pins import DATASETS, MODELS, SEED
from .policies import published_policy
from .sim.driver import evaluate_episodes
from .transforms import TRANSFORMS, carrier_span

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"


def _git_sha() -> str:
    try:
        return subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
    except Exception:
        return "unknown"


def manifest(splits: list[Split]) -> dict:
    return {
        "generated_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "harness_git_sha": _git_sha(),
        "seed": SEED,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "packages": {
            p: version(p) for p in ("torch", "transformers", "datasets", "scikit-learn", "unplug-ai")
        },
        "datasets": {
            k: {
                "repo_id": v.repo_id, "sha": v.sha, "license": v.license,
                "published": v.published, "role": v.role,
            }
            for k, v in DATASETS.items()
        },
        "models": {k: {"repo_id": v.repo_id, "sha": v.sha, "params": v.params} for k, v in MODELS.items()},
        "splits": {
            f"{s.dataset}/{s.name}": {"n": len(s), "positives": sum(e.label for e in s.examples),
                                      "checksum": s.checksum}
            for s in splits
        },
    }


def evaluate(split: Split, guards: list[Guard]) -> dict:
    texts = [e.text for e in split.examples]
    y = [e.label for e in split.examples]
    out = {}
    for guard in guards:
        scores = guard.detector.score(texts)
        block = metrics.summarise(y, scores, guard.policy.threshold, SEED)
        block["system"] = guard.detector.key
        block["label"] = guard.detector.label
        block["threshold_source"] = guard.policy.threshold_source
        if split.examples[0].pair_id is not None:
            labels = {e.uid: e.label for e in split.examples}
            smap = dict(zip((e.uid for e in split.examples), scores, strict=True))
            pairs = {e.uid: e.pair_id for e in split.examples}
            acc, ok, total = metrics.pair_accuracy(labels, smap, pairs, guard.policy.threshold)
            block["pair_accuracy"] = round(acc, 4)
            block["pairs_correct"] = ok
            block["pairs_total"] = total
            marg, _, _ = metrics.marginal_accuracy(labels, smap, guard.policy.threshold)
            block["marginal_accuracy"] = round(marg, 4)
        block["scores"] = [round(s, 6) for s in scores]
        out[guard.detector.key] = block
    return out


def _transformed(
    fn: Callable[[str, str], str], examples: list
) -> tuple[list[str] | None, str | None]:
    """The texts of one arm after a transform, or why that arm cannot be scored."""
    texts: list[str] = []
    for example in examples:
        try:
            texts.append(fn(example.text, example.uid))
        except Exception as exc:
            # Do not drop the transform from the table; a missing cell would
            # look like the arm was never part of the design.
            return None, f"{type(exc).__name__}: {exc} (uid={example.uid!r})"
    return texts, None


def _fire(scores: list[float], threshold: float) -> tuple[float, int, int]:
    """Hits at the operating threshold, with the denominator that rate belongs to."""
    n = len(scores)
    hits = sum(s >= threshold for s in scores)
    return (hits / n if n else 0.0), hits, n


def _average_precision(y_true: list[int], y_score: list[float]) -> float:
    """Average precision for one bootstrap draw, NaN when the draw holds a single class.

    bootstrap_ci drops NaN draws, so a resample that happened to miss one arm
    is excluded from the interval rather than counted as a result of zero.
    """
    if len(set(y_true)) < 2:
        return float("nan")
    return float(average_precision_score(y_true, y_score))


def _ranking(
    pos_scores: list[float] | None, ben_scores: list[float] | None
) -> tuple[dict | None, str | None]:
    """Threshold-free ranking of one arm pair, or why no AUC can exist for them.

    PR-AUC and ROC-AUC rank the transformed positives against the transformed
    benign rows, which is what a recall figure at a fixed threshold cannot see:
    a distribution that slid below the threshold without changing the order.
    Both are undefined unless both classes are present, and the reason is
    returned rather than a zero or a NaN that would later read as a result.
    The interval uses the same seeded bootstrap and the same seed as the
    static table, so resampling noise is shared and a delta against another
    seeded number is not inflated by two independent draws.
    """
    if pos_scores is None or ben_scores is None:
        arm = "positives" if pos_scores is None else "benign"
        return None, (
            f"PR-AUC and ROC-AUC are undefined: the {arm} arm of this transform "
            f"was not scored"
        )
    if not pos_scores or not ben_scores:
        return None, (
            f"PR-AUC and ROC-AUC are undefined: the ranked rows hold one class "
            f"({len(pos_scores)} positives, {len(ben_scores)} benign)"
        )
    y = [1] * len(pos_scores) + [0] * len(ben_scores)
    s = [*pos_scores, *ben_scores]
    lo, hi = metrics.bootstrap_ci(y, s, _average_precision, seed=SEED)
    return {
        "pr_auc": float(average_precision_score(y, s)),
        "pr_auc_ci95": [lo, hi],
        "roc_auc": float(roc_auc_score(y, s)),
    }, None


def evaluate_shift(
    split: Split,
    guards: list[Guard],
    transforms: Mapping[str, Callable[[str, str], str]] | None = None,
) -> dict:
    """Robustness of each detector to seeded, label-preserving surface changes.

    Both arms of the split are transformed, because a recall figure without
    its false-positive rate is not a result. Each arm pair is also ranked
    threshold-free, because a table read at one fixed threshold cannot tell a
    ranking that survived the shift from one that did not, and the two
    failures have different fixes (docs/FINDINGS.md finding 2).
    """
    table = TRANSFORMS if transforms is None else transforms
    positives = [e for e in split.examples if e.label == 1]
    benign = [e for e in split.examples if e.label == 0]
    out: dict[str, dict] = {}
    for guard in guards:
        thr = guard.policy.threshold
        # Separate batches keep the positive-arm measurement identical to the
        # slice that used to score positives only.
        base_pos = guard.detector.score([e.text for e in positives]) if positives else []
        base_ben = guard.detector.score([e.text for e in benign]) if benign else []
        base_recall, _, _ = _fire(base_pos, thr)
        base_fpr, _, _ = _fire(base_ben, thr)
        base_rank, base_auc_note = _ranking(base_pos, base_ben)
        row: dict = {
            "baseline_recall": round(base_recall, 4),
            "n_positives": len(positives),
            "baseline_fpr": round(base_fpr, 4),
            "n_benign": len(benign),
            "baseline_pr_auc": None if base_rank is None else round(base_rank["pr_auc"], 4),
            "baseline_roc_auc": None if base_rank is None else round(base_rank["roc_auc"], 4),
            "transforms": {},
        }
        if base_auc_note is not None:
            row["baseline_auc_undefined"] = base_auc_note
        for name, fn in table.items():
            entry: dict = {}
            rec: float | None = None
            pos_scores: list[float] | None
            pos_texts, pos_note = _transformed(fn, positives)
            if pos_note is not None:
                pos_scores = None
                entry.update(
                    {
                        "recall": None,
                        "delta": None,
                        "recalled": 0,
                        "n_positives": 0,
                        "fails_robustness_bar": False,
                        "positives_skipped": pos_note,
                    }
                )
            else:
                pos_scores = guard.detector.score(pos_texts) if pos_texts else []
                rec, recalled, rec_n = _fire(pos_scores, thr)
                entry.update(
                    {
                        "recall": round(rec, 4),
                        "delta": round(rec - base_recall, 4),
                        "recalled": recalled,
                        "n_positives": rec_n,
                        "fails_robustness_bar": fails_robustness(base_recall, rec),
                    }
                )
            ben_scores: list[float] | None
            ben_texts, ben_note = _transformed(fn, benign)
            if ben_note is not None:
                ben_scores = None
                entry.update(
                    {
                        "fpr": None,
                        "fpr_delta": None,
                        "false_positives": 0,
                        "n_benign": 0,
                        "fails_fpr_bar": False,
                        "benign_skipped": ben_note,
                    }
                )
            else:
                ben_scores = guard.detector.score(ben_texts) if ben_texts else []
                fpr, fps, fpr_n = _fire(ben_scores, thr)
                entry.update(
                    {
                        "fpr": round(fpr, 4),
                        "fpr_delta": round(fpr - base_fpr, 4),
                        "false_positives": fps,
                        "n_benign": fpr_n,
                        "fails_fpr_bar": fails_fpr_shift(base_fpr, fpr),
                    }
                )
            rank, auc_note = _ranking(pos_scores, ben_scores)
            if rank is None or base_rank is None:
                entry.update(
                    {
                        "pr_auc": None,
                        "pr_auc_ci95": None,
                        "pr_auc_delta": None,
                        "roc_auc": None,
                        "roc_auc_delta": None,
                        "classification": None,
                        "auc_undefined": auc_note if auc_note is not None else base_auc_note,
                    }
                )
            else:
                lo, hi = rank["pr_auc_ci95"]
                entry.update(
                    {
                        "pr_auc": round(rank["pr_auc"], 4),
                        "pr_auc_ci95": [round(lo, 4), round(hi, 4)],
                        "pr_auc_delta": round(rank["pr_auc"] - base_rank["pr_auc"], 4),
                        "roc_auc": round(rank["roc_auc"], 4),
                        "roc_auc_delta": round(rank["roc_auc"] - base_rank["roc_auc"], 4),
                        "classification": classify_shift_failure(
                            base_recall, rec, base_rank["pr_auc"], rank["pr_auc"]
                        ),
                    }
                )
            row["transforms"][name] = entry
        out[guard.detector.key] = row
    return out


def evaluate_spans(split: Split, unplug_model: SpanDetector) -> dict:
    """Span metrics, carrier transform only, where offsets are known by construction."""
    positives = [e for e in split.examples if e.label == 1]
    inter = union = 0
    exact = hit = 0
    for e in positives:
        text = TRANSFORMS["carrier"](e.text, e.uid)
        gold_a, gold_b = carrier_span(e.text)
        pred = unplug_model.spans(text)
        if not pred:
            union += gold_b - gold_a
            continue
        hit += 1
        pa, pb = min(p.start for p in pred), max(p.end for p in pred)
        i = max(0, min(gold_b, pb) - max(gold_a, pa))
        u = max(gold_b, pb) - min(gold_a, pa)
        inter += i
        union += u
        if abs(pa - gold_a) <= 5 and abs(pb - gold_b) <= 5:
            exact += 1
    n = len(positives)
    return {
        "n_positives": n,
        "fired_on": hit,
        "char_iou": round(inter / union, 4) if union else 0.0,
        "exact_within_5_chars": exact,
        "exact_rate": round(exact / n, 4),
        "note": "carrier transform only; offsets known because the harness spliced the payload",
    }


def evaluate_stage_split(split: Split, pipeline) -> dict:
    """How often the SDK's regex stage decides before the model is consulted."""
    counts = {"regex_only": 0, "model_involved": 0, "no_finding": 0}
    for e in split.examples:
        stages = set(pipeline.stages(e.text))
        if not stages:
            counts["no_finding"] += 1
        elif stages == {"regex"}:
            counts["regex_only"] += 1
        else:
            counts["model_involved"] += 1
    counts["regex_share_of_findings"] = round(
        counts["regex_only"] / max(1, counts["regex_only"] + counts["model_involved"]), 4
    )
    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-shift", action="store_true")
    args = ap.parse_args()

    RESULTS.mkdir(exist_ok=True)
    guards = [Guard(d, published_policy(d.key)) for d in all_detectors()]
    by_key = {g.detector.key: g for g in guards}

    primary_val = load_split("boundary_pairs", "validation")
    primary_test = load_split("boundary_pairs", "test")
    control_test = load_split("deepset", "test")
    splits = [primary_val, primary_test, control_test]

    report = {
        "primary_test": evaluate(primary_test, guards),
        "primary_validation": evaluate(primary_val, guards),
        "control_deepset_test": evaluate(control_test, guards),
    }

    for key in by_key:
        p = report["primary_test"][key]["f1"]
        d = report["control_deepset_test"][key]["f1"]
        report["control_deepset_test"][key]["contamination_flag"] = fails_contamination(d, p)
        report["control_deepset_test"][key]["f1_gap_vs_primary"] = round(d - p, 4)

    report["stage_split"] = evaluate_stage_split(primary_test, by_key["unplug-pipeline"].detector)
    if not args.skip_shift:
        report["shift"] = evaluate_shift(primary_test, guards)
        report["spans_carrier"] = evaluate_spans(primary_test, by_key["unplug-model"].detector)

    report["regex_floor_hit_names"] = {
        e.uid: regex_hits(e.text) for e in primary_test.examples if regex_hits(e.text)
    }
    report["episodes"] = evaluate_episodes(guards)

    (RESULTS / "manifest.json").write_text(json.dumps(manifest(splits), indent=2) + "\n")
    (RESULTS / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {RESULTS/'results.json'} and {RESULTS/'manifest.json'}")


if __name__ == "__main__":
    main()
