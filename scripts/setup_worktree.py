#!/usr/bin/env python3
"""Provision a marshal worktree.

Exists because `worktree_setup` is exec'd directly rather than through a shell,
so `a && b` reaches uv as a literal argument and fails with a usage error. One
entry point, several steps.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv" / "bin" / "python"


def run(*cmd: str) -> None:
    print("+", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)


def main() -> int:
    run("uv", "venv", "--python", "3.12", str(ROOT / ".venv"))
    run("uv", "sync", "--frozen", "--extra", "dev")
    return 0


if __name__ == "__main__":
    sys.exit(main())
