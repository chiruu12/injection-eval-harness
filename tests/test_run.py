"""evaluate_shift, checked with a scripted detector. No model, no network."""

from dataclasses import dataclass

from injection_eval.data import Example, Split
from injection_eval.guard import Guard
from injection_eval.policies import ThresholdPolicy
from injection_eval.run import evaluate_shift
from injection_eval.transforms import TRANSFORMS


@dataclass
class KeywordDetector:
    """A stand-in whose fires are determined by substrings, so shift tests stay offline."""

    key: str = "keyword"
    label: str = "keyword"
    needles: tuple[str, ...] = ("INJECT",)

    def score(self, texts: list[str]) -> list[float]:
        return [1.0 if any(n in text for n in self.needles) else 0.0 for text in texts]


def _split(n: int = 4) -> Split:
    examples = []
    for i in range(n):
        examples.append(
            Example(
                uid=f"p{i}",
                text=f"INJECT payload {i}",
                label=1,
                pair_id=f"pair{i}",
                family="test",
            )
        )
        examples.append(
            Example(
                uid=f"b{i}",
                text=f"ordinary text {i}",
                label=0,
                pair_id=f"pair{i}",
                family="test",
            )
        )
    return Split("boundary_pairs", "test", examples)


def _guard() -> Guard:
    return Guard(KeywordDetector(), ThresholdPolicy(0.5))


def _identity(text: str, uid: str) -> str:
    return text


def _flag(text: str, uid: str) -> str:
    return f"INJECT {text}"


def test_evaluate_shift_returns_both_arms_for_every_transform():
    block = evaluate_shift(_split(), [_guard()])
    row = block["keyword"]
    assert row["n_positives"] == 4
    assert row["n_benign"] == 4
    assert set(row["transforms"]) == set(TRANSFORMS)
    for name, t in row["transforms"].items():
        assert t["n_positives"] == 4, name
        assert t["n_benign"] == 4, name
        assert t["recall"] is not None, name
        assert t["fpr"] is not None, name
        assert "fails_robustness_bar" in t, name
        assert "fails_fpr_bar" in t, name


def test_evaluate_shift_flags_a_transform_that_raises_fpr():
    block = evaluate_shift(
        _split(),
        [_guard()],
        transforms={"identity": _identity, "flag": _flag},
    )
    row = block["keyword"]
    assert row["baseline_recall"] == 1.0
    assert row["baseline_fpr"] == 0.0
    identity = row["transforms"]["identity"]
    assert identity["recall"] == 1.0
    assert identity["fpr"] == 0.0
    assert identity["fails_robustness_bar"] is False
    assert identity["fails_fpr_bar"] is False
    flag = row["transforms"]["flag"]
    assert flag["recall"] == 1.0
    assert flag["fpr"] == 1.0
    assert flag["fpr_delta"] == 1.0
    assert flag["false_positives"] == 4
    assert flag["n_benign"] == 4
    assert flag["fails_robustness_bar"] is False
    assert flag["fails_fpr_bar"] is True


def test_evaluate_shift_flags_neither_bar_when_both_arms_are_unchanged():
    block = evaluate_shift(
        _split(),
        [_guard()],
        transforms={"identity": _identity},
    )
    t = block["keyword"]["transforms"]["identity"]
    assert t["delta"] == 0.0
    assert t["fpr_delta"] == 0.0
    assert t["fails_robustness_bar"] is False
    assert t["fails_fpr_bar"] is False


def test_evaluate_shift_records_why_a_benign_arm_cannot_be_scored():
    def boom(text: str, uid: str) -> str:
        if "ordinary" in text:
            raise ValueError("not a payload")
        return text

    block = evaluate_shift(
        _split(n=2),
        [_guard()],
        transforms={"boom": boom},
    )
    t = block["keyword"]["transforms"]["boom"]
    assert t["recall"] == 1.0
    assert t["n_positives"] == 2
    assert t["fpr"] is None
    assert t["n_benign"] == 0
    assert t["fails_fpr_bar"] is False
    assert "benign_skipped" in t
    assert "ValueError" in t["benign_skipped"]
    assert "uid=" in t["benign_skipped"]
