"""Policies map scores (and spans) onto Action. No model, no network."""

from injection_eval.core.contracts import Action, Policy, Span
from injection_eval.policies import RedactSpanPolicy, ThresholdPolicy, published_policy


def test_policies_satisfy_the_protocol():
    assert isinstance(ThresholdPolicy(0.5), Policy)
    assert isinstance(RedactSpanPolicy(0.9, 0.45), Policy)


def test_threshold_policy_allows_below_and_blocks_at_or_above():
    policy = ThresholdPolicy(threshold=0.5)
    assert policy.decide("x", 0.49, ()).action is Action.ALLOW
    assert policy.decide("x", 0.5, ()).action is Action.BLOCK
    assert policy.decide("x", 0.99, ()).action is Action.BLOCK


def test_redact_span_policy_allows_below_doc_threshold():
    policy = RedactSpanPolicy(threshold=0.9, span_threshold=0.45)
    span = Span(0, 4, 0.99)
    verdict = policy.decide("abcd", 0.89, (span,))
    assert verdict.action is Action.ALLOW
    assert verdict.content == "abcd"


def test_redact_span_policy_blocks_when_flagged_with_no_usable_spans():
    policy = RedactSpanPolicy(threshold=0.9, span_threshold=0.45)
    empty = policy.decide("abcd", 0.95, ())
    assert empty.action is Action.BLOCK
    weak = policy.decide("abcd", 0.95, (Span(0, 4, 0.2),))
    assert weak.action is Action.BLOCK


def test_redact_span_policy_removes_the_flagged_characters():
    policy = RedactSpanPolicy(threshold=0.5, span_threshold=0.5)
    text = "hello INJECT world"
    span = Span(6, 12, 0.95)
    verdict = policy.decide(text, 0.9, (span,))
    assert verdict.action is Action.REDACT
    assert "INJECT" not in verdict.content
    assert verdict.content == "hello [REDACTED] world"


def test_redact_span_policy_removes_overlapping_spans():
    policy = RedactSpanPolicy(threshold=0.5, span_threshold=0.5)
    text = "aaaINJECTbbb"
    verdict = policy.decide(text, 0.9, (Span(3, 7, 0.8), Span(5, 9, 0.9)))
    assert verdict.action is Action.REDACT
    assert "INJECT" not in verdict.content
    assert "aaa" in verdict.content and "bbb" in verdict.content


def test_published_policy_thresholds_match_the_committed_table():
    assert published_policy("regex-floor").threshold == 0.5
    assert published_policy("unplug-model").threshold == 0.9
    assert published_policy("unplug-pipeline").threshold == 0.5
    assert published_policy("protectai").threshold == 0.5
    unplug = published_policy("unplug-model")
    assert isinstance(unplug, RedactSpanPolicy)
    assert unplug.span_threshold == 0.45
