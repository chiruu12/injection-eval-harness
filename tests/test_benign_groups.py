"""Benign controls are two strata, not one blended utility cell. No network."""

from injection_eval.detectors.regex_floor import regex_hits
from injection_eval.scenarios import all_scenarios, by_benign_group
from injection_eval.scenarios.scenario import ADVERSARIAL_BENIGN, PLAIN_BENIGN
from injection_eval.sim.runner import GuardPlacement, Runner

# 9 plain, 3 adversarial. The mix is a declared design choice, not a sample
# from boundary-pairs; see benign_controls module docstring.
_DECLARED_PLAIN = 9
_DECLARED_ADVERSARIAL = 3


def _tool_responses(scenario) -> list[str]:
    texts: list[str] = []
    for tool in scenario.build_tools().values():
        texts.extend(getattr(tool, "responses", ()))
    return texts


def test_by_benign_group_partitions_every_benign_scenario():
    groups = by_benign_group()
    assert set(groups) == {PLAIN_BENIGN, ADVERSARIAL_BENIGN}
    grouped = [s.key for group in groups.values() for s in group]
    benign = [s.key for s in all_scenarios() if s.benign]
    attacks = [s.key for s in all_scenarios() if not s.benign]
    assert set(grouped) == set(benign)
    assert len(grouped) == len(benign) == len(set(grouped))
    assert not set(grouped) & set(attacks)
    for s in all_scenarios():
        if s.benign:
            assert s.benign_group in {PLAIN_BENIGN, ADVERSARIAL_BENIGN}, s.key
        else:
            assert s.benign_group == "", s.key


def test_plain_benign_tool_outputs_have_zero_keyword_bait():
    for s in by_benign_group()[PLAIN_BENIGN]:
        for text in _tool_responses(s):
            assert regex_hits(text) == [], (s.key, regex_hits(text))


def test_every_adversarial_benign_scenario_trips_the_regex_floor():
    group = by_benign_group()[ADVERSARIAL_BENIGN]
    assert group, "adversarial cell is empty, so it tests nothing"
    for s in group:
        hits = [regex_hits(text) for text in _tool_responses(s)]
        assert any(hits), s.key


def test_declared_plain_to_adversarial_ratio():
    groups = by_benign_group()
    assert len(groups[PLAIN_BENIGN]) == _DECLARED_PLAIN
    assert len(groups[ADVERSARIAL_BENIGN]) == _DECLARED_ADVERSARIAL
    assert len(groups[PLAIN_BENIGN]) == 3 * len(groups[ADVERSARIAL_BENIGN])


def test_every_benign_scenario_completes_unguarded():
    runner = Runner(max_turns=24, placement=GuardPlacement.NONE)
    for s in all_scenarios():
        if not s.benign:
            continue
        ep = runner.run(s)
        assert ep.task_completed is True, s.key


def test_attack_scenarios_keep_unguarded_outcomes():
    runner = Runner(max_turns=24, placement=GuardPlacement.NONE)
    for s in all_scenarios():
        if s.benign:
            continue
        ep = runner.run(s)
        assert ep.attack_succeeded is True, s.key
        assert ep.task_completed is True, s.key
