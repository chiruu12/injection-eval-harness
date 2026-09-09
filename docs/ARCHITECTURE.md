# Architecture, v2

v1 answered one question: how do detectors score a list of strings? It answered it
well enough to produce six findings, and its shape is now the limit. `systems.py`
holds scoring, thresholds and labels in one class; there is nowhere to put a tool,
a turn, or an agent; and every metric assumes a flat array of independent texts.

v2 keeps every v1 number reproducible and adds the thing the threat model always
claimed to be about: a detector sitting on an agent's untrusted-input boundary
across a multi-turn task.

## The shape

```
core/contracts.py        protocols and dataclasses, imports nothing from the package
  Detector, SpanDetector      score text
  Policy, Verdict, Action     decide what to do about a score
  Tool, ToolCall, ToolResult  where untrusted content enters
  Agent, Turn, Episode        what happens over time
  Scenario                    a reproducible episode plus its success predicates

detectors/               one adapter per system, each implementing Detector
policies/                threshold policies, including the vendors' published ones
guard.py                 Detector + Policy, placed at a boundary
tools/                   scripted tools; the injection lives in a tool result
agents/                  scripted agent (default) and an LLM adapter (optional)
scenarios/               the corpus, declarative
sim/runner.py            Scenario x Guard -> Episode
metrics/                 static metrics (v1) and episode metrics (v2)
report.py                rendering only
```

Dependency arrows point at `contracts`. Nothing else is allowed to import
`detectors` from `sim`, or `unplug` from anywhere but `detectors/`.

## Why these seams and not others

**Detector is not Guard.** v1's finding 2 was that every system fails calibration:
the scores rank well and the published thresholds are wrong. That finding is only
sayable because scoring and thresholding are separable. v2 makes the separation
structural instead of incidental, so a policy can be swapped without touching a
model adapter and the harness can attribute a failure to one or the other.

**SpanDetector is a separate protocol.** protectai is a sequence classifier and
cannot produce spans. Putting `spans()` on the base protocol would force a
NotImplementedError into three of four adapters, which makes the interface a
statement that is not true. Callers ask `isinstance(d, SpanDetector)`.

**The guard sits on tool output, not on user input.** That is the whole point of
the indirect threat model. The same `Guard` object can be placed at any boundary,
and where it is placed is a parameter of the run rather than a property of the
code, so "guard on tool output" and "guard on user input" are two rows of the same
table.

**Attack success is a scenario predicate, not "did the guard fire".** A guard that
blocks a payload and an agent that ignores it are different outcomes. Collapsing
them flatters the guard. `Episode` carries `attack_succeeded` and `task_completed`
independently, because a guard that stops the attack by breaking the task has not
won anything.

**The default agent is scripted.** Attack success then depends on the injected
text and the guard, not on a model's mood, and the suite stays deterministic and
offline. An LLM agent is a second implementation of the same protocol.

## What v2 measures that v1 could not

- Attack success rate, guard on versus guard off, per scenario family.
- Utility under guard: task completion on benign scenarios with the guard
  active. This is the over-refusal axis, and without it a block-everything guard
  scores perfectly.
- Detection turn, meaning which turn the guard first fired on. A guard that catches
  the payload after the agent has already acted on it has not defended anything.
- Position sensitivity: the same payload at turn 1 versus turn 8 of a long
  horizon episode. v1's carrier transform showed protectai losing 39 points to a
  400-character benign wrapper; this is that result extended along time instead of
  along document length.
- Multi-turn assembly: a payload split across several tool results, each
  fragment individually benign. No single-text detector can see this, and that is
  the finding.

## YAGNI, enforced

Not building: a plugin registry or entry points, a config DSL, async, a database,
a web UI, a caching layer, an abstract base class with one implementation, or a
scenario format that needs a parser. Scenarios are Python objects. If a scenario
corpus ever outgrows that, it can be serialised then and not before.

The v1 modules stay where they are and keep producing the v1 table. A refactor
that changes a published number is a bug, and `results/results.json` from v1 is
the regression test.
