"""Declarative scenario corpus for the agentic evaluation."""

from .registry import all_scenarios, by_benign_group, by_family
from .scenario import ADVERSARIAL_BENIGN, PLAIN_BENIGN

__all__ = [
    "ADVERSARIAL_BENIGN",
    "PLAIN_BENIGN",
    "all_scenarios",
    "by_benign_group",
    "by_family",
]
