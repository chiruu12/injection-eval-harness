"""Deprecated import path. Prefer `injection_eval.detectors`.

Kept so existing imports and the package `__all__` keep working while the
detectors live next to the protocol they implement.
"""

from .detectors.protectai import ProtectAI
from .detectors.regex_floor import RegexFloor, regex_hits
from .detectors.registry import all_detectors as all_systems
from .detectors.unplug_model import UnplugModel
from .detectors.unplug_pipeline import UnplugPipeline

__all__ = [
    "ProtectAI",
    "RegexFloor",
    "UnplugModel",
    "UnplugPipeline",
    "all_systems",
    "regex_hits",
]
