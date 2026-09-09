"""`make fetch`: pull every pinned artifact and print a manifest.

Separated from `make table` so the download is a distinct, cacheable step and so
a pin that has gone stale fails here rather than mid-evaluation.
"""

from __future__ import annotations

from huggingface_hub import snapshot_download

from .data import load_split
from .pins import DATASETS, MODELS


def main() -> None:
    for key, pin in MODELS.items():
        path = snapshot_download(pin.repo_id, revision=pin.sha)
        print(f"model  {key:14s} {pin.repo_id}@{pin.sha[:12]} -> {path}")

    for dataset, splits in (("boundary_pairs", ("validation", "test")), ("deepset", ("test",))):
        pin = DATASETS[dataset]
        for split in splits:
            s = load_split(dataset, split)
            print(
                f"data   {dataset:14s} {pin.repo_id}@{pin.sha[:12]} "
                f"{split:10s} n={len(s):4d} pos={sum(e.label for e in s.examples):4d} "
                f"checksum={s.checksum}"
            )


if __name__ == "__main__":
    main()
