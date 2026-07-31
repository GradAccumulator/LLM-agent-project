from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class VoiceActivityConfig:
    sample_rate: int = 16_000
    threshold: float = 0.50
    chunk_samples: int = 512
    use_onnx: bool = True


class VoiceActivityDetector:
    """Streaming Silero VAD wrapper for int16, 16 kHz mono audio."""

    def __init__(self, config: VoiceActivityConfig) -> None:
        if config.sample_rate not in (8_000, 16_000):
            raise ValueError("Silero VAD supports 8000 Hz or 16000 Hz.")
        if not 0.0 < config.threshold < 1.0:
            raise ValueError("VAD threshold must be between 0 and 1.")
        if config.chunk_samples <= 0:
            raise ValueError("chunk_samples must be positive.")

        try:
            import torch
            from silero_vad import load_silero_vad
        except ImportError as exc:
            raise RuntimeError(
                "silero-vad is not installed. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        torch.set_num_threads(1)

        self.config = config
        self._torch = torch
        self._model = load_silero_vad(onnx=config.use_onnx)
        self._buffer = np.empty(0, dtype=np.int16)
        self._last_probability = 0.0

    @property
    def last_probability(self) -> float:
        return self._last_probability

    def reset(self) -> None:
        self._buffer = np.empty(0, dtype=np.int16)
        self._last_probability = 0.0

        reset_states = getattr(self._model, "reset_states", None)
        if callable(reset_states):
            reset_states()

    def predict(self, samples: np.ndarray) -> float:
        """Return the maximum speech probability produced by this audio frame."""

        if samples.ndim != 1:
            raise ValueError("VAD audio must be a one-dimensional mono array.")
        if samples.dtype != np.int16:
            samples = samples.astype(np.int16, copy=False)

        self._buffer = np.concatenate((self._buffer, samples))
        probabilities: list[float] = []

        while self._buffer.size >= self.config.chunk_samples:
            chunk = self._buffer[: self.config.chunk_samples]
            self._buffer = self._buffer[self.config.chunk_samples :]

            normalized = chunk.astype(np.float32) / 32768.0
            tensor = self._torch.from_numpy(normalized)

            probability = float(
                self._model(tensor, self.config.sample_rate).item()
            )
            probabilities.append(probability)

        if probabilities:
            self._last_probability = max(probabilities)

        return self._last_probability

    def is_speech(self, samples: np.ndarray) -> tuple[bool, float]:
        probability = self.predict(samples)
        return probability >= self.config.threshold, probability
