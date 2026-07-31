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
    """Thin application wrapper around openWakeWord.

    Imports and model downloads are delayed until construction so commands such
    as `--list-devices` continue to work without initializing the ML runtime.
    """

    def __init__(self, config: WakeWordConfig) -> None:
        self._validate_config(config)
        self.config = config

        try:
            import openwakeword
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "openwakeword is not installed. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        # The package stores the official model assets locally. Existing files
        # are skipped, so network access is normally needed only on first run.
        openwakeword.utils.download_models(model_names=["hey_jarvis"])

        self._model = Model(
            wakeword_models=[config.model_name],
            inference_framework="onnx",
        )

        loaded_models = tuple(self._model.models.keys())
        if not loaded_models:
            raise RuntimeError("No wake-word model was loaded.")

        self._model_key = loaded_models[0]
        self._last_detection_at = float("-inf")
        self._samples_seen = 0

    @staticmethod
    def _validate_config(config: WakeWordConfig) -> None:
        if not 0.0 < config.threshold < 1.0:
            raise ValueError("threshold must be between 0 and 1.")
        if config.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative.")
        if config.warmup_seconds < 0:
            raise ValueError("warmup_seconds cannot be negative.")
        if config.sample_rate != 16_000:
            raise ValueError("openWakeWord input must be 16000 Hz.")

    @property
    def loaded_model_name(self) -> str:
        return self._model_key

    def predict(self, samples: np.ndarray) -> DetectionResult:
        if not isinstance(samples, np.ndarray):
            raise TypeError("samples must be a NumPy array.")
        if samples.dtype != np.int16:
            raise ValueError(f"samples must be int16, received {samples.dtype}.")
        if samples.ndim != 1:
            raise ValueError(f"samples must be mono 1-D audio, received {samples.shape}.")

        predictions = self._model.predict(samples)
        score = float(predictions.get(self._model_key, 0.0))

        self._samples_seen += samples.size
        warmed_up = (
            self._samples_seen / self.config.sample_rate
            >= self.config.warmup_seconds
        )

        now = monotonic()
        cooldown_finished = (
            now - self._last_detection_at >= self.config.cooldown_seconds
        )
        detected = (
            warmed_up
            and cooldown_finished
            and score >= self.config.threshold
        )

        if detected:
            self._last_detection_at = now

        return DetectionResult(
            model_name=self._model_key,
            score=score,
            detected=detected,
            warmed_up=warmed_up,
        )
