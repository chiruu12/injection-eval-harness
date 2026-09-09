"""The in-repo keyword floor every learned detector has to beat."""

from __future__ import annotations

import re
from dataclasses import dataclass

# Written from the public prompt-injection literature (OWASP LLM01, Greshake et
# al. 2023, the Lakera/Gandalf writeups) before any test row was inspected. It is
# a floor, not a contribution. If a 184M transformer cannot clear it on paired
# data, that is the result.
_PATTERNS: tuple[tuple[str, str], ...] = (
    ("ignore_previous", r"\b(ignore|disregard|forget)\b[^.\n]{0,40}\b(previous|prior|earlier|above|all)\b"),
    ("instruction_override", r"\b(new|updated|revised)\s+(instructions?|rules?|system\s+prompt)\b"),
    ("role_reassign", r"\byou\s+are\s+now\b|\bact\s+as\s+(?:a|an|the)\b|\bpretend\s+to\s+be\b"),
    ("system_prompt_probe", r"\b(system|initial|original)\s+prompt\b|\brepeat\s+(?:the|your)\s+instructions\b"),
    ("dev_mode", r"\b(developer|debug|god|dan)\s+mode\b|\bjailbreak\b"),
    ("exfiltrate", r"\b(send|email|post|upload|forward|exfiltrate)\b[^.\n]{0,40}\b(key|token|secret|credential|password|api)\b"),
    ("bypass_control", r"\b(bypass|skip|disable|override|circumvent)\b[^.\n]{0,40}\b(approval|review|human|check|guard|policy|confirmation)\b"),
    ("privilege", r"\b(admin|root|elevated|superuser)\s+(access|privileges?|rights?)\b"),
    ("silence", r"\b(do\s+not|don't|never)\b[^.\n]{0,30}\b(tell|inform|mention|log|report|notify)\b"),
    ("encoded_payload", r"\b(base64|rot13|hex|decode|decrypt)\b[^.\n]{0,40}\b(then|and|execute|run|follow|obey)\b"),
    ("urgency_authority", r"\b(urgent|immediately|without\s+delay)\b[^.\n]{0,40}\b(transfer|delete|send|approve|execute)\b"),
    ("tool_abuse", r"\b(call|invoke|execute|run)\b[^.\n]{0,30}\b(tool|function|command|shell|script)\b[^.\n]{0,40}\b(hidden|silently|without)\b"),
)

_COMPILED = tuple((name, re.compile(rx, re.IGNORECASE)) for name, rx in _PATTERNS)

# Three matches saturates. Gives the floor an ordering so it has a PR curve at
# all, rather than a single degenerate operating point.
_SATURATE_AT = 3


def regex_hits(text: str) -> list[str]:
    """The pattern names that fired, so a floor score can be audited."""
    return [name for name, rx in _COMPILED if rx.search(text)]


@dataclass
class RegexFloor:
    """A 12-pattern keyword floor published as a baseline, not a detector to ship."""

    key: str = "regex-floor"
    label: str = "regex floor (12 patterns, in-repo)"

    def score(self, texts: list[str]) -> list[float]:
        return [min(1.0, len(regex_hits(t)) / _SATURATE_AT) for t in texts]
