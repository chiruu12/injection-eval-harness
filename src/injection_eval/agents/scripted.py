"""A deterministic stand-in for the model under attack.

The agent's only job in this harness is to be compromisable in a way that is
decidable. A real LLM would make attack success a function of sampling
temperature; this makes it a function of the injected text and the guard, which
is the variable under study. An LLM-backed agent implementing the same protocol
can be added later without touching the runner.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.contracts import ToolCall, Turn, TurnKind


@dataclass
class ScriptedAgent:
    """Follows a fixed plan, and obeys any imperative it reads in tool output.

    The compliance rule is the model of susceptibility: if a tool result that
    reached the agent contains a trigger phrase, the agent's next action becomes
    the action that phrase demands. That is a generous model of a weak agent, and
    it is stated here rather than buried so nobody reads an attack success rate
    from this harness as an attack success rate against a frontier model.
    """

    name: str = "scripted"
    plan: tuple[ToolCall, ...] = ()
    final: str = "done"
    triggers: tuple[tuple[str, ToolCall], ...] = ()
    _step: int = field(default=0, repr=False)

    def act(self, history: list[Turn]) -> ToolCall | str:
        hijack = self._hijack(history)
        if hijack is not None:
            return hijack
        if self._step < len(self.plan):
            call = self.plan[self._step]
            self._step += 1
            return call
        return self.final

    def _hijack(self, history: list[Turn]) -> ToolCall | None:
        """The most recent unguarded tool result wins, if it carries a trigger.

        Only the last tool turn is consulted. An agent that re-reads its whole
        history and re-triggers on turn 9 for something it saw on turn 2 would
        make detection-turn meaningless.
        """
        last = next(
            (t for t in reversed(history) if t.kind is TurnKind.TOOL), None
        )
        if last is None or last.guarded:
            return None
        for pattern, call in self.triggers:
            if re.search(pattern, last.content, re.IGNORECASE):
                return call
        return None

    def reset(self) -> None:
        self._step = 0
