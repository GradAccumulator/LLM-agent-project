from __future__ import annotations
from dataclasses import dataclass
from time import monotonic
import numpy as np

@dataclass(frozen=True, slots=True)
class WakeWordConfig:
    model_name: str = "hey jarvis"
    threshold: float = 0.5
    cooldown_seconds: float = 2.0
    warmup_seconds: float = 1.0
    sample_rate: int = 16_000

@dataclass(frozen=True, slots=True)
class DetectionResult:
    model_name: str
    score: float
    detected: bool
    warmed_up: bool

class WakeWordDetector:
    def __init__(self, config: WakeWordConfig) -> None:
        if not 0 < config.threshold < 1: raise ValueError("threshold must be between 0 and 1")
        self.config=config
        import openwakeword
        from openwakeword.model import Model
        openwakeword.utils.download_models(model_names=["hey_jarvis"])
        self._model=Model(wakeword_models=[config.model_name], inference_framework="onnx")
        self._model_key=next(iter(self._model.models))
        self._last=float("-inf")
        self._samples=0

    @property
    def loaded_model_name(self) -> str: return self._model_key

    def predict(self, samples: np.ndarray) -> DetectionResult:
        score=float(self._model.predict(samples).get(self._model_key, 0.0))
        self._samples += samples.size
        warmed=self._samples/self.config.sample_rate >= self.config.warmup_seconds
        now=monotonic()
        detected=warmed and score>=self.config.threshold and now-self._last>=self.config.cooldown_seconds
        if detected: self._last=now
        return DetectionResult(self._model_key, score, detected, warmed)
