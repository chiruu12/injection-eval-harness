"""The unplug-tiny document head, isolated from the SDK regex stage.

Disclosure: the author works on Unplug. Failure criteria in docs/PLAN.md were
fixed before the first run.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from ..core.contracts import Span
from ..pins import MODELS


@dataclass
class UnplugModel:
    """Unplug-tiny-v1's document head, with the SDK regex stage left off.

    Isolated so a published *model* number is not quietly a pipeline number.
    """

    key: str = "unplug-model"
    label: str = "unplug-tiny-v1 doc head, regex stage disabled"
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

    def spans(self, text: str) -> list[Span]:
        p = self._engine.predict(text)
        return [Span(s.start, s.end, float(s.score)) for s in p.spans]
