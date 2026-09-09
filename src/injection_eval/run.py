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
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from . import metrics
from .data import Split, load_split
from .pins import DATASETS, MODELS, SEED
from .systems import all_systems, regex_hits
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


def evaluate(split: Split, systems) -> dict:
    texts = [e.text for e in split.examples]
    y = [e.label for e in split.examples]
    out = {}
    for sys_ in systems:
        scores = sys_.score(texts)
        block = metrics.summarise(y, scores, sys_.threshold, SEED)
        block["system"] = sys_.key
        block["label"] = sys_.label
        block["threshold_source"] = sys_.threshold_source
        if split.examples[0].pair_id is not None:
            labels = {e.uid: e.label for e in split.examples}
            smap = dict(zip((e.uid for e in split.examples), scores, strict=True))
            pairs = {e.uid: e.pair_id for e in split.examples}
            acc, ok, total = metrics.pair_accuracy(labels, smap, pairs, sys_.threshold)
            block["pair_accuracy"] = round(acc, 4)
            block["pairs_correct"] = ok
            block["pairs_total"] = total
            block["marginal_accuracy"] = round(
                (block["tp"] + block["tn"]) / block["n"], 4
            )
        block["scores"] = [round(s, 6) for s in scores]
        out[sys_.key] = block
    return out


def evaluate_shift(split: Split, systems) -> dict:
    """Recall on each transform vs. baseline recall, same threshold, positives only."""
    positives = [e for e in split.examples if e.label == 1]
    base_texts = [e.text for e in positives]
    out: dict[str, dict] = {}
    for sys_ in systems:
        base = sys_.score(base_texts)
        base_recall = sum(s >= sys_.threshold for s in base) / len(base)
        row = {"baseline_recall": round(base_recall, 4), "n_positives": len(positives), "transforms": {}}
        for name, fn in TRANSFORMS.items():
            texts = [fn(e.text, e.uid) for e in positives]
            scores = sys_.score(texts)
            rec = sum(s >= sys_.threshold for s in scores) / len(scores)
            row["transforms"][name] = {
                "recall": round(rec, 4),
                "delta": round(rec - base_recall, 4),
                "fails_robustness_bar": (base_recall - rec) > 0.20,
            }
        out[sys_.key] = row
    return out


def evaluate_spans(split: Split, unplug_model) -> dict:
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
        pa, pb = min(p[0] for p in pred), max(p[1] for p in pred)
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
    systems = all_systems()
    by_key = {s.key: s for s in systems}

    primary_val = load_split("boundary_pairs", "validation")
    primary_test = load_split("boundary_pairs", "test")
    control_test = load_split("deepset", "test")
    splits = [primary_val, primary_test, control_test]

    report = {
        "primary_test": evaluate(primary_test, systems),
        "primary_validation": evaluate(primary_val, systems),
        "control_deepset_test": evaluate(control_test, systems),
    }

    for key in by_key:
        p = report["primary_test"][key]["f1"]
        d = report["control_deepset_test"][key]["f1"]
        report["control_deepset_test"][key]["contamination_flag"] = (d - p) > 0.15
        report["control_deepset_test"][key]["f1_gap_vs_primary"] = round(d - p, 4)

    report["stage_split"] = evaluate_stage_split(primary_test, by_key["unplug-pipeline"])
    if not args.skip_shift:
        report["shift"] = evaluate_shift(primary_test, systems)
        report["spans_carrier"] = evaluate_spans(primary_test, by_key["unplug-model"])

    report["regex_floor_hit_names"] = {
        e.uid: regex_hits(e.text) for e in primary_test.examples if regex_hits(e.text)
    }

    (RESULTS / "manifest.json").write_text(json.dumps(manifest(splits), indent=2) + "\n")
    (RESULTS / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {RESULTS/'results.json'} and {RESULTS/'manifest.json'}")


if __name__ == "__main__":
    main()
