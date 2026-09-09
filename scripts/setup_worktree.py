#!/usr/bin/env python3
"""Provision the virtualenv and locked dependencies for a checkout.

One entry point so CI and a fresh local clone provision identically, and so the
steps stay in a file that can be read rather than spread across workflow yaml.
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
