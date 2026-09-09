"""Load the pinned evaluation splits.

The upstream splits are used exactly as published. The harness never re-splits,
re-balances or re-samples, so "frozen split" means the same thing to anyone who
re-runs it. Thresholds are fit on `validation` and `test` is read once.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from datasets import load_dataset

from .pins import DATASETS


@dataclass(frozen=True)
class Example:
    uid: str
    text: str
    label: int          # 1 = injection, 0 = benign
    pair_id: str | None  # boundary-pairs only; the benign twin shares it


@dataclass(frozen=True)
class Split:
    dataset: str
    name: str
    examples: list[Example]

    @property
    def checksum(self) -> str:
        h = hashlib.sha256()
        for e in self.examples:
            h.update(e.uid.encode())
            h.update(b"\x00")
            h.update(e.text.encode())
            h.update(b"\x00")
            h.update(str(e.label).encode())
            h.update(b"\x01")
        return h.hexdigest()[:16]

    def __len__(self) -> int:
        return len(self.examples)


def _boundary_pairs(split: str) -> Split:
    pin = DATASETS["boundary_pairs"]
    ds = load_dataset(pin.repo_id, revision=pin.sha, split=split)
    rows = [
        Example(
            uid=r["id"],
            text=r["text"],
            label=int(r["label"]),
            pair_id=r["pair_id"],
        )
        for r in ds
    ]
    rows.sort(key=lambda e: e.uid)
    return Split("boundary_pairs", split, rows)


def _deepset(split: str) -> Split:
    pin = DATASETS["deepset"]
    ds = load_dataset(pin.repo_id, revision=pin.sha, split=split)
    rows = [
        Example(
            uid=f"deepset-{split}-{i:04d}",
            text=r["text"],
            label=int(r["label"]),
            pair_id=None,
        )
        for i, r in enumerate(ds)
    ]
    return Split("deepset", split, rows)


_LOADERS = {"boundary_pairs": _boundary_pairs, "deepset": _deepset}


def load_split(dataset: str, split: str) -> Split:
    if dataset not in _LOADERS:
        msg = f"unknown dataset {dataset!r}; known: {sorted(_LOADERS)}"
        raise KeyError(msg)
    return _LOADERS[dataset](split)
