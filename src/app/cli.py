from __future__ import annotations

import argparse
from pathlib import Path


def parse_device(value: str) -> int | str:
    value = value.strip()
    return int(value) if value.isdigit() else value


def parse_language(value: str) -> str | None:
    value = value.strip()
    return None if value.casefold() == "auto" else value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Detect Hey Jarvis, capture speech, transcribe it locally, "
            "run GPT tools, inspect the screen, and speak the response."
        )
    )
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--device", type=parse_device, default=None)
    parser.add_argument(
        "--prefer-device",
        default="BlackShark",
        help="Preferred microphone name substring. Default: BlackShark.",
    )
    parser.add_argument(
        "--wake-threshold",
        "--threshold",
        dest="wake_threshold",
        type=float,
        default=0.45,
        help="Wake-word threshold. Default: 0.45.",
    )
    parser.add_argument("--cooldown", type=float, default=2.0)
    parser.add_argument(
        "--vad-threshold",
        type=float,
        default=0.50,
        help="Silero speech threshold. Default: 0.50.",
    )
    parser.add_argument(
        "--start-timeout",
        type=float,
        default=4.0,
        help="Seconds to wait for speech after wake-word detection.",
    )
    parser.add_argument(
        "--end-silence",
        type=float,
        default=0.4,
        help="Silence duration that ends a command. Default: 0.4.",
    )
    parser.add_argument(
        "--max-command-seconds",
        type=float,
        default=15.0,
        help="Maximum captured command length.",
    )
    parser.add_argument(
        "--save-dir",
        type=Path,
        default=Path("recordings"),
        help="Directory for captured WAV files.",
    )
    parser.add_argument(
        "--no-save-audio",
        action="store_true",
        help="Do not keep captured command WAV files.",
    )

    parser.add_argument(
        "--stt-model",
        default="turbo",
        help="Faster-Whisper model name or local path. Default: turbo.",
    )
    parser.add_argument(
        "--stt-language",
        type=parse_language,
        default="ko",
        help="Language code, or auto. Default: ko.",
    )
    parser.add_argument(
        "--stt-device",
        choices=("auto", "cuda", "cpu"),
        default="auto",
        help="STT inference device. Default: auto.",
    )
    parser.add_argument(
        "--stt-compute-type",
        default="float16",
        help=(
            "CTranslate2 compute type. Default: float16 on CUDA; "
            "automatic CPU fallback uses int8."
        ),
    )
    parser.add_argument(
        "--stt-beam-size",
        type=int,
        default=1,
        help="Whisper beam size. Default: 1 for low latency.",
    )
    parser.add_argument(
        "--stt-best-of",
        type=int,
        default=1,
        help="Whisper best-of candidates. Default: 1 for low latency.",
    )
    parser.add_argument(
        "--stt-model-dir",
        type=Path,
        default=Path("models/faster-whisper"),
        help="Model download/cache directory.",
    )
    parser.add_argument(
        "--stt-workers",
        type=int,
        default=2,
        help="CTranslate2 worker count. Default: 2.",
    )
    parser.add_argument(
        "--disable-stt-warmup",
        action="store_true",
        help="Skip the startup inference used to warm CUDA kernels.",
    )
    parser.add_argument(
        "--stt-cpu-threads",
        type=int,
        default=16,
        help="CPU threads used by CTranslate2 fallback. Default: 16.",
    )

    parser.add_argument(
        "--llm-model",
        default="gpt-5.6-luna",
        help="OpenAI model ID. Default: gpt-5.6-luna.",
    )
    parser.add_argument(
        "--llm-reasoning",
        choices=("none", "low", "medium", "high", "xhigh", "max"),
        default="low",
        help="Reasoning effort. Default: low.",
    )
    parser.add_argument(
        "--llm-max-output-tokens",
        type=int,
        default=512,
        help="Maximum LLM output tokens. Default: 512.",
    )
    parser.add_argument(
        "--llm-timeout",
        type=float,
        default=60.0,
        help="OpenAI API timeout in seconds. Default: 60.",
    )
    parser.add_argument(
        "--no-llm-memory",
        action="store_true",
        help="Do not link responses across voice commands.",
    )
    parser.add_argument(
        "--disable-tools",
        action="store_true",
        help="Disable all local function tools.",
    )
    parser.add_argument(
        "--llm-max-tool-rounds",
        type=int,
        default=4,
        help="Maximum function-calling rounds per command. Default: 4.",
    )
    parser.add_argument(
        "--vision-detail",
        choices=("low", "high", "original", "auto"),
        default="original",
        help=(
            "Detail level for screen images sent to GPT. "
            "Default: original."
        ),
    )

    parser.add_argument(
        "--list-tts-voices",
        action="store_true",
        help="List Edge neural TTS voices and exit.",
    )
    parser.add_argument(
        "--disable-tts",
        "--no-tts",
        action="store_true",
        help="Start with spoken responses disabled.",
    )
    parser.add_argument(
        "--tts-voice",
        default="ko-KR-InJoonNeural",
        help=(
            "Microsoft Edge neural voice name. "
            "Default: ko-KR-InJoonNeural."
        ),
    )
    parser.add_argument(
        "--tts-rate",
        type=int,
        default=0,
        help="Edge TTS speech-rate percent from -100 to 100. Default: 0.",
    )
    parser.add_argument(
        "--tts-volume",
        type=int,
        default=100,
        help="Speech volume from 0 to 100. Default: 100.",
    )
    parser.add_argument(
        "--tts-pitch",
        type=int,
        default=0,
        help="Edge TTS pitch adjustment in Hz from -100 to 100. Default: 0.",
    )
    parser.add_argument(
        "--tts-max-characters",
        type=int,
        default=1200,
        help="Maximum response characters spoken aloud. Default: 1200.",
    )
    parser.add_argument(
        "--tts-first-chunk-characters",
        type=int,
        default=80,
        help="Maximum size of the first TTS chunk. Default: 80.",
    )
    parser.add_argument(
        "--tts-chunk-characters",
        type=int,
        default=180,
        help="Maximum size of later TTS chunks. Default: 180.",
    )
    parser.add_argument(
        "--tts-parallel-requests",
        type=int,
        default=3,
        help="Parallel Edge TTS synthesis requests. Default: 3.",
    )
    parser.add_argument(
        "--tts-mixer-buffer",
        type=int,
        default=256,
        help="pygame mixer buffer size. Default: 256.",
    )

    parser.add_argument(
        "--hide-state-transitions",
        action="store_true",
        help="Do not print state transition lines.",
    )
    parser.add_argument(
        "--recovery-delay",
        type=float,
        default=0.25,
        help="Delay before returning to LISTENING after an error.",
    )
    return parser
