"""Scenario plus optional Guard to a finished Episode.

The runner is the only place the turn loop lives. Placement is a constructor
argument so "guard on tool output", "guard on user input", and "no guard" share
this loop rather than forking it.
"""

from __future__ import annotations

from enum import Enum

from ..core.contracts import (
    Action,
    Episode,
    Guard,
    Scenario,
    Tool,
    ToolCall,
    ToolResult,
    Turn,
    TurnKind,
    Verdict,
)

# Short enough that a blocked turn cannot be mistaken for tool output.
BLOCKED_NOTICE = "blocked by guard"


class GuardPlacement(str, Enum):
    """Which untrusted boundary the guard sits on for this run."""

    NONE = "none"
    TOOL_OUTPUT = "tool_output"
    USER_INPUT = "user_input"


class Runner:
    """The episode loop: one scenario, an optional guard, a finished trajectory."""

    def __init__(
        self,
        *,
        max_turns: int = 12,
        placement: GuardPlacement = GuardPlacement.TOOL_OUTPUT,
    ) -> None:
        self.max_turns = max_turns
        self.placement = placement

    def run(self, scenario: Scenario, guard: Guard | None = None) -> Episode:
        """One finished trajectory for this scenario and guard."""
        agent = scenario.build_agent()
        tools = scenario.build_tools()
        _reset(agent)
        for tool in tools.values():
            _reset(tool)

        turns: list[Turn] = []
        # contracts.Scenario is frozen without this field; every runnable
        # scenario carries an opening request the loop can put on turn 0.
        opening: str = scenario.opening_request  # type: ignore[attr-defined]
        user_text, user_verdict = self._filter(
            opening, at=GuardPlacement.USER_INPUT, guard=guard
        )
        turns.append(
            Turn(
                index=0,
                kind=TurnKind.USER,
                content=user_text,
                verdict=user_verdict,
            )
        )

        answered = False
        for _ in range(self.max_turns):
            action = agent.act(turns)
            if isinstance(action, str):
                turns.append(
                    Turn(
                        index=len(turns),
                        kind=TurnKind.AGENT,
                        content=action,
                    )
                )
                answered = True
                break
            if not isinstance(action, ToolCall):
                msg = f"agent returned {type(action).__name__}, expected ToolCall or str"
                raise TypeError(msg)
            turns.append(
                Turn(
                    index=len(turns),
                    kind=TurnKind.AGENT,
                    content=action.tool,
                    tool_call=action,
                )
            )
            result = _invoke(tools, action)
            visible, verdict = self._filter(
                result.content, at=GuardPlacement.TOOL_OUTPUT, guard=guard
            )
            turns.append(
                Turn(
                    index=len(turns),
                    kind=TurnKind.TOOL,
                    content=visible,
                    tool_result=result,
                    verdict=verdict,
                )
            )

        return Episode(
            scenario=scenario.key,
            guard=_guard_label(guard, self.placement),
            turns=tuple(turns),
            attack_succeeded=scenario.objective_met(turns),
            task_completed=scenario.task_completed(turns),
            stopped_early=not answered,
        )

    def _filter(
        self,
        text: str,
        *,
        at: GuardPlacement,
        guard: Guard | None,
    ) -> tuple[str, Verdict | None]:
        # Same branch for every placement: skip unless this run sits here.
        if guard is None or self.placement is not at:
            return text, None
        verdict = guard.inspect(text)
        return _visible(verdict, text), verdict


def _visible(verdict: Verdict, original: str) -> str:
    if verdict.action is Action.BLOCK:
        return BLOCKED_NOTICE
    if verdict.action is Action.REDACT:
        return verdict.content
    return original


def _invoke(tools: dict[str, Tool], call: ToolCall) -> ToolResult:
    tool = tools.get(call.tool)
    if tool is None:
        return ToolResult(tool=call.tool, content="", ok=False)
    return tool.call(call)


def _reset(obj: object) -> None:
    reset = getattr(obj, "reset", None)
    if callable(reset):
        reset()


def _guard_label(guard: Guard | None, placement: GuardPlacement) -> str:
    if guard is None or placement is GuardPlacement.NONE:
        return "none"
    return guard.name
