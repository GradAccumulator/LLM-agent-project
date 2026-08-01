from __future__ import annotations

import asyncio
from dataclasses import dataclass
import importlib
import re
import subprocess
import sys
from typing import Any


@dataclass(frozen=True, slots=True)
class SpeechSynthesizerConfig:
    voice_name: str = "ko-KR-InJoonNeural"
    rate: int = 0
    volume: int = 100
    pitch_hz: int = 0
    max_characters: int = 1_200
    playback_timeout_seconds: float = 120.0
    voice_list_locale: str | None = "ko-KR"


@dataclass(frozen=True, slots=True)
class VoiceInfo:
    index: int
    name: str
    language: str
    gender: str = ""
    friendly_name: str = ""


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


class SpeechSynthesizer:
    """Microsoft Edge online neural TTS with Windows-native playback."""

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

        try:
            importlib.import_module("edge_tts")
            importlib.import_module("edge_playback")
        except ImportError as exc:
            raise RuntimeError(
                "edge-tts is not installed. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        self.config = config
        locale = (
            voice_name.split("-", 2)[:2]
            if voice_name.count("-") >= 2
            else []
        )
        language = "-".join(locale) if locale else ""
        self._selected_voice = VoiceInfo(
            index=-1,
            name=voice_name,
            language=language,
        )

    @staticmethod
    def _signed_percent(value: int) -> str:
        return f"{value:+d}%"

    @staticmethod
    def _signed_hz(value: int) -> str:
        return f"{value:+d}Hz"

    @property
    def selected_voice(self) -> VoiceInfo:
        return self._selected_voice

    async def _fetch_voices(self) -> list[dict[str, Any]]:
        edge_tts = importlib.import_module("edge_tts")
        voices = await edge_tts.list_voices()
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
            if (
                locale_filter
                and locale.casefold() != locale_filter
            ):
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
            gender = voice.gender or "?"
            lines.append(
                f"[{voice.index}] {voice.name} "
                f"(locale={voice.language or '?'}, "
                f"gender={gender}){selected}"
            )

        if not lines:
            locale = self.config.voice_list_locale or "all"
            return f"No voices found for locale: {locale}"
        return "\n".join(lines)

    def speak(self, text: str) -> bool:
        speakable = clean_for_speech(
            text,
            max_characters=self.config.max_characters,
        )
        if not speakable:
            return False

        # 100 means normal volume in the CLI. Edge expects a relative value.
        relative_volume = self.config.volume - 100

        command = [
            sys.executable,
            "-m",
            "edge_playback",
            "--text",
            speakable,
            "--voice",
            self.config.voice_name,
            f"--rate={self._signed_percent(self.config.rate)}",
            f"--volume={self._signed_percent(relative_volume)}",
            f"--pitch={self._signed_hz(self.config.pitch_hz)}",
        ]

        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = getattr(
                subprocess,
                "CREATE_NO_WINDOW",
                0,
            )

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.config.playback_timeout_seconds,
                check=False,
                creationflags=creation_flags,
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                "Edge TTS playback timed out."
            ) from exc
        except OSError as exc:
            raise RuntimeError(
                f"Could not start Edge TTS playback: {exc}"
            ) from exc

        if completed.returncode != 0:
            details = (
                completed.stderr.strip()
                or completed.stdout.strip()
                or f"exit code {completed.returncode}"
            )
            raise RuntimeError(
                f"Edge TTS playback failed: {details}"
            )

        return True

    def close(self) -> None:
        return None

    def __enter__(self) -> SpeechSynthesizer:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()
