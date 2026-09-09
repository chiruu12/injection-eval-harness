"""Every external artifact this harness touches, pinned by commit sha.

Nothing in the harness resolves a name to `main`. If a pin is stale the fetch
fails loudly rather than silently evaluating a different artifact than the one
the results table claims.
"""

from __future__ import annotations

from dataclasses import dataclass

SEED = 20260912


@dataclass(frozen=True)
class DatasetPin:
    repo_id: str
    sha: str
    license: str
    published: str
    role: str


@dataclass(frozen=True)
class ModelPin:
    repo_id: str
    sha: str
    params: str
    published: str


DATASETS: dict[str, DatasetPin] = {
    # Published after every model under test. That constrains these Hub
    # repositories only: the set is synthetic_curated, so upload date is
    # not creation date and says nothing about what it was derived from.
    # Treat publication order as a weak control, not a firewall. Paired:
    # each attack has a benign twin sharing asset, role, tool and topic.
    "boundary_pairs": DatasetPin(
        repo_id="3nesdeniz/agentic-prompt-injection-boundary-pairs",
        sha="a5682e7573e1c7bc4b12e64d49c0dcd90ca776cf",
        license="cc-by-4.0",
        published="2026-07-13",
        role="primary",
    ),
    # 110K downloads, predates every model here. Almost certainly in the
    # training mix of every prompt-injection detector on the Hub. Present
    # as a control, not as a second result.
    "deepset": DatasetPin(
        repo_id="deepset/prompt-injections",
        sha="4f61ecb038e9c3fb77e21034b22511b523772cdd",
        license="apache-2.0",
        published="2023-05-17",
        role="contamination-control",
    ),
}

MODELS: dict[str, ModelPin] = {
    "unplug_tiny": ModelPin(
        repo_id="Unplug-AI/unplug-tiny-v1",
        sha="19b7d6701bea1f6d9f03ec7bcaeeea390dff43be",
        params="70.7M",
        published="2026-06-10",
    ),
    "protectai": ModelPin(
        repo_id="protectai/deberta-v3-base-prompt-injection-v2",
        sha="90c9989b1a342275dd0d1a95aad283c04e075671",
        params="184M",
        published="2024-04-01",
    ),
}
