"""Agents under attack: three implementations of one protocol.

ScriptedAgent is last-turn regex compliance. An attack-success number from it
says the injected text matched a trigger the agent was allowed to read. It
cannot say that a language model followed an instruction.

AccumulatingAgent is the same rule over concatenated readable tool text. An
attack-success number from it says whether the guard withheld a fragment that
would have assembled a trigger. It cannot say that a model assembled one.

LlmAgent is a model that chooses tools from the conversation. An attack-success
number from it can say the guard stopped, or failed to stop, a model from
following an injected instruction. It cannot join the static table: it is
opt-in, needs a Completion backend, and is not byte-reproducible.
"""

from .accumulating import AccumulatingAgent
from .llm import (
    Completion,
    FakeCompletion,
    LlmAgent,
    LlmBackendUnavailable,
    OpenAICompatCompletion,
)
from .scripted import ScriptedAgent

__all__ = [
    "AccumulatingAgent",
    "Completion",
    "FakeCompletion",
    "LlmAgent",
    "LlmBackendUnavailable",
    "OpenAICompatCompletion",
    "ScriptedAgent",
]
