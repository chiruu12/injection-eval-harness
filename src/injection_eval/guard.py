"""A detector and a policy, sitting on a piece of untrusted text.

Scoring and acting stay independently swappable: the same detector can be
measured under two policies, and the same policy can wrap two detectors. This
object does not know about tools, turns, or episodes; where it is placed is the
caller's decision.
"""

from __future__ import annotations

from dataclasses import dataclass

from .core.contracts import Detector, Policy, SpanDetector, Verdict


@dataclass
class Guard:
    """The inspectable boundary: a Detector read through a Policy."""

    detector: Detector
    policy: Policy

    @property
    def name(self) -> str:
        """Identifies this guard in an Episode. Detector and threshold together,
        because the same detector under two thresholds is two guards as far as
        any result table is concerned."""
        return f"{self.detector.key}@{self.policy.threshold:g}"

    def inspect(self, text: str) -> Verdict:
        """The boundary decision for one untrusted string."""
        return self.inspect_many([text])[0]

    def inspect_many(self, texts: list[str]) -> list[Verdict]:
        """The boundary decision for each untrusted string, in input order."""
        # Score the whole batch at once: padded batches of 1 change ProtectAI logits.
        scores = self.detector.score(texts)
        detector = self.detector
        take_spans = isinstance(detector, SpanDetector)
        out: list[Verdict] = []
        for text, score in zip(texts, scores, strict=True):
            spans = tuple(detector.spans(text)) if take_spans else ()
            out.append(self.policy.decide(text, score, spans))
        return out
