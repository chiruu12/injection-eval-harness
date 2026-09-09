"""The ProtectAI sequence classifier, the independent row on the table."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property

from ..pins import MODELS


@dataclass
class ProtectAI:
    """protectai/deberta-v3-base-prompt-injection-v2, scored at the model-card argmax."""

    key: str = "protectai"
    label: str = "protectai/deberta-v3-base-prompt-injection-v2"
    batch_size: int = 16

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
