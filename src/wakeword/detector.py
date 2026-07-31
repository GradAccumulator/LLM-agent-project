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
        if not 0.0 < config.threshold < 1.0:
            raise ValueError("threshold must be between 0 and 1.")

        self.config = config

        try:
            import openwakeword
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "openwakeword is not installed. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        openwakeword.utils.download_models(model_names=["hey_jarvis"])
        self._model = Model(
            wakeword_models=[config.model_name],
            inference_framework="onnx",
        )

        loaded = tuple(self._model.models.keys())
        if not loaded:
            raise RuntimeError("No wake-word model was loaded.")

        self._model_key = loaded[0]
        self._last_detection_at = float("-inf")
        self._samples_seen = 0

    @property
    def loaded_model_name(self) -> str:
        return self._model_key

    def predict(self, samples: np.ndarray) -> DetectionResult:
        predictions = self._model.predict(samples)
        score = float(predictions.get(self._model_key, 0.0))

        self._samples_seen += samples.size
        warmed_up = (
            self._samples_seen / self.config.sample_rate
            >= self.config.warmup_seconds
        )

        now = monotonic()
        detected = (
            warmed_up
            and score >= self.config.threshold
            and now - self._last_detection_at >= self.config.cooldown_seconds
        )
        if detected:
            self._last_detection_at = now

        return DetectionResult(
            model_name=self._model_key,
            score=score,
            detected=detected,
            warmed_up=warmed_up,
        )
