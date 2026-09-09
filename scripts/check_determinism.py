#!/usr/bin/env python3
"""Assert that a re-run of the harness reproduces the committed numbers.

Two different failures are worth telling apart, so this checks both.

- Regression: the committed results/results.json is the contract. A refactor that
  moves a published number is a bug, and this catches it without anyone having to
  remember to look.
- Non-determinism: two runs of the same checkout must agree. If they do not,
  something is unpinned and the manifest is a description of an artifact that no
  longer exists.

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


def _diff(a: Any, b: Any, path: str = "") -> list[str]:
    """Every leaf where two parsed JSON documents disagree, as dotted paths."""
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
                out.extend(_diff(a[key], b[key], here))
        return out
    if isinstance(a, list):
        if len(a) != len(b):
            return [f"{path}: length {len(a)} vs {len(b)}"]
        out = []
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            out.extend(_diff(x, y, f"{path}[{i}]"))
        return out
    if a != b:
        return [f"{path}: {a!r} vs {b!r}"]
    return []


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
        help="Run the table twice and require the two outputs to agree.",
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

    regression = _diff(baseline, first)
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
    print(f"ok: {checked} clean against {RESULTS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
