"""The four detectors under test, constructed at their in-repo defaults.

A function that returns instances, not a plugin registry: the set is closed and
listed here because those are the table rows.
"""

from __future__ import annotations

from ..core.contracts import Detector
from .protectai import ProtectAI
from .regex_floor import RegexFloor
from .unplug_model import UnplugModel
from .unplug_pipeline import UnplugPipeline


def all_detectors() -> list[Detector]:
    """The four rows of the eval table, in table order."""
    return [RegexFloor(), UnplugModel(), UnplugPipeline(), ProtectAI()]
