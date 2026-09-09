"""The episode driver actually runs the corpus. No model, no network."""

import json

from injection_eval.detectors.regex_floor import RegexFloor
from injection_eval.guard import Guard
from injection_eval.policies import published_policy
from injection_eval.scenarios.registry import all_scenarios
from injection_eval.sim.driver import evaluate_episodes


def _regex_guard() -> Guard:
    return Guard(RegexFloor(), published_policy("regex-floor"))


def test_evaluate_episodes_shape_matches_what_results_json_will_store():
    block = evaluate_episodes([_regex_guard()])
    assert list(block) == ["regex-floor"]
    row = block["regex-floor"]
    assert set(row) == {"with_guard", "without_guard", "delta"}
    for side in ("with_guard", "without_guard"):
        assert set(row[side]) == {
            "n_episodes",
            "attack_success",
            "utility",
            "detection_turns",
            "late_detection",
            "position_sensitivity",
        }
    n = len(all_scenarios())
    assert row["with_guard"]["n_episodes"] == n
    assert row["without_guard"]["n_episodes"] == n
    assert row["delta"]["n_scenarios"] == n
    assert json.loads(json.dumps(block)) == block


def test_unguarded_run_never_fires_and_completes_the_benign_tasks():
    # max_turns must cover the 12-call briefing; if it did not, utility
    # without a guard would drop and this test would be the one that says so.
    row = evaluate_episodes([_regex_guard()])["regex-floor"]
    off = row["without_guard"]
    assert off["detection_turns"]["never_fired"] == off["n_episodes"]
    assert off["detection_turns"]["never_fired_share"] == 1.0
    assert off["late_detection"]["late_detection_rate"] == 0.0
    assert off["attack_success"]["attack_success_rate"] == 1.0
    assert row["delta"]["utility_rate_without_guard"] == 1.0


def test_position_sensitivity_covers_the_long_horizon_pos_slots():
    pos = evaluate_episodes([_regex_guard()])["regex-floor"]["with_guard"]["position_sensitivity"]
    assert list(pos) == ["pos01", "pos05", "pos10"]
    for suffix in pos:
        assert pos[suffix]["n"] == 1


def test_two_driver_runs_agree():
    guard = _regex_guard()
    first = evaluate_episodes([guard])
    second = evaluate_episodes([guard])
    assert first == second
