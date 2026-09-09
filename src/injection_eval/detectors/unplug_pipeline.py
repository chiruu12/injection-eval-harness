"""The Unplug SDK as a caller actually constructs it.

Disclosure: the author works on Unplug. This row exists so the gap between the
checkpoint and the SDK default policy is a measured quantity, not a footnote.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property


@dataclass
class UnplugPipeline:
    """`Guard.with_tiny()`: regex stage plus model, SDK default policy."""

    key: str = "unplug-pipeline"
    label: str = "Unplug SDK Guard.with_tiny(), regex + model"

    @cached_property
    def _guard(self):
        from unplug import Guard

        return Guard.with_tiny()

    def score(self, texts: list[str]) -> list[float]:
        return [float(self._guard.scan(t).risk_score) for t in texts]

    def stages(self, text: str) -> list[str]:
        """Which stage produced each finding. Used for the regex-vs-model split."""
        return [f.stage for f in self._guard.scan(text).findings]
