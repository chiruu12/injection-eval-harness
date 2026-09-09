"""The interfaces every other module depends on, and the only module none of them may import from.

This file exists so that adding a detector, a scenario, a tool or a metric does
not require editing anything that already works. It is deliberately small: types
and protocols, no logic, no I/O, no third-party imports beyond the standard
library. If something here needs `torch`, it belongs somewhere else.

Two rules keep it that way.

- Nothing in this module imports from the rest of the package. The dependency
  arrow points inward, always.
- A protocol here earns its place by having at least two real implementations.
  That is a target. Detector has four (regex floor, unplug pipeline, unplug
  model, protectai), Policy has two (threshold and redact-span), and Agent has
  two (scripted and accumulating). SpanDetector, Guard, Tool, and Scenario each
  have one production class. A protocol with one implementation is a class with
  extra steps; those four stay because the runner and the adapters must agree
  on a shared shape, not because a second implementation exists.
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
        """Shared half-open overlap so span metrics do not each invent the formula.

        Zero when disjoint. run.py.evaluate_spans currently inlines the same
        arithmetic on predicted bounds; that file is owned elsewhere, so this
        stays as the one implementation those callers should switch to.
        """
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
    # The corpus writes this on every planned call. ScriptedTool.call ignores
    # the ToolCall, including args. Deleting the field would break scenarios/
    # which another worker owns; honouring args is that worker's job.
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
    # Runner and ScriptedTool write False when the tool is missing or has no
    # responses. tests/test_runner.py reads it. Metrics do not.
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
    # Runner writes this from Guard.name. tests/test_guard_runner_integration.py
    # reads it so a real Guard, not a stub, labels the episode. Metrics and
    # report.py group by detector key in the driver instead, which is a
    # reporting gap rather than dead weight.
    guard: str
    turns: tuple[Turn, ...]
    attack_succeeded: bool
    task_completed: bool
    # Runner writes this when the turn budget expired before a final answer.
    # tests/test_runner.py and tests/test_accumulating.py read it. Metrics and
    # report.py do not, which is a reporting gap (truncated vs finished is a
    # different outcome), not a reason to drop the field.
    stopped_early: bool = False

    @property
    def detection_turn(self) -> int | None:
        """Index of the first turn a guard flagged, or None if it never fired."""
        return next((t.index for t in self.turns if t.guarded), None)

    @property
    def n_turns(self) -> int:
        """Turn count for callers that should not walk `turns` just to ask length.

        tests/test_guard_runner_integration.py is the reader. Episode metrics
        walk `turns` themselves.
        """
        return len(self.turns)


# --------------------------------------------------------------------------- #
# Agents and scenarios
# --------------------------------------------------------------------------- #


@runtime_checkable
class Agent(Protocol):
    """The thing under attack.

    Deliberately narrow so a scripted agent can implement it without an API key.
    Two implementations exist: ScriptedAgent (last-turn compliance) and
    AccumulatingAgent (concatenated tool text). There is no LLM-backed agent
    in this tree. Adding one later would be a third implementation of the same
    protocol, not a different runner.
    """

    name: str

    def act(self, history: list[Turn]) -> ToolCall | str:
        """Return the next tool call, or a final answer as a string."""
        ...


@runtime_checkable
class Scenario(Protocol):
    """A reproducible episode: what the agent is asked, what the tools return, and what counts as compromise."""

    key: str
    # ScriptedScenario copies this onto opening_request when that is empty,
    # which is how this corpus states what the user asked. The runner reads
    # opening_request, not this field.
    description: str
    # ScriptedScenario reads this: benign scenarios get no triggers and
    # objective_met is always False. MiniScenario does the same. Episode
    # metrics do not; they derive attack-ness from payload_span (or
    # attack_succeeded for USER_INPUT). Both are intentional: a scenario
    # author must declare intent, and a finished Episode must remain
    # attributable without the Scenario object.
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
