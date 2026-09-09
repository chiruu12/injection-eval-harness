"""Pins must be full commit shas. A branch name here would silently unfreeze the eval."""

import re

from injection_eval.pins import DATASETS, MODELS

SHA = re.compile(r"^[0-9a-f]{40}$")


def test_every_dataset_is_pinned_to_a_commit():
    for key, pin in DATASETS.items():
        assert SHA.match(pin.sha), f"{key} is not a 40-char sha"


def test_every_model_is_pinned_to_a_commit():
    for key, pin in MODELS.items():
        assert SHA.match(pin.sha), f"{key} is not a 40-char sha"


def test_primary_dataset_postdates_every_model():
    primary = DATASETS["boundary_pairs"]
    assert primary.role == "primary"
    for key, model in MODELS.items():
        assert model.published < primary.published, (
            f"{key} published {model.published}, primary set {primary.published}: "
            "contamination is no longer ruled out by date"
        )
