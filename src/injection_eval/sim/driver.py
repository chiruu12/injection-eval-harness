"""Scenario corpus times each configured guard, on and off the tool-output boundary.

The episode metrics exist to be reported. This is the loop `make table` runs so
those numbers land in results.json rather than only in unit tests.
"""

from __future__ import annotations

from ..core.contracts import Episode, Scenario
from ..guard import Guard
from ..metrics.episode import guard_delta, summarise_episodes
from ..scenarios.registry import all_scenarios
from .runner import GuardPlacement, Runner

# The runner counts agent actions, not wall-clock turns. The longest corpus
# plan is 12 calls; a hijack inserts one extra action and the final answer
# needs another, so the runner default of 12 would truncate benign
# long-horizon tasks and report a false over-refusal.
_MAX_TURNS = 24


def run_guard_pair(
    guard: Guard,
    scenarios: list[Scenario],
) -> tuple[list[Episode], list[Episode]]:
    """The same scenarios with this guard on tool output, then with it off."""
    on_runner = Runner(max_turns=_MAX_TURNS, placement=GuardPlacement.TOOL_OUTPUT)
    off_runner = Runner(max_turns=_MAX_TURNS, placement=GuardPlacement.NONE)
    with_guard = [on_runner.run(scenario, guard) for scenario in scenarios]
    without_guard = [off_runner.run(scenario, guard) for scenario in scenarios]
    return with_guard, without_guard


def evaluate_episodes(
    guards: list[Guard],
    scenarios: list[Scenario] | None = None,
) -> dict:
    """Per-guard episode summaries and on/off deltas, shaped for results.json."""
    corpus = list(all_scenarios() if scenarios is None else scenarios)
    out: dict[str, dict] = {}
    for guard in guards:
        with_guard, without_guard = run_guard_pair(guard, corpus)
        out[guard.detector.key] = {
            "with_guard": summarise_episodes(with_guard),
            "without_guard": summarise_episodes(without_guard),
            "delta": guard_delta(with_guard, without_guard),
        }
    return out
