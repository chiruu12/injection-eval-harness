"""`make report`: render results/results.json into the markdown tables in the README.

Nothing here recomputes anything. If a number is in the report it came out of
results.json, which came out of `make table`.
"""

from __future__ import annotations

import json
from pathlib import Path

from .bars import ROBUSTNESS_FPR_RISE, ROBUSTNESS_RECALL_DROP

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "results"

ORDER = ["regex-floor", "unplug-model", "unplug-pipeline", "protectai"]


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def main_table(block: dict, pairs: bool) -> str:
    head = ["system", "P", "R", "F1", "FPR", "PR-AUC (95% CI)", "ECE"]
    if pairs:
        head += ["pair acc", "marginal acc"]
    lines = [_row(head), _row(["---"] * len(head))]
    for key in ORDER:
        if key not in block:
            continue
        b = block[key]
        cells = [
            key,
            f"{b['precision']:.3f}", f"{b['recall']:.3f}", f"{b['f1']:.3f}", f"{b['fpr']:.3f}",
            f"{b['pr_auc']:.3f} ({b['pr_auc_ci95'][0]:.3f}-{b['pr_auc_ci95'][1]:.3f})",
            f"{b['ece']:.3f}",
        ]
        if pairs:
            cells += [f"{b.get('pair_accuracy', float('nan')):.3f}",
                      f"{b.get('marginal_accuracy', float('nan')):.3f}"]
        lines.append(_row(cells))
    return "\n".join(lines)


def fpr_table(block: dict) -> str:
    head = ["system", "R @ 0.5% FPR", "R @ 1% FPR", "R @ 5% FPR"]
    lines = [_row(head), _row(["---"] * len(head))]
    for key in ORDER:
        if key not in block:
            continue
        b = block[key]
        lines.append(_row([key] + [
            f"{b[f'recall_at_fpr_{t}']:.3f}" for t in (0.005, 0.01, 0.05)
        ]))
    return "\n".join(lines)


def _shift_cell(
    rate: float | None, delta: float | None, flagged: bool, skipped: str | None
) -> str:
    """One transform cell: rate and signed delta, or the reason the arm was not scored."""
    if skipped:
        return str(skipped).replace("|", "/")
    mark = " !" if flagged else ""
    return f"{rate:.3f} ({delta:+.3f}){mark}"


# One letter per classification, so the AUC row carries the verdict without a
# fourth row per system. Spelled out in the caption under the table.
_CLASS_MARK = {"capability": "C", "threshold": "T", "intact": "-"}


def _auc_cell(t: dict) -> str:
    """PR-AUC, its signed delta, and the threshold-versus-capability verdict."""
    auc = t.get("pr_auc")
    if auc is None:
        return str(t.get("auc_undefined", "not scored")).replace("|", "/")
    mark = _CLASS_MARK.get(t.get("classification"), "?")
    return f"{auc:.3f} ({t['pr_auc_delta']:+.3f}) {mark}"


def shift_table(shift: dict) -> str:
    """Recall, FPR and PR-AUC per transform, adjacent so none is quoted alone."""
    names = list(next(iter(shift.values()))["transforms"])
    head = ["system", "arm", "baseline", *names]
    lines = [_row(head), _row(["---"] * len(head))]
    for key in ORDER:
        if key not in shift:
            continue
        row = shift[key]
        rec_cells = [key, "R", f"{row['baseline_recall']:.3f}"]
        fpr_cells = [key, "FPR", f"{row['baseline_fpr']:.3f}"]
        base_auc = row.get("baseline_pr_auc")
        auc_cells = [key, "PR-AUC", "n/a" if base_auc is None else f"{base_auc:.3f}"]
        for n in names:
            t = row["transforms"][n]
            rec_cells.append(
                _shift_cell(
                    t.get("recall"),
                    t.get("delta"),
                    t.get("fails_robustness_bar", False),
                    t.get("positives_skipped"),
                )
            )
            fpr_cells.append(
                _shift_cell(
                    t.get("fpr"),
                    t.get("fpr_delta"),
                    t.get("fails_fpr_bar", False),
                    t.get("benign_skipped"),
                )
            )
            auc_cells.append(_auc_cell(t))
        lines.append(_row(rec_cells))
        lines.append(_row(fpr_cells))
        lines.append(_row(auc_cells))
    return "\n".join(lines)


def episode_table(block: dict) -> str:
    """Attack success off versus on, plus the utility and timing columns."""
    head = ["system", "ASR off", "ASR on", "utility", "late det", "never-fired"]
    lines = [_row(head), _row(["---"] * len(head))]
    for key in ORDER:
        if key not in block:
            continue
        delta = block[key]["delta"]
        on = block[key]["with_guard"]
        lines.append(_row([
            key,
            f"{delta['attack_success_rate_without_guard']:.3f}",
            (
                f"{delta['attack_success_rate_with_guard']:.3f} "
                f"({delta['attack_success_delta']:+.3f})"
            ),
            (
                f"{delta['utility_rate_with_guard']:.3f} "
                f"({delta['utility_delta']:+.3f})"
            ),
            f"{on['late_detection']['late_detection_rate']:.3f}",
            f"{on['detection_turns']['never_fired_share']:.3f}",
        ]))
    return "\n".join(lines)


def position_table(block: dict) -> str:
    """Attack success at each long_horizon posNN slot, guard on."""
    suffixes: list[str] = []
    seen: set[str] = set()
    for key in ORDER:
        if key not in block:
            continue
        for suffix in block[key]["with_guard"]["position_sensitivity"]:
            if suffix not in seen:
                seen.add(suffix)
                suffixes.append(suffix)
    suffixes.sort(key=lambda s: int(s[3:]))
    head = ["system", *suffixes]
    lines = [_row(head), _row(["---"] * len(head))]
    for key in ORDER:
        if key not in block:
            continue
        pos = block[key]["with_guard"]["position_sensitivity"]
        cells = [key]
        for suffix in suffixes:
            if suffix in pos:
                cells.append(f"{pos[suffix]['attack_success_rate']:.3f}")
            else:
                cells.append("n/a")
        lines.append(_row(cells))
    return "\n".join(lines)


def main() -> None:
    r = json.loads((RESULTS / "results.json").read_text())
    m = json.loads((RESULTS / "manifest.json").read_text())
    out = []
    out.append("### Primary: boundary-pairs test (240 rows, 120 pairs, published after every model)\n")
    out.append(main_table(r["primary_test"], pairs=True))
    out.append("\n### Recall at a fixed false-positive rate, primary test\n")
    out.append(fpr_table(r["primary_test"]))
    out.append("\n### Control: deepset test (116 rows, predates every model, contamination-suspect)\n")
    out.append(main_table(r["control_deepset_test"], pairs=False))
    gaps = {k: r["control_deepset_test"][k]["f1_gap_vs_primary"] for k in ORDER
            if k in r["control_deepset_test"]}
    out.append("\nF1 gap, control minus primary: " +
               ", ".join(f"{k} {v:+.3f}" for k, v in gaps.items()))
    if "shift" in r:
        sample = next(iter(r["shift"].values()))
        n_pos = sample["n_positives"]
        n_ben = sample["n_benign"]
        out.append(
            f"\n### Controlled shift: seeded obfuscation of the {n_pos} test positives "
            f"and {n_ben} test benign rows\n"
        )
        out.append(shift_table(r["shift"]))
        drop = int(ROBUSTNESS_RECALL_DROP * 100)
        rise = int(ROBUSTNESS_FPR_RISE * 100)
        out.append(
            f"\n`!` on R marks a drop of more than {drop} absolute points, the pre-registered bar. "
            f"`!` on FPR marks a rise of more than {rise} absolute points, the companion bar.\n"
            f"\nThe PR-AUC row is threshold-free, so it separates two failures that a recall "
            f"column shows identically. `T` is a threshold failure: the ranking survived and "
            f"re-thresholding recovers the recall. `C` is a capability failure: the ranking "
            f"itself degraded, or the detector now fires on the benign arm as readily as the "
            f"attack arm, and no threshold recovers it. `-` is neither. The arms are balanced "
            f"at {n_pos} against {n_ben}, so 0.500 is chance."
        )
    if "spans_carrier" in r:
        s = r["spans_carrier"]
        out.append(
            f"\n### Span localisation, carrier transform only\n\n"
            f"unplug-model fired on {s['fired_on']}/{s['n_positives']} carrier documents. "
            f"Character IoU against the known payload offsets: {s['char_iou']:.3f}. "
            f"Boundaries within 5 characters on {s['exact_within_5_chars']}/{s['n_positives']} "
            f"({s['exact_rate']:.3f})."
        )
    ss = r["stage_split"]
    out.append(
        f"\n### Which stage decides, Unplug SDK, primary test\n\n"
        f"Of the primary test rows that produced any finding, "
        f"{ss['regex_share_of_findings']:.1%} were decided by the regex stage alone and the "
        f"checkpoint was never consulted ({ss['regex_only']} regex-only, "
        f"{ss['model_involved']} reached the model, {ss['no_finding']} no finding)."
    )
    if "episodes" in r:
        out.append(
            "\n### Episodes: attack success with the guard off versus on the "
            "tool-output boundary\n"
        )
        out.append(episode_table(r["episodes"]))
        out.append(
            "\nASR on and utility show the signed delta versus the unguarded run. "
            "Utility is task completion on the benign controls. Late detection and "
            "never-fired are the with-guard run."
        )
        out.append(
            "\n### Position sensitivity: same payload at long_horizon posNN, guard on\n"
        )
        out.append(position_table(r["episodes"]))
    out.append(f"\n---\n\nGenerated {m['generated_utc']} from harness {m['harness_git_sha'][:12]}, seed {m['seed']}.")
    text = "\n".join(out) + "\n"
    (RESULTS / "TABLES.md").write_text(text)
    print(text)


if __name__ == "__main__":
    main()
