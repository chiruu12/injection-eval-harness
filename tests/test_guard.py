"""Guard is the inspectable boundary. Stubs only; no model, no network."""

from dataclasses import dataclass

from injection_eval.core.contracts import Action, Detector, Span, SpanDetector
from injection_eval.guard import Guard
from injection_eval.policies import RedactSpanPolicy, ThresholdPolicy


@dataclass
class StubDetector:
    """A fixed score, so Guard tests do not touch a real model."""

    key: str = "stub"
    label: str = "stub"
    value: float = 0.4

    def score(self, texts: list[str]) -> list[float]:
        return [self.value] * len(texts)


@dataclass
class StubSpanDetector:
    """A fixed score plus one span, for the redact path."""

    key: str = "stub-span"
    label: str = "stub-span"
    value: float = 0.95
    flagged: tuple[int, int, float] = (6, 12, 0.99)

    def score(self, texts: list[str]) -> list[float]:
        return [self.value] * len(texts)

    def spans(self, text: str) -> list[Span]:
        start, end, score = self.flagged
        return [Span(start, end, score)]


def test_stubs_satisfy_the_protocols():
    assert isinstance(StubDetector(), Detector)
    assert not isinstance(StubDetector(), SpanDetector)
    assert isinstance(StubSpanDetector(), SpanDetector)


def test_guard_inspect_many_returns_one_verdict_per_text():
    guard = Guard(StubDetector(value=0.4), ThresholdPolicy(0.5))
    verdicts = guard.inspect_many(["a", "b"])
    assert [v.action for v in verdicts] == [Action.ALLOW, Action.ALLOW]
    guard_hi = Guard(StubDetector(value=0.9), ThresholdPolicy(0.5))
    assert guard_hi.inspect("secret").action is Action.BLOCK


def test_guard_redacts_when_the_detector_supplies_spans():
    guard = Guard(StubSpanDetector(), RedactSpanPolicy(threshold=0.9, span_threshold=0.45))
    verdict = guard.inspect("hello INJECT world")
    assert verdict.action is Action.REDACT
    assert "INJECT" not in verdict.content
    assert verdict.content == "hello [REDACTED] world"
