"""Operating points: what to do with a score, including each vendor's published one."""

from __future__ import annotations

from dataclasses import dataclass

from ..core.contracts import Action, Policy, Span, Verdict

# Vendor-published document thresholds. Changing these changes every thresholded
# number in results/results.json.
_REGEX_FLOOR_THRESHOLD = 0.5
_UNPLUG_DOC_THRESHOLD = 0.9
_UNPLUG_SPAN_THRESHOLD = 0.45
_UNPLUG_PIPELINE_THRESHOLD = 0.5
_PROTECTAI_THRESHOLD = 0.5

_PLACEHOLDER = "[REDACTED]"


@dataclass(frozen=True)
class ThresholdPolicy:
    """A hard cutoff: at or above `threshold` the text is blocked, otherwise allowed."""

    threshold: float
    threshold_source: str = ""

    def decide(self, text: str, score: float, spans: tuple[Span, ...]) -> Verdict:
        if score >= self.threshold:
            return Verdict(
                action=Action.BLOCK,
                score=score,
                threshold=self.threshold,
                spans=spans,
            )
        return Verdict(
            action=Action.ALLOW,
            score=score,
            threshold=self.threshold,
            spans=spans,
            content=text,
        )


def _merge(spans: tuple[Span, ...]) -> list[Span]:
    ordered = sorted(spans, key=lambda s: (s.start, s.end))
    merged: list[Span] = []
    for span in ordered:
        if merged and span.start <= merged[-1].end:
            prev = merged[-1]
            merged[-1] = Span(prev.start, max(prev.end, span.end), max(prev.score, span.score))
        else:
            merged.append(span)
    return merged


def _redact(text: str, spans: tuple[Span, ...]) -> str:
    out = text
    for span in reversed(_merge(spans)):
        out = out[: span.start] + _PLACEHOLDER + out[span.end :]
    return out


@dataclass(frozen=True)
class RedactSpanPolicy:
    """Unplug's operating point: cut out high-scoring spans, block when none are usable."""

    threshold: float
    span_threshold: float
    threshold_source: str = ""

    def decide(self, text: str, score: float, spans: tuple[Span, ...]) -> Verdict:
        if score < self.threshold:
            return Verdict(
                action=Action.ALLOW,
                score=score,
                threshold=self.threshold,
                spans=spans,
                content=text,
            )
        usable = tuple(s for s in spans if s.score >= self.span_threshold)
        if usable:
            return Verdict(
                action=Action.REDACT,
                score=score,
                threshold=self.threshold,
                spans=usable,
                content=_redact(text, usable),
            )
        return Verdict(
            action=Action.BLOCK,
            score=score,
            threshold=self.threshold,
            spans=spans,
        )


def published_policy(detector_key: str) -> Policy:
    """The vendor's published operating point for this table row."""
    if detector_key == "regex-floor":
        return ThresholdPolicy(
            threshold=_REGEX_FLOOR_THRESHOLD,
            threshold_source="one match fires",
        )
    if detector_key == "unplug-model":
        return RedactSpanPolicy(
            threshold=_UNPLUG_DOC_THRESHOLD,
            span_threshold=_UNPLUG_SPAN_THRESHOLD,
            threshold_source="model card: doc_threshold 0.9",
        )
    if detector_key == "unplug-pipeline":
        return ThresholdPolicy(
            threshold=_UNPLUG_PIPELINE_THRESHOLD,
            threshold_source="SDK default block action",
        )
    if detector_key == "protectai":
        return ThresholdPolicy(
            threshold=_PROTECTAI_THRESHOLD,
            threshold_source="argmax, the model card's usage example",
        )
    raise ValueError(f"no published policy for {detector_key!r}")
