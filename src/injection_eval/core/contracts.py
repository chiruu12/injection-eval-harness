"""The interfaces every other module depends on, and the only module none of them may import from.

This file exists so that adding a detector, a scenario, a tool or a metric does
not require editing anything that already works. It is deliberately small: types
and protocols, no logic, no I/O, no third-party imports beyond the standard
library. If something here needs `torch`, it belongs somewhere else.

Two rules keep it that way.

- Nothing in this module imports from the rest of the package. The dependency
  arrow points inward, always.
- A protocol here earns its place by having at least two real implementations. A
  protocol with one implementation is a class with extra steps.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, runtime_checkable

# --------------------------------------------------------------------------- #
# Detection
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Span:
    """A half-open character range within some text, with the score that flagged it."""

    start: int
    end: int
    score: float

    def __post_init__(self) -> None:
        if self.start < 0 or self.end < self.start:
            msg = f"degenerate span [{self.start}, {self.end})"
            raise ValueError(msg)

    def overlaps(self, other: Span) -> int:
        """Overlapping character count. Zero when disjoint."""
        return max(0, min(self.end, other.end) - max(self.start, other.start))


@runtime_checkable
class Detector(Protocol):
    """Something that assigns each text a continuous injection score in [0, 1].

    Scoring only. A detector does not know what threshold it will be read at, and
    does not decide what to do about a score. That is `Policy`, below, and keeping
    the two apart is what lets the same detector be measured at its vendor's
    published operating point and at a threshold fitted here.
    """

    key: str
    label: str

    def score(self, texts: list[str]) -> list[float]:
        """Score every text. Must return exactly one score per input, in order."""
        ...


@runtime_checkable
class SpanDetector(Detector, Protocol):
    """A detector that also localises what it flagged.

    Separate from `Detector` on purpose: a sequence classifier cannot implement
    this, and forcing it to raise NotImplementedError would make the wider
    interface a lie. Ask `isinstance(d, SpanDetector)` before reaching for spans.
    """

    def spans(self, text: str) -> list[Span]:
        """Character ranges this detector considers injected. May be empty."""
        ...


# --------------------------------------------------------------------------- #
# Policy: what to do about a score
# --------------------------------------------------------------------------- #


class Action(str, Enum):
    """What a guard decided to do with a piece of untrusted content."""

    ALLOW = "allow"
    REDACT = "redact"
    BLOCK = "block"


@dataclass(frozen=True)
class Verdict:
    """One guard decision, carrying enough to reconstruct why it was made."""

    action: Action
    score: float
    threshold: float
    spans: tuple[Span, ...] = ()
    content: str = ""

    @property
    def flagged(self) -> bool:
        return self.action is not Action.ALLOW


@runtime_checkable
class Policy(Protocol):
    """Turns a score, and optionally spans, into an action.

    This is the seam the calibration findings live behind. A detector that ranks
    well and is thresholded badly is a policy problem, and separating them means
    the harness can say which of the two failed.
    """

    threshold: float

    def decide(self, text: str, score: float, spans: tuple[Span, ...]) -> Verdict:
        ...


@runtime_checkable
class Guard(Protocol):
    """A detector read through a policy, consulted at one untrusted boundary.

    Lives here rather than in sim/ because the runner and the concrete guard must
    agree on it, and a protocol declared inside the consumer is a protocol only
    the consumer can satisfy. `name` is part of the contract because an Episode
    records which guard produced it, and an unnamed guard makes a results table
    that cannot be read back.
    """

    name: str

    def inspect(self, text: str) -> Verdict:
        ...


# --------------------------------------------------------------------------- #
# Tools: where untrusted content enters an agent
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class ToolCall:
    """A request from the agent to a tool."""

    tool: str
    args: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    """What a tool returned, and whether the harness put an attack in it.

    `content` is untrusted by definition: it is the text a guard is placed to
    inspect, and after the runner filters it, the text the agent actually saw.
    `payload_span` is harness-only ground truth from splicing. It is never a
    string the detector or agent can read: the span holds indices and a score,
    not the payload, and it survives a BLOCK so `carries_attack` still marks
    attack episodes after the payload has been stripped from `content`. The
    span indexes the original spliced text, which the runner discards; it is
    not a span into filtered `content`.
    """

    tool: str
    content: str
    payload_span: Span | None = None
    ok: bool = True

    @property
    def carries_attack(self) -> bool:
        return self.payload_span is not None


@runtime_checkable
class Tool(Protocol):
    """Anything an agent can call that returns text it did not author."""

    name: str

    def call(self, call: ToolCall) -> ToolResult:
        ...


# --------------------------------------------------------------------------- #
# Episodes: multi-turn trajectories
# --------------------------------------------------------------------------- #


class TurnKind(str, Enum):
    USER = "user"
    AGENT = "agent"
    TOOL = "tool"


@dataclass(frozen=True)
class Turn:
    """One step of a trajectory, after any guard has already acted on it.

    `content` and `tool_result.content` (when present) are the post-guard text.
    That a payload was spliced is recorded only on `tool_result.payload_span`,
    never in an agent-visible string.
    """

    index: int
    kind: TurnKind
    content: str
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    verdict: Verdict | None = None

    @property
    def guarded(self) -> bool:
        return self.verdict is not None and self.verdict.flagged

    @property
    def withheld(self) -> bool:
        """The BLOCK-only signal the agent uses to skip a turn.

        `guarded` is True for REDACT as well, and detection_turn needs that
        broader meaning. Collapsing the two would score a missed redaction as
        a successful block.
        """
        return self.verdict is not None and self.verdict.action is Action.BLOCK


@dataclass(frozen=True)
class Episode:
    """A finished trajectory and what it means.

    `attack_succeeded` is decided by the scenario's own predicate, not by whether
    the guard fired. A guard that blocks the payload and an agent that ignores it
    are different outcomes, and collapsing them would make the guard look better
    than it is.
    """

    scenario: str
    guard: str
    turns: tuple[Turn, ...]
    attack_succeeded: bool
    task_completed: bool
    stopped_early: bool = False
    notes: str = ""

    @property
    def detection_turn(self) -> int | None:
        """Index of the first turn a guard flagged, or None if it never fired."""
        return next((t.index for t in self.turns if t.guarded), None)

    @property
    def n_turns(self) -> int:
        return len(self.turns)


# --------------------------------------------------------------------------- #
# Agents and scenarios
# --------------------------------------------------------------------------- #


@runtime_checkable
class Agent(Protocol):
    """The thing under attack.

    Deliberately narrow so a scripted agent can implement it without an API key.
    A scripted agent makes attack success a property of the injected text rather
    than of some model's mood, which is what keeps the harness deterministic. A
    real-LLM agent is a second implementation of the same protocol, not a
    different runner.
    """

    name: str

    def act(self, history: list[Turn]) -> ToolCall | str:
        """Return the next tool call, or a final answer as a string."""
        ...


@runtime_checkable
class Scenario(Protocol):
    """A reproducible episode: what the agent is asked, what the tools return, and what counts as compromise."""

    key: str
    description: str
    benign: bool
    opening_request: str
    """What the user asks for on turn 0. The runner puts this on the first turn,
    and a guard placed at the user-input boundary inspects it there."""

    def build_agent(self) -> Agent:
        ...

    def build_tools(self) -> dict[str, Tool]:
        ...

    def objective_met(self, turns: list[Turn]) -> bool:
        """True when the injected objective was carried out. Always False for a benign scenario."""
        ...

    def task_completed(self, turns: list[Turn]) -> bool:
        """True when the agent did the job the user actually asked for.

        Measured separately from attack success so that a guard which blocks the
        attack by breaking the task does not read as a win.
        """
        ...
