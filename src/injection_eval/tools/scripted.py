"""Tools whose output is fixed in advance, and the splicing that puts an attack in it.

A scripted tool is what makes an episode reproducible. The agent believes it
called a retriever or read a ticket; the harness knows exactly which characters
it handed back and which of them are the payload.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.contracts import Span, ToolCall, ToolResult


@dataclass(frozen=True)
class ScriptedTool:
    """Returns canned content, optionally with an injected payload spliced in.

    `responses` is consulted in call order: the first call gets `responses[0]`,
    the second `responses[1]`, and the last entry repeats if the agent keeps
    calling. A tool with no responses returns an empty, failed result rather than
    raising, so a scenario that over-calls degrades visibly instead of crashing
    the run.
    """

    name: str
    responses: tuple[str, ...] = ()
    payload: str | None = None
    payload_at_call: int = 0
    payload_offset: int | None = None
    _calls: list[int] = field(default_factory=list, repr=False, compare=False)

    def call(self, call: ToolCall) -> ToolResult:
        n = len(self._calls)
        self._calls.append(n)
        if not self.responses:
            return ToolResult(tool=self.name, content="", ok=False)
        body = self.responses[min(n, len(self.responses) - 1)]
        if self.payload is None or n != self.payload_at_call:
            return ToolResult(tool=self.name, content=body)
        return splice(self.name, body, self.payload, self.payload_offset)

    def reset(self) -> None:
        """Clear call state so one scenario definition can be run more than once."""
        self._calls.clear()


def splice(
    tool: str, carrier: str, payload: str, offset: int | None = None
) -> ToolResult:
    """Insert `payload` into `carrier` and record exactly where it landed.

    `offset` is a character index into the carrier; None means the midpoint, on a
    line boundary where one is available. The returned span is ground truth and is
    never shown to a detector.
    """
    if offset is None:
        mid = len(carrier) // 2
        nl = carrier.find("\n", mid)
        offset = nl + 1 if nl != -1 else mid
    offset = max(0, min(offset, len(carrier)))
    content = carrier[:offset] + payload + carrier[offset:]
    return ToolResult(
        tool=tool,
        content=content,
        payload_span=Span(offset, offset + len(payload), 1.0),
    )
