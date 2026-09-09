"""Vendor adapters that implement Detector (and SpanDetector, when they can)."""

from .protectai import ProtectAI
from .regex_floor import RegexFloor, regex_hits
from .registry import all_detectors
from .unplug_model import UnplugModel
from .unplug_pipeline import UnplugPipeline

__all__ = [
    "ProtectAI",
    "RegexFloor",
    "UnplugModel",
    "UnplugPipeline",
    "all_detectors",
    "regex_hits",
]
