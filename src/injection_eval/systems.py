"""The four systems under test.

Every system exposes the same contract: a continuous score in [0, 1] per text,
plus the operating threshold its vendor publishes. Thresholded metrics use the
published threshold; threshold-free metrics (PR-AUC, ROC-AUC) and the calibration
analysis use the raw score.

Disclosure: the author works on Unplug. `unplug-model` and `unplug-pipeline` are
two of the four rows here, the failure criteria in docs/PLAN.md were fixed before
the first run, and the regex floor is included so there is a number to lose to.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cached_property

from .pins import MODELS


@dataclass
class System:
    key: str
    label: str
    threshold: float
    threshold_source: str

    def score(self, texts: list[str]) -> list[float]:
        raise NotImplementedError


# ---------------------------------------------------------------- regex floor

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
    return [name for name, rx in _COMPILED if rx.search(text)]


@dataclass
class RegexFloor(System):
    key: str = "regex-floor"
    label: str = "regex floor (12 patterns, in-repo)"
    threshold: float = 0.5
    threshold_source: str = "one match fires"

    def score(self, texts: list[str]) -> list[float]:
        return [min(1.0, len(regex_hits(t)) / _SATURATE_AT) for t in texts]


# ------------------------------------------------------------- unplug (model)

@dataclass
class UnplugModel(System):
    key: str = "unplug-model"
    label: str = "unplug-tiny-v1 doc head, regex stage disabled"
    threshold: float = 0.9
    threshold_source: str = "model card: doc_threshold 0.9"
    batch_size: int = 16

    @cached_property
    def _engine(self):
        from huggingface_hub import snapshot_download
        from unplug.ml.span_model import SpanInferenceModel

        pin = MODELS["unplug_tiny"]
        path = snapshot_download(pin.repo_id, revision=pin.sha)
        engine = SpanInferenceModel(path, local_files_only=True)
        engine.load()
        return engine

    def score(self, texts: list[str]) -> list[float]:
        out: list[float] = []
        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i : i + self.batch_size]
            out.extend(float(p.doc_score) for p in self._engine.predict_batch(chunk))
        return out

    def spans(self, text: str) -> list[tuple[int, int, float]]:
        p = self._engine.predict(text)
        return [(s.start, s.end, float(s.score)) for s in p.spans]


# ---------------------------------------------------------- unplug (pipeline)

@dataclass
class UnplugPipeline(System):
    key: str = "unplug-pipeline"
    label: str = "Unplug SDK Guard.with_tiny(), regex + model"
    threshold: float = 0.5
    threshold_source: str = "SDK default block action"

    @cached_property
    def _guard(self):
        from unplug import Guard

        return Guard.with_tiny()

    def score(self, texts: list[str]) -> list[float]:
        return [float(self._guard.scan(t).risk_score) for t in texts]

    def stages(self, text: str) -> list[str]:
        """Which stage produced each finding. Used for the regex-vs-model split."""
        return [f.stage for f in self._guard.scan(text).findings]


# ------------------------------------------------------------------ protectai

@dataclass
class ProtectAI(System):
    key: str = "protectai"
    label: str = "protectai/deberta-v3-base-prompt-injection-v2"
    threshold: float = 0.5
    threshold_source: str = "argmax, the model card's usage example"
    batch_size: int = 16
    _loaded: dict = field(default_factory=dict, repr=False)

    @cached_property
    def _pipe(self):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        pin = MODELS["protectai"]
        tok = AutoTokenizer.from_pretrained(pin.repo_id, revision=pin.sha)
        mdl = AutoModelForSequenceClassification.from_pretrained(pin.repo_id, revision=pin.sha)
        mdl.eval()
        inj_idx = next(
            i for i, name in mdl.config.id2label.items() if str(name).upper().startswith("INJ")
        )
        return tok, mdl, int(inj_idx), torch

    def score(self, texts: list[str]) -> list[float]:
        tok, mdl, inj, torch = self._pipe
        out: list[float] = []
        with torch.no_grad():
            for i in range(0, len(texts), self.batch_size):
                enc = tok(
                    texts[i : i + self.batch_size],
                    return_tensors="pt",
                    truncation=True,
                    max_length=512,
                    padding=True,
                )
                probs = mdl(**enc).logits.softmax(-1)[:, inj]
                out.extend(float(p) for p in probs)
        return out


def all_systems() -> list[System]:
    return [RegexFloor(), UnplugModel(), UnplugPipeline(), ProtectAI()]
