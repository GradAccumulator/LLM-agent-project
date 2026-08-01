from __future__ import annotations

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
import importlib
from pathlib import Path
import re
import tempfile
from time import perf_counter, sleep
from typing import Any


@dataclass(frozen=True, slots=True)
class SpeechSynthesizerConfig:
    voice_name: str = "ko-KR-InJoonNeural"
    rate: int = 4
    volume: int = 100
    pitch_hz: int = -6
    max_characters: int = 1_200
    playback_timeout_seconds: float = 120.0
    voice_list_locale: str | None = "ko-KR"
    first_chunk_characters: int = 80
    chunk_characters: int = 180
    parallel_requests: int = 3
    mixer_buffer: int = 256
    playback_poll_seconds: float = 0.01


@dataclass(frozen=True, slots=True)
class VoiceInfo:
    index: int
    name: str
    language: str
    gender: str = ""
    friendly_name: str = ""


@dataclass(frozen=True, slots=True)
class SpeechTiming:
    chunks: int
    first_audio_seconds: float
    total_seconds: float


def clean_for_speech(text: str, max_characters: int = 1_200) -> str:
    """Convert a terminal-oriented GPT response into TTS-friendly text."""

    if max_characters <= 0:
        raise ValueError("max_characters must be positive.")

    cleaned = text.strip()
    if not cleaned:
        return ""

    cleaned = re.sub(
        r"```.*?```",
        " 코드 내용은 화면에 출력했습니다. ",
        cleaned,
        flags=re.DOTALL,
    )
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", " 링크 ", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"[*_~#>|]+", " ", cleaned)
    cleaned = re.sub(r"^\s*[-+]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\d+[.)]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) <= max_characters:
        return cleaned

    boundary = max(
        cleaned.rfind(". ", 0, max_characters),
        cleaned.rfind("다. ", 0, max_characters),
        cleaned.rfind("? ", 0, max_characters),
        cleaned.rfind("! ", 0, max_characters),
    )
    if boundary < max_characters // 2:
        boundary = max_characters

    shortened = cleaned[:boundary].rstrip(" ,.;:")
    return shortened + ". 자세한 내용은 화면에 출력했습니다."


def _hard_split(text: str, limit: int) -> list[str]:
    pieces: list[str] = []
    remaining = text.strip()

    while len(remaining) > limit:
        boundary = max(
            remaining.rfind(" ", 0, limit + 1),
            remaining.rfind(",", 0, limit + 1),
        )
        if boundary < limit // 2:
            boundary = limit

        pieces.append(remaining[:boundary].strip())
        remaining = remaining[boundary:].strip()

    if remaining:
        pieces.append(remaining)
    return pieces


def split_for_low_latency(
    text: str,
    first_limit: int,
    later_limit: int,
) -> tuple[str, ...]:
    """Use a short first sentence so audible output starts sooner."""

    if first_limit <= 0 or later_limit <= 0:
        raise ValueError("TTS chunk limits must be positive.")

    sentences = [
        item.strip()
        for item in re.split(r"(?<=[.!?。！？])\s+", text)
        if item.strip()
    ]
    if not sentences:
        return ()

    chunks: list[str] = []
    current = ""
    limit = first_limit

    for sentence in sentences:
        sentence_parts = _hard_split(sentence, limit)
        for part in sentence_parts:
            candidate = f"{current} {part}".strip()
            if current and len(candidate) > limit:
                chunks.append(current)
                current = part
                limit = later_limit
            else:
                current = candidate

            # Once the first chunk is reasonably complete, flush it early.
            if not chunks and len(current) >= first_limit:
                chunks.append(current)
                current = ""
                limit = later_limit

    if current:
        chunks.append(current)

    return tuple(chunk for chunk in chunks if chunk)


class SpeechSynthesizer:
    """Low-latency Edge neural TTS with persistent local playback."""

    def __init__(self, config: SpeechSynthesizerConfig) -> None:
        voice_name = config.voice_name.strip()
        if not voice_name:
            raise ValueError("TTS voice_name must not be empty.")
        if not -100 <= config.rate <= 100:
            raise ValueError("TTS rate must be between -100 and 100.")
        if not 0 <= config.volume <= 100:
            raise ValueError("TTS volume must be between 0 and 100.")
        if not -100 <= config.pitch_hz <= 100:
            raise ValueError("TTS pitch_hz must be between -100 and 100.")
        if config.max_characters <= 0:
            raise ValueError("TTS max_characters must be positive.")
        if config.playback_timeout_seconds <= 0:
            raise ValueError(
                "playback_timeout_seconds must be positive."
            )
        if config.first_chunk_characters <= 0:
            raise ValueError(
                "first_chunk_characters must be positive."
            )
        if config.chunk_characters <= 0:
            raise ValueError("chunk_characters must be positive.")
        if config.parallel_requests <= 0:
            raise ValueError("parallel_requests must be positive.")
        if config.mixer_buffer <= 0:
            raise ValueError("mixer_buffer must be positive.")
        if config.playback_poll_seconds <= 0:
            raise ValueError(
                "playback_poll_seconds must be positive."
            )

        try:
            self._edge_tts = importlib.import_module("edge_tts")
            self._pygame = importlib.import_module("pygame")
        except ImportError as exc:
            raise RuntimeError(
                "Edge TTS or pygame is not installed. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        self.config = config
        locale_parts = (
            voice_name.split("-", 2)[:2]
            if voice_name.count("-") >= 2
            else []
        )
        language = "-".join(locale_parts) if locale_parts else ""
        self._selected_voice = VoiceInfo(
            index=-1,
            name=voice_name,
            language=language,
        )
        self._executor = ThreadPoolExecutor(
            max_workers=config.parallel_requests,
            thread_name_prefix="jarvis-tts",
        )
        self._temporary_directory = tempfile.TemporaryDirectory(
            prefix="jarvis_tts_"
        )
        self._last_timing = SpeechTiming(
            chunks=0,
            first_audio_seconds=0.0,
            total_seconds=0.0,
        )
        self._closed = False

        try:
            self._pygame.mixer.pre_init(
                frequency=24_000,
                size=-16,
                channels=2,
                buffer=config.mixer_buffer,
            )
            self._pygame.mixer.init()
        except Exception as exc:
            self.close()
            raise RuntimeError(
                f"Could not initialize low-latency audio playback: {exc}"
            ) from exc

    @staticmethod
    def _signed_percent(value: int) -> str:
        return f"{value:+d}%"

    @staticmethod
    def _signed_hz(value: int) -> str:
        return f"{value:+d}Hz"

    @property
    def selected_voice(self) -> VoiceInfo:
        return self._selected_voice

    @property
    def last_timing(self) -> SpeechTiming:
        return self._last_timing

    async def _fetch_voices(self) -> list[dict[str, Any]]:
        voices = await self._edge_tts.list_voices()
        if not isinstance(voices, list):
            raise RuntimeError(
                "edge-tts returned an unexpected voice-list response."
            )
        return voices

    @property
    def available_voices(self) -> tuple[VoiceInfo, ...]:
        try:
            raw_voices = asyncio.run(self._fetch_voices())
        except Exception as exc:
            raise RuntimeError(
                "Could not retrieve Edge TTS voices. "
                "Check the internet connection."
            ) from exc

        locale_filter = self.config.voice_list_locale
        if locale_filter:
            locale_filter = locale_filter.casefold()

        voices: list[VoiceInfo] = []
        for raw in raw_voices:
            name = str(
                raw.get("ShortName")
                or raw.get("Name")
                or ""
            ).strip()
            locale = str(raw.get("Locale") or "").strip()
            if not name:
                continue
            if locale_filter and locale.casefold() != locale_filter:
                continue

            voices.append(
                VoiceInfo(
                    index=len(voices),
                    name=name,
                    language=locale,
                    gender=str(raw.get("Gender") or ""),
                    friendly_name=str(
                        raw.get("FriendlyName") or ""
                    ),
                )
            )

        return tuple(voices)

    def format_available_voices(self) -> str:
        lines: list[str] = []
        for voice in self.available_voices:
            selected = (
                "  [selected]"
                if voice.name.casefold()
                == self.selected_voice.name.casefold()
                else ""
            )
            lines.append(
                f"[{voice.index}] {voice.name} "
                f"(locale={voice.language or '?'}, "
                f"gender={voice.gender or '?'}){selected}"
            )

        if not lines:
            locale = self.config.voice_list_locale or "all"
            return f"No voices found for locale: {locale}"
        return "\n".join(lines)

    async def _synthesize_async(self, text: str) -> bytes:
        relative_volume = self.config.volume - 100
        communicate = self._edge_tts.Communicate(
            text=text,
            voice=self.config.voice_name,
            rate=self._signed_percent(self.config.rate),
            volume=self._signed_percent(relative_volume),
            pitch=self._signed_hz(self.config.pitch_hz),
        )

        audio = bytearray()
        async for item in communicate.stream():
            if item.get("type") == "audio":
                data = item.get("data")
                if isinstance(data, (bytes, bytearray)):
                    audio.extend(data)

        if not audio:
            raise RuntimeError("Edge TTS returned no audio data.")
        return bytes(audio)

    def _synthesize_chunk(self, text: str) -> bytes:
        try:
            return asyncio.run(self._synthesize_async(text))
        except Exception as exc:
            raise RuntimeError(
                f"Edge TTS synthesis failed: {exc}"
            ) from exc

    def _play_audio_bytes(self, audio: bytes, index: int) -> None:
        path = (
            Path(self._temporary_directory.name)
            / f"chunk_{index:03d}.mp3"
        )
        path.write_bytes(audio)

        try:
            self._pygame.mixer.music.load(str(path))
            self._pygame.mixer.music.play()

            started_at = perf_counter()
            while self._pygame.mixer.music.get_busy():
                if (
                    perf_counter() - started_at
                    > self.config.playback_timeout_seconds
                ):
                    self._pygame.mixer.music.stop()
                    raise RuntimeError("TTS playback timed out.")
                sleep(self.config.playback_poll_seconds)
        finally:
            try:
                self._pygame.mixer.music.unload()
            except Exception:
                pass
            path.unlink(missing_ok=True)

    def speak(self, text: str) -> bool:
        speakable = clean_for_speech(
            text,
            max_characters=self.config.max_characters,
        )
        if not speakable:
            return False

        chunks = split_for_low_latency(
            speakable,
            first_limit=self.config.first_chunk_characters,
            later_limit=self.config.chunk_characters,
        )
        if not chunks:
            return False

        started_at = perf_counter()
        futures: list[Future[bytes]] = [
            self._executor.submit(self._synthesize_chunk, chunk)
            for chunk in chunks
        ]

        first_audio_seconds = 0.0
        for index, future in enumerate(futures):
            try:
                audio = future.result(
                    timeout=self.config.playback_timeout_seconds
                )
            except TimeoutError as exc:
                for pending in futures:
                    pending.cancel()
                raise RuntimeError(
                    "Parallel Edge TTS synthesis timed out."
                ) from exc

            if index == 0:
                first_audio_seconds = perf_counter() - started_at
            self._play_audio_bytes(audio, index)

        self._last_timing = SpeechTiming(
            chunks=len(chunks),
            first_audio_seconds=first_audio_seconds,
            total_seconds=perf_counter() - started_at,
        )
        return True

    def close(self) -> None:
        if getattr(self, "_closed", True):
            return
        self._closed = True

        try:
            self._pygame.mixer.music.stop()
            self._pygame.mixer.quit()
        except Exception:
            pass

        self._executor.shutdown(
            wait=False,
            cancel_futures=True,
        )
        self._temporary_directory.cleanup()

    def __enter__(self) -> SpeechSynthesizer:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
