#!/usr/bin/env python3
"""Assert that a re-run of the harness reproduces the committed numbers.

Two different failures are worth telling apart, so this checks both.

- Regression: the committed results/results.json is the contract. A refactor that
  moves a published number is a bug, and this catches it without anyone having to
  remember to look.
- Non-determinism: two runs of the same checkout on the same machine must agree
  exactly. If they do not, something is unpinned and the manifest is a
  description of an artifact that no longer exists.

The regression check takes a tolerance and the determinism check never does, and
that asymmetry is the point. Two runs on one machine have no excuse to differ by
anything. A run on a different CPU does: the first Linux run of this harness
reproduced the macOS table to 2.1e-05 on raw scores, moving no recall, no FPR,
no F1, no ECE and no bar verdict, but shifting PR-AUC on one system in the third
decimal, because average precision ranks rows and float noise reorders adjacent
ones. Demanding bit-equality across platforms would fail on that forever and
teach everyone to ignore the check. Demanding nothing would let a real
regression through. The tolerance is the honest middle, and the measured
envelope is in docs/FINDINGS.md rather than left for a reader to discover.

The manifest is compared separately and loosely: its timestamp and git sha are
expected to move, its pins and checksums are not.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "results" / "results.json"
MANIFEST = ROOT / "results" / "manifest.json"
PY_BIN = ROOT / ".venv" / "bin" / "python"

# Regenerated every run and expected to differ. Everything else must not.
VOLATILE_MANIFEST_KEYS = {"generated_utc", "harness_git_sha", "platform", "python", "packages"}


def _run_table() -> None:
    subprocess.run([str(PY_BIN), "-m", "injection_eval.run"], cwd=ROOT, check=True)


def _diff(a: Any, b: Any, path: str = "", tol: float = 0.0) -> list[str]:
    """Every leaf where two parsed JSON documents disagree, as dotted paths.

    `tol` forgives float differences at or below it. Ints, strings and bools are
    compared exactly whatever the tolerance, so a changed count or a flipped bar
    verdict is never absorbed by a numeric slack meant for rounding noise.
    """
    if type(a) is not type(b):
        return [f"{path or '<root>'}: type {type(a).__name__} vs {type(b).__name__}"]
    if isinstance(a, dict):
        out = []
        for key in sorted(set(a) | set(b)):
            here = f"{path}.{key}" if path else key
            if key not in a:
                out.append(f"{here}: missing on the left")
            elif key not in b:
                out.append(f"{here}: missing on the right")
            else:
                out.extend(_diff(a[key], b[key], here, tol))
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} vs {len(b)}"]
        out = []
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            out.extend(_diff(x, y, f"{path}[{i}]", tol))
        return out
    if a == b:
        return []
    if tol and isinstance(a, float) and isinstance(b, float) and abs(a - b) <= tol:
        return []
    return [f"{path}: {a!r} vs {b!r}"]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--regenerate",
        action="store_true",
        help="Run the table before comparing. Needs the pinned models and network.",
    )
    ap.add_argument(
        "--twice",
        action="store_true",
        help="Run the table twice and require the two outputs to agree exactly.",
    )
    ap.add_argument(
        "--tolerance",
        type=float,
        default=0.0,
        help=(
            "Forgive float differences at or below this when comparing against the "
            "committed table. Use it to reproduce on hardware other than the machine "
            "that generated the baseline; leave it at 0 on the same machine."
        ),
    )
    args = ap.parse_args()

    if not RESULTS.is_file():
        print(f"no committed baseline at {RESULTS}", file=sys.stderr)
        return 2

    baseline = json.loads(RESULTS.read_text())
    baseline_manifest = json.loads(MANIFEST.read_text()) if MANIFEST.is_file() else {}

    if not (args.regenerate or args.twice):
        print("nothing to do; pass --regenerate and/or --twice")
        return 0

    _run_table()
    first = json.loads(RESULTS.read_text())
    first_manifest = json.loads(MANIFEST.read_text())

    failures: list[str] = []

    regression = _diff(baseline, first, tol=args.tolerance)
    if regression:
        failures.append("committed results changed:")
        failures.extend(f"  {line}" for line in regression[:40])
        if len(regression) > 40:
            failures.append(f"  ... and {len(regression) - 40} more")

    pins_before = {k: v for k, v in baseline_manifest.items() if k not in VOLATILE_MANIFEST_KEYS}
    pins_after = {k: v for k, v in first_manifest.items() if k not in VOLATILE_MANIFEST_KEYS}
    pin_drift = _diff(pins_before, pins_after)
    if pin_drift:
        failures.append("manifest pins or split checksums moved:")
        failures.extend(f"  {line}" for line in pin_drift)

    if args.twice:
        _run_table()
        second = json.loads(RESULTS.read_text())
        wobble = _diff(first, second)
        if wobble:
            failures.append("two runs of the same checkout disagreed:")
            failures.extend(f"  {line}" for line in wobble[:40])

    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1

    checked = "regression" + (" and determinism" if args.twice else "")
    within = f" within {args.tolerance:g}" if args.tolerance else " exactly"
    print(f"ok: {checked} clean against {RESULTS.relative_to(ROOT)}{within}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
