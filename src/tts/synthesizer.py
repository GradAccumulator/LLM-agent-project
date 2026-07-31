from __future__ import annotations

from dataclasses import dataclass
import re
import sys
from typing import Any


@dataclass(frozen=True, slots=True)
class SpeechSynthesizerConfig:
    voice_name: str | None = None
    rate: int = 0
    volume: int = 100
    max_characters: int = 1_200
    prefer_korean_voice: bool = True


@dataclass(frozen=True, slots=True)
class VoiceInfo:
    index: int
    name: str
    language: str
    token_id: str


def clean_for_speech(text: str, max_characters: int = 1_200) -> str:
    """Convert a terminal-oriented GPT response into TTS-friendly text."""

    if max_characters <= 0:
        raise ValueError("max_characters must be positive.")

    cleaned = text.strip()
    if not cleaned:
        return ""

    # Large code blocks are useful on screen but painful to read aloud.
    cleaned = re.sub(
        r"```.*?```",
        " 코드 내용은 화면에 출력했습니다. ",
        cleaned,
        flags=re.DOTALL,
    )

    # Keep link labels but do not read long URLs.
    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"https?://\S+", " 링크 ", cleaned)

    # Keep inline-code content while dropping Markdown markers.
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"[*_~#>|]+", " ", cleaned)
    cleaned = re.sub(r"^\s*[-+]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"^\s*\d+[.)]\s+", "", cleaned, flags=re.MULTILINE)

    # SAPI handles sentences better than line-heavy Markdown.
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
    """Local Windows SAPI5 text-to-speech output."""

    _KOREAN_LANGUAGE_IDS = {"412", "0412", "1042"}

    def __init__(self, config: SpeechSynthesizerConfig) -> None:
        if sys.platform != "win32":
            raise RuntimeError(
                "Local TTS currently supports Windows only."
            )
        if not -10 <= config.rate <= 10:
            raise ValueError("TTS rate must be between -10 and 10.")
        if not 0 <= config.volume <= 100:
            raise ValueError("TTS volume must be between 0 and 100.")
        if config.max_characters <= 0:
            raise ValueError("TTS max_characters must be positive.")

        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise RuntimeError(
                "pywin32 is not installed. Run "
                "`python -m pip install -r requirements.txt`."
            ) from exc

        self.config = config
        self._pythoncom = pythoncom
        self._pythoncom.CoInitialize()
        self._com_initialized = True

        try:
            self._speaker = win32com.client.Dispatch("SAPI.SpVoice")
            self._voices = self._load_voices()
            selected = self._select_voice()
            self._speaker.Voice = selected
            self._speaker.Rate = config.rate
            self._speaker.Volume = config.volume
            self._selected_voice = self._voice_info_for_token(selected)
        except Exception:
            self.close()
            raise

    @staticmethod
    def _token_attribute(token: Any, name: str) -> str:
        try:
            return str(token.GetAttribute(name) or "")
        except Exception:
            return ""

    @staticmethod
    def _token_id(token: Any) -> str:
        try:
            return str(token.Id or "")
        except Exception:
            return ""

    @staticmethod
    def _token_name(token: Any) -> str:
        try:
            return str(token.GetDescription() or "")
        except Exception:
            return ""

    def _load_voices(self) -> list[Any]:
        tokens = self._speaker.GetVoices()
        voices = [tokens.Item(index) for index in range(tokens.Count)]
        if not voices:
            raise RuntimeError(
                "Windows did not expose any SAPI speech voices."
            )
        return voices

    def _voice_info_for_token(self, token: Any) -> VoiceInfo:
        for index, voice in enumerate(self._voices):
            if self._token_id(voice) == self._token_id(token):
                return VoiceInfo(
                    index=index,
                    name=self._token_name(voice),
                    language=self._token_attribute(voice, "Language"),
                    token_id=self._token_id(voice),
                )

        return VoiceInfo(
            index=-1,
            name=self._token_name(token),
            language=self._token_attribute(token, "Language"),
            token_id=self._token_id(token),
        )

    def _is_korean_voice(self, token: Any) -> bool:
        language = self._token_attribute(token, "Language")
        parts = {
            part.strip().casefold()
            for part in re.split(r"[;, ]+", language)
            if part.strip()
        }
        return bool(parts & self._KOREAN_LANGUAGE_IDS)

    def _select_voice(self) -> Any:
        requested = (
            self.config.voice_name.strip().casefold()
            if self.config.voice_name
            else ""
        )

        if requested:
            for token in self._voices:
                searchable = (
                    f"{self._token_name(token)} "
                    f"{self._token_id(token)}"
                ).casefold()
                if requested in searchable:
                    return token

            available = ", ".join(
                self._token_name(token) for token in self._voices
            )
            raise RuntimeError(
                f"TTS voice was not found: {self.config.voice_name}. "
                f"Available voices: {available}"
            )

        if self.config.prefer_korean_voice:
            for token in self._voices:
                if self._is_korean_voice(token):
                    return token

        return self._speaker.Voice

    @property
    def selected_voice(self) -> VoiceInfo:
        return self._selected_voice

    @property
    def available_voices(self) -> tuple[VoiceInfo, ...]:
        return tuple(
            VoiceInfo(
                index=index,
                name=self._token_name(token),
                language=self._token_attribute(token, "Language"),
                token_id=self._token_id(token),
            )
            for index, token in enumerate(self._voices)
        )

    def format_available_voices(self) -> str:
        lines = []
        for voice in self.available_voices:
            selected = (
                "  [selected]"
                if voice.token_id == self.selected_voice.token_id
                else ""
            )
            lines.append(
                f"[{voice.index}] {voice.name} "
                f"(language={voice.language or '?'}){selected}"
            )
        return "\n".join(lines)

    def speak(self, text: str) -> bool:
        speakable = clean_for_speech(
            text,
            max_characters=self.config.max_characters,
        )
        if not speakable:
            return False

        try:
            # Default SAPI Speak is synchronous. The microphone loop is
            # intentionally paused while Jarvis is speaking.
            self._speaker.Speak(speakable)
        except Exception as exc:
            raise RuntimeError(
                f"Windows TTS playback failed: {exc}"
            ) from exc
        return True

    def close(self) -> None:
        self._speaker = None
        if getattr(self, "_com_initialized", False):
            try:
                self._pythoncom.CoUninitialize()
            finally:
                self._com_initialized = False

    def __enter__(self) -> SpeechSynthesizer:
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass
