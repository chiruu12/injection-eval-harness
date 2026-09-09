"""The scenario corpus, listed in one place so a run can enumerate it without importing each family."""

from __future__ import annotations

from ..core.contracts import Scenario
from .benign_controls import SCENARIOS as BENIGN_CONTROLS
from .long_horizon import SCENARIOS as LONG_HORIZON
from .single_turn import SCENARIOS as SINGLE_TURN
from .split_payload import SCENARIOS as SPLIT_PAYLOAD


def all_scenarios() -> list[Scenario]:
    """The full corpus, in a stable family order, for anything that walks every episode."""
    return [*SINGLE_TURN, *LONG_HORIZON, *SPLIT_PAYLOAD, *BENIGN_CONTROLS]


def by_family() -> dict[str, list[Scenario]]:
    """The corpus grouped by attack shape, for tables that split on family."""
    return {
        "single_turn": list(SINGLE_TURN),
        "long_horizon": list(LONG_HORIZON),
        "split_payload": list(SPLIT_PAYLOAD),
        "benign_controls": list(BENIGN_CONTROLS),
    }
