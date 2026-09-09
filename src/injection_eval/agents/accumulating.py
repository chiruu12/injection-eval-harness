"""An agent whose susceptibility is the concatenation of every tool result it was allowed to read.

Split-payload attacks are invisible to a detector that scores one tool result
at a time, and they are also invisible to ScriptedAgent, which only looks at
the last turn. This implementation is the model of an agent that keeps tool
text in context, so that family measures the detector rather than the stub.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..core.contracts import ToolCall, Turn, TurnKind


@dataclass
class AccumulatingAgent:
    """Follows a fixed plan, and obeys an imperative assembled across readable tool output.

    The compliance rule is the same as ScriptedAgent's, except the trigger is
    matched against every tool result that actually reached the agent, joined
    in order. A fragment that is innocuous alone can still hijack once later
    fragments fill it in, which is the case the split-payload family exists to
    measure.
    """

    name: str = "accumulating"
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

    def _readable_buffer(self, history: list[Turn]) -> str:
        """The agent's working context: every tool turn it was allowed to read.

        Empty-string join: this family splits trigger words across results
        ("prev" + "ious"). A newline or space would be closer to a chat
        transcript and would make those splits fail to assemble, so the
        family would measure the separator rather than the detector.
        """
        return "".join(
            t.content for t in history if t.kind is TurnKind.TOOL and not t.withheld
        )

    def _hijack(self, history: list[Turn]) -> ToolCall | None:
        """The attacker's tool call, if readable tool text has assembled a trigger.

        BLOCK never enters the buffer, so a guard that withholds a fragment
        gets credit. REDACT does enter, because that is the string the agent
        saw. An already-issued attack call is not repeated: ScriptedAgent
        stops after the last turn no longer matches, and a growing buffer would
        otherwise re-issue forever.
        """
        buffer = self._readable_buffer(history)
        for pattern, call in self.triggers:
            already = any(
                t.kind is TurnKind.AGENT and t.tool_call == call for t in history
            )
            if already:
                continue
            if re.search(pattern, buffer, re.IGNORECASE):
                return call
        return None

    def reset(self) -> None:
        self._step = 0
